"""Reglas de clasificación de salida y rango de objetivo para JavaScript/TypeScript (EP-11a).

Permite al Reviewer clasificar fallos de Vitest (entorno, error técnico de la prueba o
fallo de aserción) y determinar las líneas de la función probada para la cobertura.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from qagent.lenguajes.base import Clasificacion
from qagent.lenguajes.javascript_estructura import exportadas, gramatica_de
from qagent.lenguajes.treesitter import obtener_parser

_PATRONES_ENTORNO = (
    "econnrefused",
    "etimedout",
    "enotfound",
    "connection refused",
    "operationalerror",
)

_PATRONES_ERROR_TEST = (
    "syntaxerror",
    "failed to resolve import",
    "cannot find module",
    "failed to load url",
    "no test suite found",
    "no tests found",
    "cannot use import statement outside a module",
    "is not defined",
    "error: unhandled error",
    "failed to compile",
)


def clasificar_salida_vitest(
    salida: str, contrato: dict[str, Any], raiz: Path
) -> Clasificacion | None:
    """Clasifica la salida de Vitest según las reglas del Reviewer."""
    texto = salida.lower()

    # 1. Error de entorno (servicios caídos, sin conexión)
    for patron in _PATRONES_ENTORNO:
        if patron in texto:
            return Clasificacion(
                "entorno",
                f"Error de entorno en Node: {patron}",
            )

    # 2. Error técnico del test (sintaxis, import roto, etc.)
    for patron in _PATRONES_ERROR_TEST:
        if patron in texto:
            return Clasificacion(
                "error_test",
                f"Error técnico en la prueba: {patron}\n{salida[-2000:]}",
            )

    # 3. Fallo de aserción (AssertionError) -> bug_codigo
    if "assertionerror" in texto or "\nassert " in texto:
        return Clasificacion("fallo_asercion", salida)

    return None


def rango_de_objetivo_js(
    raiz: Path, modulo: str, nombre: str
) -> tuple[int, int] | None:
    """Devuelve primera y última línea del cuerpo de la función en modulo."""
    archivo = raiz / modulo
    try:
        fuente = archivo.read_text(encoding="utf-8-sig")
        arbol = obtener_parser(gramatica_de(modulo)).parse(fuente.encode("utf-8"))
        if arbol.root_node.has_error:
            return None
        for exp in exportadas(arbol.root_node):
            if exp.nombre == nombre:
                cuerpo = exp.nodo.child_by_field_name("body")
                if cuerpo is not None:
                    return (cuerpo.start_point.row + 1, cuerpo.end_point.row + 1)
                return (exp.nodo.start_point.row + 1, exp.nodo.end_point.row + 1)
        return None
    except (OSError, UnicodeError, ValueError):
        return None
