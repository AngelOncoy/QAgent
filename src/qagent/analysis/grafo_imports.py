"""Grafo de dependencias e imports internos con tree-sitter (SPK #196).

Analiza estáticamente los imports internos de un proyecto, siguiendo referencias
entre archivos sin ejecutar código del usuario (0 tokens, 100 % determinista).
Permite enriquecer el contexto del Generator para que no invente valores de retorno
ni deje dependencias sin simular en proyectos modulares.
"""

from __future__ import annotations

import tokenize
from dataclasses import dataclass, field
from pathlib import Path

from tree_sitter import Node, Tree

from qagent.analysis import arbol_ts, texto_ts
from qagent.analysis.arbol_ts import (
    campo,
    cuerpo,
    definicion,
    es_clase,
    es_funcion,
    importacion,
    nombre,
    sentencias,
    sin_envoltura,
    texto,
)


@dataclass(frozen=True)
class SimboloDependencia:
    """Información estática de un símbolo definido en una dependencia interna."""

    modulo_origen: str
    archivo_origen: str
    nombre: str
    tipo: str  # "funcion", "clase", "variable"
    firma: str = ""
    docstring: str = ""
    atributos_o_campos: list[str] = field(default_factory=list)
    llamadas_internas: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ModuloDependencia:
    """Módulo interno del proyecto importado directa o indirectamente."""

    ruta_relativa: str
    ruta_importable: str
    simbolos: dict[str, SimboloDependencia] = field(default_factory=dict)
    imports_internos: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GrafoDependencias:
    """Grafo de dependencias internas de una función o endpoint."""

    modulo_raiz: str
    objetivo: str
    tipo_objetivo: str  # "funcion" o "endpoint"
    modulos: dict[str, ModuloDependencia] = field(default_factory=dict)
    simbolos_directos: list[SimboloDependencia] = field(default_factory=list)
    llamadas_transitivas: list[tuple[str, str]] = field(default_factory=list)


def parsear_archivo(ruta: Path) -> tuple[Tree, str] | None:
    """Lee y parsea un archivo Python con tree-sitter sin ejecutarlo."""
    try:
        with tokenize.open(ruta) as f:
            fuente = f.read()
        arbol = arbol_ts.parsear(fuente)
        return arbol, fuente
    except (OSError, UnicodeDecodeError, SyntaxError):
        return None


def resolver_ruta_import(
    raiz: Path, modulo_actual: str, imp: arbol_ts.Importacion
) -> list[tuple[str, str, str]]:
    """Resuelve un import relativo o absoluto contra archivos del proyecto.

    Returns:
        Lista de tuplas (nombre_simbolo, ruta_relativa_archivo, nombre_punteado).
    """
    resultados: list[tuple[str, str, str]] = []
    raiz_path = Path(raiz).resolve()
    archivo_actual = (raiz_path / modulo_actual).resolve()
    dir_actual = archivo_actual.parent

    if imp.desde:
        # from ... import ...
        if imp.nivel > 0:
            # Import relativo: . o ..
            dir_base = dir_actual
            for _ in range(imp.nivel - 1):
                dir_base = dir_base.parent
            if imp.modulo:
                partes = imp.modulo.split(".")
                dir_destino = dir_base.joinpath(*partes)
            else:
                dir_destino = dir_base
        else:
            # Import absoluto desde la raíz del proyecto
            if not imp.modulo:
                return []
            partes = imp.modulo.split(".")
            dir_destino = raiz_path.joinpath(*partes)

        # Puede ser un archivo .py o un paquete (__init__.py)
        candidato_py = dir_destino.with_suffix(".py")
        candidato_init = dir_destino / "__init__.py"

        archivo_encontrado: Path | None = None
        if candidato_py.is_file():
            archivo_encontrado = candidato_py
        elif candidato_init.is_file():
            archivo_encontrado = candidato_init

        if archivo_encontrado is not None:
            try:
                ruta_rel = archivo_encontrado.relative_to(raiz_path).as_posix()
                mod_punteado = (
                    archivo_encontrado.relative_to(raiz_path)
                    .with_suffix("")
                    .as_posix()
                    .replace("/", ".")
                )
                mod_punteado = mod_punteado.removesuffix(".__init__")

                for original, alias in imp.nombres:
                    resultados.append((original, ruta_rel, mod_punteado))
            except ValueError:
                pass
        else:
            # Podría ser `from . import servicio` donde `servicio` es un archivo .py
            for original, alias in imp.nombres:
                cand_sub = dir_destino / f"{original}.py"
                if cand_sub.is_file():
                    try:
                        ruta_rel = cand_sub.relative_to(raiz_path).as_posix()
                        mod_punteado = (
                            cand_sub.relative_to(raiz_path)
                            .with_suffix("")
                            .as_posix()
                            .replace("/", ".")
                        )
                        resultados.append(("*", ruta_rel, mod_punteado))
                    except ValueError:
                        pass
    else:
        # import a.b.c
        for original, alias in imp.nombres:
            partes = original.split(".")
            cand_py = raiz_path.joinpath(*partes).with_suffix(".py")
            cand_init = raiz_path.joinpath(*partes) / "__init__.py"
            encontrado = (
                cand_py
                if cand_py.is_file()
                else (cand_init if cand_init.is_file() else None)
            )
            if encontrado is not None:
                try:
                    ruta_rel = encontrado.relative_to(raiz_path).as_posix()
                    mod_punteado = (
                        encontrado.relative_to(raiz_path)
                        .with_suffix("")
                        .as_posix()
                        .replace("/", ".")
                    )
                    mod_punteado = mod_punteado.removesuffix(".__init__")
                    resultados.append(("*", ruta_rel, mod_punteado))
                except ValueError:
                    pass

    return resultados


def _extraer_llamadas(nodo: Node) -> list[str]:
    """Obtiene los nombres de llamadas dentro de un subárbol."""
    llamadas = []
    for actual in arbol_ts.recorrer(nodo):
        if actual.type == "call":
            fn = campo(actual, "function")
            fn = sin_envoltura(fn)
            if fn is None:
                continue
            if fn.type == "identifier":
                llamadas.append(texto(fn))
            elif fn.type == "attribute":
                attr = campo(fn, "attribute")
                if attr is not None:
                    llamadas.append(texto(attr))
    return llamadas


def extraer_simbolos_de_archivo(
    ruta_archivo: Path, ruta_relativa: str, mod_punteado: str
) -> dict[str, SimboloDependencia]:
    """Extrae las firmas y docstrings de funciones y clases de un módulo con tree-sitter."""
    parsed = parsear_archivo(ruta_archivo)
    if parsed is None:
        return {}
    arbol, _ = parsed
    simbolos: dict[str, SimboloDependencia] = {}

    for sentencia in sentencias(arbol.root_node):
        elem = definicion(sentencia)
        if es_funcion(elem):
            nom = nombre(elem)
            sig = texto_ts.firma(elem)
            doc = texto_ts.docstring(cuerpo(elem)) or ""
            calls = _extraer_llamadas(elem)
            simbolos[nom] = SimboloDependencia(
                modulo_origen=mod_punteado,
                archivo_origen=ruta_relativa,
                nombre=nom,
                tipo="funcion",
                firma=sig,
                docstring=doc.splitlines()[0] if doc else "",
                llamadas_internas=calls,
            )
        elif es_clase(elem):
            nom = nombre(elem)
            doc = texto_ts.docstring(cuerpo(elem)) or ""
            campos: list[str] = []
            metodos_sig: list[str] = []
            bloque = cuerpo(elem)
            if bloque is not None:
                for sub in sentencias(bloque):
                    sub_def = definicion(sub)
                    if es_funcion(sub_def):
                        met_nom = nombre(sub_def)
                        met_sig = texto_ts.firma(sub_def)
                        metodos_sig.append(f"{met_nom}{met_sig}")
                    elif sub.type == "expression_statement":
                        # Anotaciones de atributos de clase / BaseModel
                        asig = campo(sub, "assignment")
                        if asig is not None:
                            izq = campo(asig, "left")
                            tip = campo(asig, "type")
                            if izq and tip:
                                campos.append(f"{texto(izq)}: {texto(tip)}")
            simbolos[nom] = SimboloDependencia(
                modulo_origen=mod_punteado,
                archivo_origen=ruta_relativa,
                nombre=nom,
                tipo="clase",
                firma=f"class {nom}",
                docstring=doc.splitlines()[0] if doc else "",
                atributos_o_campos=campos + metodos_sig[:5],
            )
    return simbolos


def construir_grafo_dependencias(
    raiz: str | Path,
    modulo: str,
    nombre_objetivo: str,
    tipo_objetivo: str = "funcion",
    profundidad_max: int = 3,
) -> GrafoDependencias:
    """Construye el grafo estático de dependencias internas para un objetivo.

    Args:
        raiz: Directorio raíz del proyecto.
        modulo: Ruta relativa del archivo que contiene el objetivo.
        nombre_objetivo: Nombre de la función o endpoint.
        tipo_objetivo: "funcion" o "endpoint".
        profundidad_max: Nivel máximo de recursión de imports.
    """
    raiz_path = Path(raiz).resolve()
    archivo_objetivo = raiz_path / modulo
    parsed = parsear_archivo(archivo_objetivo)
    if parsed is None:
        return GrafoDependencias(
            modulo_raiz=modulo,
            objetivo=nombre_objetivo,
            tipo_objetivo=tipo_objetivo,
        )

    arbol, _ = parsed
    nodo_objetivo = next(
        (
            definicion(nodo)
            for nodo in sentencias(arbol.root_node)
            if (es_funcion(nodo) or es_clase(nodo)) and nombre(nodo) == nombre_objetivo
        ),
        None,
    )

    llamadas_objetivo = (
        _extraer_llamadas(nodo_objetivo) if nodo_objetivo is not None else []
    )

    modulos_visitados: dict[str, ModuloDependencia] = {}
    simbolos_directos: list[SimboloDependencia] = []
    llamadas_transitivas: list[tuple[str, str]] = []

    # 1. Analizar imports del archivo raíz
    cola: list[tuple[str, int]] = [(modulo, 0)]
    visitados: set[str] = {modulo}

    # Mapa de imports locales en el módulo raíz: nombre_local -> (ruta_rel, mod_punteado, nombre_orig)
    mapa_importaciones_raiz: dict[str, tuple[str, str, str]] = {}

    for sentencia in sentencias(arbol.root_node):
        imp = importacion(sentencia)
        if imp is not None:
            resueltos = resolver_ruta_import(raiz_path, modulo, imp)
            for sym, ruta_rel, mod_punt in resueltos:
                mapa_importaciones_raiz[sym] = (ruta_rel, mod_punt, sym)
                if ruta_rel not in visitados and len(visitados) < 15:
                    visitados.add(ruta_rel)
                    cola.append((ruta_rel, 1))

    # 2. Recorrer módulos internos hasta profundidad_max
    while cola:
        ruta_rel_act, prof = cola.pop(0)
        arch_act = raiz_path / ruta_rel_act
        mod_punt_act = Path(ruta_rel_act).with_suffix("").as_posix().replace("/", ".")
        simbolos_mod = extraer_simbolos_de_archivo(arch_act, ruta_rel_act, mod_punt_act)

        mod_dep = ModuloDependencia(
            ruta_relativa=ruta_rel_act,
            ruta_importable=mod_punt_act,
            simbolos=simbolos_mod,
        )
        modulos_visitados[ruta_rel_act] = mod_dep

        # Si estamos dentro de la profundidad permitida, seguir sus imports
        if prof < profundidad_max:
            sub_parsed = parsear_archivo(arch_act)
            if sub_parsed:
                sub_arbol, _ = sub_parsed
                for sub_sent in sentencias(sub_arbol.root_node):
                    sub_imp = importacion(sub_sent)
                    if sub_imp is not None:
                        for _, sub_rel, _ in resolver_ruta_import(
                            raiz_path, ruta_rel_act, sub_imp
                        ):
                            if sub_rel not in visitados and len(visitados) < 15:
                                visitados.add(sub_rel)
                                cola.append((sub_rel, prof + 1))

    # 3. Cruzar las llamadas del objetivo con los símbolos importados
    for nom_llamada in dict.fromkeys(llamadas_objetivo):
        if nom_llamada in mapa_importaciones_raiz:
            ruta_rel, mod_punt, nom_orig = mapa_importaciones_raiz[nom_llamada]
            mod_info = modulos_visitados.get(ruta_rel)
            if mod_info and nom_orig in mod_info.simbolos:
                simb = mod_info.simbolos[nom_orig]
                simbolos_directos.append(simb)
                # Inspeccionar llamadas transitivas de ese símbolo
                for sub_call in simb.llamadas_internas:
                    llamadas_transitivas.append((simb.nombre, sub_call))
        else:
            # Buscar si está definido en alguno de los módulos importados
            for mod_info in modulos_visitados.values():
                if nom_llamada in mod_info.simbolos:
                    simb = mod_info.simbolos[nom_llamada]
                    if simb not in simbolos_directos:
                        simbolos_directos.append(simb)

    return GrafoDependencias(
        modulo_raiz=modulo,
        objetivo=nombre_objetivo,
        tipo_objetivo=tipo_objetivo,
        modulos=modulos_visitados,
        simbolos_directos=simbolos_directos,
        llamadas_transitivas=llamadas_transitivas,
    )


def formatear_contexto_grafo(grafo: GrafoDependencias, modulo_importador: str) -> str:
    """Genera el bloque textual de contexto de dependencias para el prompt del Generator."""
    if not grafo.simbolos_directos and not grafo.modulos:
        return ""

    lineas = [
        "DEPENDENCIAS INTERNAS DEL PROYECTO (firmas estáticas extraídas con tree-sitter):"
    ]

    if grafo.tipo_objetivo == "endpoint":
        lineas.append(
            "- Este endpoint invoca funciones y servicios definidos en otros archivos del proyecto."
        )

    for simb in grafo.simbolos_directos:
        doc_info = f" — {simb.docstring}" if simb.docstring else ""
        if simb.tipo == "funcion":
            lineas.append(
                f"- Función: `{simb.modulo_origen}.{simb.nombre}{simb.firma}`{doc_info}"
            )
            lineas.append(
                f"  Sugerencia mock: `unittest.mock.patch('{modulo_importador}.{simb.nombre}', return_value=...)`"
            )
        elif simb.tipo == "clase":
            lineas.append(f"- Clase: `{simb.modulo_origen}.{simb.nombre}`{doc_info}")
            if simb.atributos_o_campos:
                lineas.append(
                    f"  Campos y métodos: {', '.join(simb.atributos_o_campos[:6])}"
                )

    if grafo.llamadas_transitivas:
        lineas.append(
            "Llamadas transitivas entre dependencias (posibles llamadas secundarias a simular):"
        )
        for origen, destino in grafo.llamadas_transitivas[:6]:
            lineas.append(f"- `{origen}` llama a `{destino}`")

    lineas.append(
        "REGLA: Usa las firmas y tipos anteriores para configurar retornos de mocks coherentes con el negocio."
    )
    lineas.append(
        "Nunca dejes dependencias de I/O, red o servicios externos sin simular."
    )
    return "\n".join(lineas)
