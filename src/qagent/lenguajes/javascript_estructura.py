"""Funciones exportadas, JSDoc y decisiones de JavaScript y TypeScript (#176).

Todo es estático con tree-sitter (ADR-009): nunca se importa, transpila ni ejecuta
el código del usuario. Reconoce las exportaciones ESM (``export function``,
``export const f = () =>``, ``export default``, ``export { a as b }``) y CommonJS
(``module.exports = {…}``, ``module.exports.f =``, ``exports.f =``), y los métodos
públicos de las clases exportadas, que se nombran ``Clase.metodo`` como en Java.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from tree_sitter import Node

#: Un punto de decisión cada uno; ``case`` y los cortocircuitos se cuentan aparte.
_DECISIONES = frozenset(
    {
        "if_statement",
        "ternary_expression",
        "for_statement",
        "for_in_statement",
        "while_statement",
        "do_statement",
        "catch_clause",
    }
)
#: ``&&``, ``||`` y ``??`` deciden si se evalúa el operando derecho.
_CORTOCIRCUITOS = frozenset({b"&&", b"||", b"??"})
#: Funciones y clases anidadas: sus decisiones no son de la función exterior.
_AMBITOS = frozenset(
    {
        "function_declaration",
        "generator_function_declaration",
        "function_expression",
        "generator_function",
        "arrow_function",
        "method_definition",
        "class_declaration",
        "abstract_class_declaration",
        "class",
    }
)
_FUNCIONES = frozenset(
    {
        "function_declaration",
        "generator_function_declaration",
        "function_expression",
        "generator_function",
        "arrow_function",
    }
)
_CLASES = frozenset({"class_declaration", "abstract_class_declaration", "class"})


@dataclass(frozen=True)
class Exportada:
    """Una función exportada: su nodo, el nodo que lleva el JSDoc y cómo se exporta."""

    nombre: str
    nodo: Node
    ancla: Node
    exportacion: str
    clase: str | None = None


def gramatica_de(ruta: str) -> str:
    """Gramática de tree-sitter de un archivo: ``tsx``, ``typescript`` o ``javascript``."""
    minuscula = ruta.lower()
    if minuscula.endswith(".tsx"):
        return "tsx"
    if minuscula.endswith((".ts", ".mts", ".cts")):
        return "typescript"
    return "javascript"


def _texto(nodo: Node | None) -> str | None:
    return nodo.text.decode("utf-8") if nodo is not None else None


# --- JSDoc ---------------------------------------------------------------------------


def jsdoc_de(ancla: Node) -> tuple[str, int] | None:
    """Comentario ``/** … */`` inmediatamente anterior a ``ancla`` y su primera línea.

    Solo vale el comentario pegado a la declaración (a lo sumo una línea en blanco
    entre ambos); nunca se infiere desde otro lugar del archivo.
    """
    anterior = ancla.prev_sibling
    texto = _texto(anterior)
    if (
        anterior is None
        or anterior.type != "comment"
        or not texto.startswith("/**")
        or ancla.start_point.row - anterior.end_point.row > 2
    ):
        return None
    return texto, anterior.start_point.row + 1


def _tipo_y_resto(contenido: str) -> tuple[str | None, str]:
    """Separa ``{Tipo} resto`` respetando llaves anidadas; sin llaves no hay tipo."""
    if not contenido.startswith("{"):
        return None, contenido
    profundidad = 0
    for indice, caracter in enumerate(contenido):
        profundidad += {"{": 1, "}": -1}.get(caracter, 0)
        if profundidad == 0:
            return contenido[1:indice].strip(), contenido[indice + 1 :].strip()
    return None, contenido


def desglosar_jsdoc(texto: str | None, linea: int = 1) -> dict[str, Any] | None:
    """Separa descripción y etiquetas del JSDoc sin interpretar su significado.

    ``@param {T} [nombre=defecto] descripción``, ``@returns``/``@return``,
    ``@throws``/``@exception`` y ``@example`` (multilínea) se estructuran; las demás
    etiquetas se guardan por nombre. Cada etiqueta conserva su línea en el archivo
    (``linea`` es la del ``/**``) para citarla como evidencia. None si no hay JSDoc.
    """
    if texto is None:
        return None
    limpio = texto.removeprefix("/**").removesuffix("*/")
    bloques: list[tuple[str | None, int, list[str]]] = [(None, linea, [])]
    for desplazamiento, fila in enumerate(limpio.splitlines()):
        fila = re.sub(r"^\s*\* ?", "", fila).rstrip()
        etiqueta = re.match(r"^\s*@(\w+)\s*(.*)$", fila)
        if etiqueta:
            bloques.append((etiqueta[1], linea + desplazamiento, [etiqueta[2]]))
        else:
            bloques[-1][2].append(fila)
    resultado: dict[str, Any] = {
        "descripcion": "\n".join(bloques[0][2]).strip(),
        "parametros": {},
        "retorno": None,
        "excepciones": [],
        "ejemplos": [],
        "otras_etiquetas": {},
    }
    for etiqueta, numero, lineas in bloques[1:]:
        while len(lineas) > 1 and not lineas[-1].strip():
            lineas = lineas[:-1]
        while len(lineas) > 1 and not lineas[0].strip():  # @example⏎llamada
            lineas, numero = lineas[1:], numero + 1
        fin = numero + len(lineas) - 1
        contenido = "\n".join(lineas).strip()
        if etiqueta in {"param", "arg", "argument"}:
            tipo, resto = _tipo_y_resto(contenido)
            partes = resto.split(maxsplit=1)
            if not partes:
                continue
            nombre, defecto = partes[0], None
            if nombre.startswith("[") and nombre.endswith("]"):
                nombre, _, defecto = nombre[1:-1].partition("=")
                defecto = defecto or None
            resultado["parametros"][nombre] = {
                "tipo": tipo,
                "descripcion": re.sub(r"^-\s*", "", partes[1])
                if len(partes) > 1
                else "",
                "por_defecto": defecto,
            }
        elif etiqueta in {"returns", "return"}:
            tipo, resto = _tipo_y_resto(contenido)
            resultado["retorno"] = {"tipo": tipo, "descripcion": resto, "linea": numero}
        elif etiqueta in {"throws", "exception"}:
            tipo, resto = _tipo_y_resto(contenido)
            resultado["excepciones"].append(
                {"tipo": tipo, "descripcion": resto, "linea": numero}
            )
        elif etiqueta == "example":
            if contenido:
                resultado["ejemplos"].append(
                    {"texto": contenido, "linea": numero, "linea_fin": fin}
                )
        else:
            resultado["otras_etiquetas"].setdefault(etiqueta, []).append(contenido)
    return resultado


# --- Decisiones ----------------------------------------------------------------------


def nodos_del_cuerpo(funcion: Node) -> Iterator[Node]:
    """Visita el cuerpo propio de ``funcion``, sin entrar en funciones ni clases anidadas.

    El cuerpo de una flecha puede ser una expresión (``x => x ? 1 : 2``): también se
    recorre. El recorrido es iterativo y nunca evalúa el código.
    """
    cuerpo = funcion.child_by_field_name("body")
    pendientes = [cuerpo] if cuerpo is not None else []
    while pendientes:
        nodo = pendientes.pop()
        if nodo.type in _AMBITOS:
            continue
        yield nodo
        pendientes.extend(reversed(nodo.named_children))


def contar_ramas(funcion: Node) -> int:
    """Cuenta ``if``, ternarios, bucles, ``catch``, cada ``case`` y ``&&``/``||``/``??``.

    ``else if`` cuenta como otro ``if``; ``default`` no añade una decisión. Es el
    criterio de Java (#181): una función con al menos una decisión es crítica.
    """
    total = 0
    for nodo in nodos_del_cuerpo(funcion):
        if nodo.type in _DECISIONES or nodo.type == "switch_case":
            total += 1
        elif nodo.type == "binary_expression":
            operador = nodo.child_by_field_name("operator")
            total += operador is not None and operador.text in _CORTOCIRCUITOS
    return total


# --- Parámetros y firma --------------------------------------------------------------


def _sin_dos_puntos(anotacion: Node | None) -> str | None:
    texto = _texto(anotacion)
    return texto.removeprefix(":").strip() if texto is not None else None


def _parametros_de(funcion: Node) -> list[Node]:
    unico = funcion.child_by_field_name("parameter")  # x => x
    if unico is not None:
        return [unico]
    lista = funcion.child_by_field_name("parameters")
    if lista is None:
        return []
    return [h for h in lista.named_children if h.type != "comment"]


def parametros(funcion: Node) -> list[dict[str, Any]]:
    """Nombre, tipo de TypeScript y valor por defecto de cada parámetro, en orden.

    El resto lleva el prefijo ``...``; un parámetro desestructurado conserva su patrón
    literal (``{ a, b }``). Un parámetro ``x?`` de TypeScript queda ``opcional``.
    """
    resultado = []
    for nodo in _parametros_de(funcion):
        tipo = defecto = None
        opcional = nodo.type == "optional_parameter"
        patron = nodo
        if nodo.type in {"required_parameter", "optional_parameter"}:
            patron = nodo.child_by_field_name("pattern")
            tipo = _sin_dos_puntos(nodo.child_by_field_name("type"))
            defecto = _texto(nodo.child_by_field_name("value"))
        if patron is not None and patron.type == "assignment_pattern":
            defecto = _texto(patron.child_by_field_name("right"))
            patron = patron.child_by_field_name("left")
        nombre = _texto(patron) or ""
        if patron is not None and patron.type == "rest_pattern":
            nombre = "..." + (_texto(patron.named_children[0]) or "")
        resultado.append(
            {
                "nombre": nombre,
                "tipo": tipo,
                "por_defecto": defecto,
                "opcional": opcional or defecto is not None,
            }
        )
    return resultado


def es_async(funcion: Node) -> bool:
    """Si la función o el método se declaró ``async``."""
    return any(h.type == "async" for h in funcion.children)


def firma(nombre: str, funcion: Node) -> str:
    """``[async ]nombre(parámetros)[: Retorno]`` tal como están escritos en la fuente."""
    lista = funcion.child_by_field_name("parameters")
    texto_parametros = (
        _texto(lista)
        if lista is not None
        else f"({_texto(funcion.child_by_field_name('parameter')) or ''})"
    )
    retorno = _texto(funcion.child_by_field_name("return_type")) or ""
    prefijo = "async " if es_async(funcion) else ""
    return f"{prefijo}{nombre}{texto_parametros}{retorno}"


# --- Exportaciones -------------------------------------------------------------------


def declaraciones_locales(raiz: Node) -> dict[str, tuple[Node, Node]]:
    """Funciones y clases de primer nivel por nombre: (nodo, ancla del JSDoc)."""
    locales: dict[str, tuple[Node, Node]] = {}
    for sentencia in raiz.named_children:
        declaracion = sentencia
        if sentencia.type == "export_statement":
            declaracion = sentencia.child_by_field_name("declaration")
            if declaracion is None:
                continue
        if declaracion.type in _FUNCIONES | _CLASES:
            nombre = _texto(declaracion.child_by_field_name("name"))
            if nombre:
                locales.setdefault(nombre, (declaracion, sentencia))
        elif declaracion.type in {"lexical_declaration", "variable_declaration"}:
            for declarador in declaracion.named_children:
                if declarador.type != "variable_declarator":
                    continue
                valor = declarador.child_by_field_name("value")
                nombre = _texto(declarador.child_by_field_name("name"))
                if valor is not None and nombre and valor.type in _FUNCIONES | _CLASES:
                    locales.setdefault(nombre, (valor, sentencia))
    return locales


def _es_modulo_exports(nodo: Node | None) -> bool:
    """``module.exports``."""
    return (
        nodo is not None
        and nodo.type == "member_expression"
        and _texto(nodo.child_by_field_name("object")) == "module"
        and _texto(nodo.child_by_field_name("property")) == "exports"
    )


def _destino_commonjs(izquierda: Node | None) -> str | None:
    """Nombre exportado por ``exports.f =`` o ``module.exports.f =``; None si no lo es."""
    if izquierda is None or izquierda.type != "member_expression":
        return None
    objeto = izquierda.child_by_field_name("object")
    if _texto(objeto) == "exports" or _es_modulo_exports(objeto):
        return _texto(izquierda.child_by_field_name("property"))
    return None


def _metodos(clase: Node, nombre_clase: str, exportacion: str) -> list[Exportada]:
    """Métodos públicos con cuerpo: sin ``#privados``, ``private``/``protected``,
    ``constructor``, getters ni setters (no se invocan como funciones)."""
    cuerpo = clase.child_by_field_name("body")
    if cuerpo is None:
        return []
    metodos = []
    for metodo in cuerpo.named_children:
        if metodo.type != "method_definition":
            continue
        nombre = metodo.child_by_field_name("name")
        tokens = {h.type for h in metodo.children}
        accesibilidad = next(
            (_texto(h) for h in metodo.children if h.type == "accessibility_modifier"),
            "public",
        )
        if (
            nombre is None
            or nombre.type != "property_identifier"
            or _texto(nombre) == "constructor"
            or accesibilidad != "public"
            or tokens & {"get", "set"}
        ):
            continue
        metodos.append(
            Exportada(
                f"{nombre_clase}.{_texto(nombre)}",
                metodo,
                metodo,
                exportacion,
                nombre_clase,
            )
        )
    return metodos


def exportadas(raiz: Node) -> list[Exportada]:
    """Funciones y métodos exportados del módulo, en orden de aparición y sin repetir.

    ``exportacion`` vale ``nombrada`` o ``default`` (ESM) y ``commonjs`` o
    ``commonjs_modulo`` (``module.exports = f``): la parte de generación lo necesita
    para escribir el ``import``. Las reexportaciones (``export … from``) se omiten:
    la función se analiza en su propio archivo.
    """
    locales = declaraciones_locales(raiz)
    encontradas: list[Exportada] = []

    def agregar(nombre: str, nodo: Node, ancla: Node, exportacion: str) -> None:
        if nodo.type in _CLASES:
            encontradas.extend(_metodos(nodo, nombre, exportacion))
        elif nodo.type in _FUNCIONES or nodo.type == "method_definition":
            encontradas.append(Exportada(nombre, nodo, ancla, exportacion))

    def agregar_local(publico: str, local: str, exportacion: str) -> None:
        if local in locales:
            nodo, ancla = locales[local]
            agregar(publico, nodo, ancla, exportacion)

    for sentencia in raiz.named_children:
        if sentencia.type == "export_statement":
            _exportacion_esm(sentencia, locales, agregar, agregar_local)
        elif sentencia.type == "expression_statement":
            asignacion = (
                sentencia.named_children[0] if sentencia.named_children else None
            )
            if asignacion is None or asignacion.type != "assignment_expression":
                continue
            _exportacion_commonjs(sentencia, asignacion, agregar, agregar_local)

    unicas: dict[str, Exportada] = {}
    for exportada in encontradas:
        unicas.setdefault(exportada.nombre, exportada)
    return list(unicas.values())


def _exportacion_esm(sentencia, locales, agregar, agregar_local) -> None:
    if sentencia.child_by_field_name("source") is not None:
        return  # export … from './otro'
    por_defecto = any(h.type == "default" for h in sentencia.children)
    exportacion = "default" if por_defecto else "nombrada"
    declaracion = sentencia.child_by_field_name("declaration")
    valor = sentencia.child_by_field_name("value")
    if declaracion is not None:
        if declaracion.type in {"lexical_declaration", "variable_declaration"}:
            for declarador in declaracion.named_children:
                nombre = _texto(declarador.child_by_field_name("name"))
                if nombre in locales:
                    agregar_local(nombre, nombre, exportacion)
            return
        nombre = _texto(declaracion.child_by_field_name("name")) or "default"
        agregar(nombre, declaracion, sentencia, exportacion)
    elif valor is not None:
        if valor.type == "identifier":
            agregar_local(_texto(valor), _texto(valor), "default")
        else:
            nombre = _texto(valor.child_by_field_name("name")) or "default"
            agregar(nombre, valor, sentencia, "default")
    else:
        for clausula in sentencia.named_children:
            if clausula.type != "export_clause":
                continue
            for especificador in clausula.named_children:
                local = _texto(especificador.child_by_field_name("name"))
                alias = _texto(especificador.child_by_field_name("alias")) or local
                agregar_local(
                    alias, local, "default" if alias == "default" else "nombrada"
                )


def _exportacion_commonjs(sentencia, asignacion, agregar, agregar_local) -> None:
    izquierda = asignacion.child_by_field_name("left")
    derecha = asignacion.child_by_field_name("right")
    if derecha is None:
        return
    destino = _destino_commonjs(izquierda)
    if destino is not None:
        if derecha.type == "identifier":
            agregar_local(destino, _texto(derecha), "commonjs")
        else:
            agregar(destino, derecha, sentencia, "commonjs")
        return
    if not _es_modulo_exports(izquierda):
        return
    if derecha.type == "identifier":
        agregar_local(_texto(derecha), _texto(derecha), "commonjs_modulo")
    elif derecha.type == "object":
        for propiedad in derecha.named_children:
            if propiedad.type == "shorthand_property_identifier":
                agregar_local(_texto(propiedad), _texto(propiedad), "commonjs")
            elif propiedad.type == "pair":
                clave = _texto(propiedad.child_by_field_name("key"))
                valor = propiedad.child_by_field_name("value")
                if valor is None or not clave:
                    continue
                if valor.type == "identifier":
                    agregar_local(clave, _texto(valor), "commonjs")
                else:
                    agregar(clave, valor, propiedad, "commonjs")
            elif propiedad.type == "method_definition":
                nombre = _texto(propiedad.child_by_field_name("name"))
                if nombre:
                    agregar(nombre, propiedad, propiedad, "commonjs")
    else:
        nombre = _texto(derecha.child_by_field_name("name")) or "default"
        agregar(nombre, derecha, sentencia, "commonjs_modulo")


# --- Descripción de una función ------------------------------------------------------


def describir(exportada: Exportada) -> dict[str, Any]:
    """Descripción JSON de una función exportada, con las claves de Python y Java.

    ``tipada`` exige el tipo de cada parámetro y del retorno, sea de TypeScript o
    de JSDoc (``@param {T}``, ``@returns {T}``), que en JavaScript son los únicos.
    """
    nodo = exportada.nodo
    comentario = jsdoc_de(exportada.ancla)
    docstring = comentario[0] if comentario else None
    jsdoc = desglosar_jsdoc(*comentario) if comentario else None
    lista = parametros(nodo)
    retorno = _sin_dos_puntos(nodo.child_by_field_name("return_type"))
    tipos_doc = (jsdoc or {}).get("parametros", {})
    retorno_doc = ((jsdoc or {}).get("retorno") or {}).get("tipo")
    tipada = (retorno is not None or retorno_doc is not None) and all(
        p["tipo"] or (tipos_doc.get(p["nombre"].lstrip(".")) or {}).get("tipo")
        for p in lista
    )
    nombre_corto = exportada.nombre.rsplit(".", 1)[-1]
    descripcion = {
        "nombre": exportada.nombre,
        "linea": nodo.start_point.row + 1,
        "firma": firma(nombre_corto, nodo),
        "parametros": lista,
        "retorno": retorno,
        "docstring": docstring,
        "jsdoc": jsdoc,
        "ramas": contar_ramas(nodo),
        "tipada": tipada,
        "es_async": es_async(nodo),
        "exportacion": exportada.exportacion,
    }
    if exportada.clase is not None:
        descripcion["clase"] = exportada.clase
        descripcion["es_static"] = any(h.type == "static" for h in nodo.children)
    return descripcion


def extraer_funciones(raiz: Node) -> list[dict[str, Any]]:
    """Describe cada función o método exportado de un árbol de tree-sitter."""
    return [describir(e) for e in exportadas(raiz)]
