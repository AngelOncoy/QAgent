"""Analizador estático del proyecto — EN-02, con tree-sitter desde TA-16.

Extrae la estructura del código Python de un proyecto **sin ejecutarlo**:
solo lo parsea con tree-sitter (nunca ``import``, ``exec`` ni ``eval``), de acuerdo
con la regla de AGENTS.md y ADR-009. Alimenta al Planner y a las historias HU-04,
HU-06, HU-16 y HU-24. La estructura es la misma que daba el analizador anterior
con ``ast``: tipos, valores por defecto y firmas se escriben como ``ast.unparse``
(ver :mod:`qagent.analysis.texto_ts`).

Qué analiza:
    * Módulos ``.py`` del proyecto, con rutas relativas en formato POSIX.
    * Funciones públicas definidas a nivel de módulo (``def`` y ``async def``).
      Las funciones privadas (prefijo ``_``) se ignoran. Los métodos de clases
      y las funciones anidadas quedan fuera de este alcance.

    * Endpoints FastAPI, modelos Pydantic y el mapa de llamadas ``llama_a``
      (EN-14, en :mod:`qagent.analysis.rutas`). Las funciones que atienden una
      ruta salen de ``funciones`` y aparecen en ``endpoints``, para no probarlas
      dos veces.

Qué ignora:
    * Carpetas ``tests/``, ``.qagent/`` y cualquier carpeta que empiece con
      punto (``.git``, ``.venv``, ``.idea``...), además de ``__pycache__``,
      ``venv``, ``node_modules``, ``site-packages``, ``mutants`` y ``*.egg-info``.

Definiciones:
    * **Ramas** de una función: cantidad de puntos de decisión propios
      (``if``/``elif``, expresión ternaria, ``for``, ``while``, cada ``except``,
      cada ``case`` de ``match`` y cada condición ``if`` de una comprensión).
      No se cuentan las ramas de funciones o clases anidadas.
    * **Tipada**: todos los parámetros y el retorno tienen anotación.
    * **Huella** (SHA-256) de un módulo: hash del texto fuente completo (código
      y docstrings) con saltos de línea normalizados a ``\\n``. Si cambia el
      código o su documentación, cambia la huella (HU-24).

Los archivos que no se pueden analizar (error de sintaxis, codificación
inválida, etc.) se reportan en ``errores`` y **no detienen** el análisis.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tokenize
from pathlib import Path
from typing import Any

from tree_sitter import Node, Tree

from qagent.analysis import texto_ts
from qagent.analysis.arbol_ts import (
    KWARGS,
    VARARGS,
    cuerpo,
    definicion,
    es_async,
    es_funcion,
    linea,
    nombre,
    parametros,
    parsear,
    validar,
)
from qagent.analysis.ramas import contar_ramas
from qagent.analysis.rutas import analizar_rutas, sentencias_modulo

DIRECTORIOS_IGNORADOS = frozenset(
    {
        "tests",
        "__pycache__",
        "venv",
        "node_modules",
        "site-packages",
        "mutants",
        "multilenguaje",
        "dependencias",
        "graphify-out",
    }
)

_ERRORES_LECTURA = (SyntaxError, ValueError, RecursionError, OSError)


def _es_ignorado(nombre_directorio: str) -> bool:
    """Indica si una carpeta debe omitirse del análisis."""
    return (
        nombre_directorio.startswith(".")
        or nombre_directorio in DIRECTORIOS_IGNORADOS
        or nombre_directorio.endswith(".egg-info")
    )


def listar_archivos_py(raiz: Path) -> list[Path]:
    """Lista los ``.py`` del proyecto, ordenados por ruta relativa.

    Es el único criterio de qué archivos se analizan: poda las carpetas
    ignoradas y no entra en carpetas que son enlaces simbólicos. Lo reutiliza
    la HU-01 para validar una carpeta antes de abrirla.
    """
    encontrados: list[Path] = []
    for directorio, subdirectorios, archivos in os.walk(raiz):
        subdirectorios[:] = [d for d in subdirectorios if not _es_ignorado(d)]
        encontrados.extend(Path(directorio) / a for a in archivos if a.endswith(".py"))
    return sorted(encontrados, key=lambda p: p.relative_to(raiz).as_posix())


def _extraer_parametros(funcion: Node) -> list[dict[str, Any]]:
    """Extrae nombre, tipo y valor por defecto de cada parámetro, en orden."""
    resultado = []
    for parametro in parametros(funcion.child_by_field_name("parameters")):
        prefijo = {VARARGS: "*", KWARGS: "**"}.get(parametro.clase, "")
        resultado.append(
            {
                "nombre": prefijo + parametro.nombre,
                "tipo": texto_ts.expresion(parametro.tipo),
                "por_defecto": texto_ts.expresion(parametro.defecto),
            }
        )
    return resultado


def _extraer_funcion(nodo: Node) -> dict[str, Any]:
    """Convierte una ``function_definition`` en su descripción JSON."""
    funcion = definicion(nodo)
    parametros_funcion = _extraer_parametros(funcion)
    retorno = texto_ts.expresion(funcion.child_by_field_name("return_type"))
    docstring = (texto_ts.docstring(cuerpo(funcion)) or "").strip() or None
    return {
        "nombre": nombre(funcion),
        "linea": linea(funcion),
        "firma": texto_ts.firma(funcion),
        "parametros": parametros_funcion,
        "retorno": retorno,
        "docstring": docstring,
        "ramas": contar_ramas(funcion),
        "tipada": retorno is not None and all(p["tipo"] for p in parametros_funcion),
        "es_async": es_async(funcion),
    }


def _funciones_publicas(arbol: Tree) -> list[dict[str, Any]]:
    funciones = []
    vistos: set[str] = set()
    for nodo in sentencias_modulo(arbol.root_node):
        if not es_funcion(nodo):
            continue
        nombre_funcion = nombre(nodo)
        if not nombre_funcion.startswith("_") and nombre_funcion not in vistos:
            vistos.add(nombre_funcion)
            funciones.append(_extraer_funcion(nodo))
    return funciones


def calcular_huella(fuente: str) -> str:
    """SHA-256 (hex) del texto fuente de un módulo, con saltos de línea ``\\n``."""
    normalizado = fuente.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalizado.encode("utf-8")).hexdigest()


def _analizar_modulo(ruta: Path, relativa: str) -> tuple[dict[str, Any], Tree]:
    """Analiza un archivo. Lanza las excepciones de lectura o de sintaxis."""
    with tokenize.open(ruta) as archivo:  # respeta BOM y cookie de codificación
        fuente = archivo.read()
    arbol = parsear(fuente)
    validar(arbol, fuente, relativa)
    modulo = {
        "ruta": relativa,
        "huella": calcular_huella(fuente),
        "funciones": _funciones_publicas(arbol),
    }
    return modulo, arbol


def _agregar_rutas(modulos: list[dict[str, Any]], arboles: dict[str, Tree]) -> None:
    """Agrega endpoints, modelos y ``llama_a`` (EN-14) a cada módulo analizado."""
    rutas = analizar_rutas(arboles)
    for modulo in modulos:
        info = rutas[modulo["ruta"]]
        manejadores = set(info["manejadores"])
        modulo["funciones"] = [
            {**funcion, "llama_a": info["llama_a"].get(funcion["nombre"], [])}
            for funcion in modulo["funciones"]
            if funcion["nombre"] not in manejadores
        ]
        modulo["endpoints"] = info["endpoints"]
        modulo["modelos"] = info["modelos"]


def _error(relativa: str, causa: Exception) -> dict[str, Any]:
    """Describe por qué un archivo no se pudo analizar."""
    es_sintaxis = isinstance(causa, SyntaxError)
    return {
        "ruta": relativa,
        "tipo": type(causa).__name__,
        "linea": causa.lineno if es_sintaxis else None,
        "mensaje": causa.msg if es_sintaxis else str(causa),
    }


def _conteo(cantidad: int, total: int) -> dict[str, Any]:
    porcentaje = round(cantidad / total * 100, 1) if total else 0.0
    return {"cantidad": cantidad, "porcentaje": porcentaje}


def _resumen(
    modulos: list[dict[str, Any]], errores: list[dict[str, Any]]
) -> dict[str, Any]:
    funciones = [f for m in modulos for f in m["funciones"]]
    total = len(funciones)
    sin_docstring = sum(1 for f in funciones if f["docstring"] is None)
    sin_tipos = sum(1 for f in funciones if not f["tipada"])
    con_alguna = sum(1 for f in funciones if f["docstring"] is None or not f["tipada"])
    return {
        "total_modulos": len(modulos),
        "total_funciones_publicas": total,
        "total_endpoints": sum(len(m.get("endpoints", [])) for m in modulos),
        "total_errores": len(errores),
        "inconsistencias": {
            "sin_docstring": _conteo(sin_docstring, total),
            "sin_tipos": _conteo(sin_tipos, total),
            "con_alguna": _conteo(con_alguna, total),
        },
    }


def analizar_proyecto(raiz: str | os.PathLike[str]) -> dict[str, Any]:
    """Analiza estáticamente todos los módulos Python bajo ``raiz``.

    Devuelve un diccionario serializable a JSON con tres claves:

    * ``modulos``: por módulo, ``ruta``, ``huella``, ``funciones`` públicas
      (``nombre``, ``linea``, ``firma``, ``parametros``, ``retorno``,
      ``docstring``, ``ramas``, ``tipada``, ``es_async``, ``llama_a``),
      ``endpoints`` FastAPI y ``modelos`` Pydantic (EN-14, ver
      :func:`qagent.analysis.rutas.analizar_rutas`).
    * ``errores``: archivos no analizables (``ruta``, ``tipo``, ``linea``,
      ``mensaje``). No detienen el análisis del resto.
    * ``resumen``: totales de módulos, funciones públicas, endpoints y errores, más las
      inconsistencias (sin docstring, sin tipos, con alguna de las dos) con su
      porcentaje sobre el total de funciones públicas.

    Raises:
        NotADirectoryError: si ``raiz`` no es una carpeta existente.
    """
    carpeta = Path(raiz)
    if not carpeta.is_dir():
        raise NotADirectoryError(f"No es una carpeta: {carpeta}")

    modulos: list[dict[str, Any]] = []
    arboles: dict[str, Tree] = {}
    errores: list[dict[str, Any]] = []
    for ruta in listar_archivos_py(carpeta):
        relativa = ruta.relative_to(carpeta).as_posix()
        try:
            modulo, arboles[relativa] = _analizar_modulo(ruta, relativa)
            modulos.append(modulo)
        except _ERRORES_LECTURA as causa:
            errores.append(_error(relativa, causa))
    _agregar_rutas(modulos, arboles)

    return {
        "modulos": modulos,
        "errores": errores,
        "resumen": _resumen(modulos, errores),
    }


def analizar_proyecto_json(raiz: str | os.PathLike[str], indent: int | None = 2) -> str:
    """Igual que :func:`analizar_proyecto`, pero devuelve el JSON como texto."""
    return json.dumps(analizar_proyecto(raiz), ensure_ascii=False, indent=indent)


def main(argumentos: list[str] | None = None) -> int:
    """Punto de entrada de línea de comandos: imprime el JSON del análisis."""
    argumentos = sys.argv[1:] if argumentos is None else argumentos
    if len(argumentos) != 1:
        print("Uso: python -m qagent.analysis <carpeta-del-proyecto>", file=sys.stderr)
        return 2
    try:
        texto = analizar_proyecto_json(argumentos[0])
    except NotADirectoryError as error:
        print(error, file=sys.stderr)
        return 1
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # consolas de Windows (cp1252)
    print(texto)
    return 0
