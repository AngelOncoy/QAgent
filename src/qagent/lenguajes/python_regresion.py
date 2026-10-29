"""Huellas y funciones de un archivo Python para la reutilización y la regresión (#168).

Es el código que antes vivía en ``orchestrator/regresion.py``, movido sin cambios:
la regresión es compartida y pide al adaptador la huella de cada objetivo y la línea
de cada función. Todo es estático, con tree-sitter (TA-16): nunca se importa ni se
ejecuta el código del usuario.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from qagent.analysis import arbol_ts, texto_ts


def huellas_de_archivo(fuente: str, relativa: str) -> dict[str, str] | None:
    """Huella de cada función pública y de cada ruta declarada del archivo.

    La huella sale del árbol de tree-sitter (``huella_de_definicion``, versión 2
    desde TA-16). None si el archivo tiene errores de sintaxis.
    """
    try:
        arbol = arbol_ts.parsear(fuente)
        arbol_ts.validar(arbol, fuente, relativa)
    except (SyntaxError, ValueError):
        return None
    resultado: dict[str, str] = {}
    for nodo in arbol_ts.sentencias(arbol.root_node):
        if not arbol_ts.es_funcion(nodo):
            continue
        funcion = arbol_ts.definicion(nodo)
        nombre = arbol_ts.nombre(funcion)
        huella = arbol_ts.huella_de_definicion(funcion)
        if not nombre.startswith("_"):
            resultado[nombre] = huella
        for camino_ruta in _rutas_declaradas(funcion):
            resultado[camino_ruta] = huella
    return resultado


def _rutas_declaradas(funcion: Any) -> list[str]:
    """``GET /ruta`` de cada decorador ``@objeto.get("/ruta")`` de la función."""
    rutas = []
    for decorador in arbol_ts.decoradores(funcion):
        llamada = arbol_ts.sin_envoltura(decorador)
        if llamada is None or llamada.type != "call":
            continue
        atributo = arbol_ts.sin_envoltura(llamada.child_by_field_name("function"))
        argumentos = llamada.child_by_field_name("arguments")
        posicionales = [
            a
            for a in (arbol_ts.nombrados(argumentos) if argumentos is not None else [])
            if a.type not in ("keyword_argument", "dictionary_splat")
        ]
        if atributo is None or atributo.type != "attribute" or not posicionales:
            continue
        metodo = arbol_ts.texto(atributo.child_by_field_name("attribute")).upper()
        if metodo not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            continue
        try:
            camino = texto_ts.literal(posicionales[0])
        except (ValueError, TypeError):
            continue
        if isinstance(camino, str):
            rutas.append(f"{metodo} {camino}")
    return rutas


def funciones_de_modulo(raiz: Path, modulo: str) -> list[dict[str, Any]]:
    """Línea del `def` de cada función de primer nivel del módulo (tree-sitter)."""
    try:
        fuente = (raiz / modulo).read_text(encoding="utf-8")
        arbol = arbol_ts.parsear(fuente)
        arbol_ts.validar(arbol, fuente, modulo)
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError):
        return []
    return [
        {
            "nombre": arbol_ts.nombre(nodo),
            "linea": arbol_ts.linea(arbol_ts.definicion(nodo)),
        }
        for nodo in arbol_ts.sentencias(arbol.root_node)
        if arbol_ts.es_funcion(nodo)
    ]
