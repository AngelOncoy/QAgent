"""Carga de gramáticas tree-sitter y utilidades de sintaxis multilenguaje (ADR-009).

Este módulo centraliza la inicialización de tree-sitter para los adaptadores
de lenguajes (JavaScript, TypeScript y Java). Cada gramática se carga
una sola vez en memoria mediante caché (functools.cache).
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING

import tree_sitter_java
import tree_sitter_javascript
import tree_sitter_typescript
from tree_sitter import Language, Parser

if TYPE_CHECKING:
    from tree_sitter import Node


@functools.cache
def cargar_gramatica(lenguaje: str) -> Language:
    """Carga y almacena en caché la gramática compilada de tree-sitter.

    Args:
        lenguaje: Identificador ("javascript", "typescript", "tsx" o "java").

    Returns:
        tree_sitter.Language correspondiente listo para usar en un Parser.

    Raises:
        ValueError: Si la gramática solicitada no está soportada.
    """
    clave = lenguaje.lower().strip()
    if clave in ("javascript", "js"):
        return Language(tree_sitter_javascript.language())
    if clave in ("typescript", "ts"):
        return Language(tree_sitter_typescript.language_typescript())
    if clave == "tsx":
        return Language(tree_sitter_typescript.language_tsx())
    if clave == "java":
        return Language(tree_sitter_java.language())

    raise ValueError(f"Gramática de tree-sitter no soportada: '{lenguaje}'.")


def obtener_parser(lenguaje: str) -> Parser:
    """Crea un Parser configurado con la gramática especificada."""
    return Parser(cargar_gramatica(lenguaje))


def extraer_errores_sintaxis(nodo: Node) -> list[str]:
    """Recorre el árbol de sintaxis y extrae los nodos con error o faltantes.

    Detecta nodos de tipo `ERROR` (sintaxis inválida o inesperada) y `MISSING`
    (elementos esperados por la gramática que faltan en el código).

    Returns:
        Lista de mensajes con la línea de cada error encontrado, sin duplicados.
    """
    errores: list[str] = []

    def _recorrer(n: Node) -> None:
        if n.is_error or n.type == "ERROR":
            linea = n.start_point.row + 1
            errores.append(f"línea {linea}: error de sintaxis")
            return
        if n.is_missing or n.type == "MISSING":
            linea = n.start_point.row + 1
            errores.append(f"línea {linea}: falta elemento sintáctico")
            return
        for hijo in n.children:
            _recorrer(hijo)

    _recorrer(nodo)
    return list(dict.fromkeys(errores))


def validar_sintaxis_js(codigo: str) -> list[str]:
    """Valida la sintaxis de código JavaScript (incluye .js, .mjs, .cjs y JSX).

    Returns:
        Lista vacía si el código es válido; lista con la línea de los errores si no lo es.
    """
    parser = obtener_parser("javascript")
    arbol = parser.parse(codigo.encode("utf-8"))
    if not arbol.root_node.has_error:
        return []
    errores = extraer_errores_sintaxis(arbol.root_node)
    if not errores:
        # Respaldo de seguridad si has_error es True pero el nodo está en la raíz
        linea = arbol.root_node.start_point.row + 1
        return [f"línea {linea}: error de sintaxis"]
    return errores


def validar_sintaxis_ts(codigo: str) -> list[str]:
    """Valida la sintaxis de código TypeScript (incluye .ts, .mts, .cts y .tsx).

    Prueba primero con la gramática de TypeScript estándar; si encuentra errores,
    prueba con la gramática TSX (para admitir sintaxis JSX en componentes .tsx).

    Returns:
        Lista vacía si el código es válido; lista con la línea de los errores si no lo es.
    """
    bytes_codigo = codigo.encode("utf-8")

    parser_ts = obtener_parser("typescript")
    arbol_ts = parser_ts.parse(bytes_codigo)
    if not arbol_ts.root_node.has_error:
        return []

    # Si TS estándar reportó error, probamos TSX (por si incluye elementos JSX)
    parser_tsx = obtener_parser("tsx")
    arbol_tsx = parser_tsx.parse(bytes_codigo)
    if not arbol_tsx.root_node.has_error:
        return []

    # Ambos tienen errores: devolvemos los errores encontrados
    errores_ts = extraer_errores_sintaxis(arbol_ts.root_node)
    errores_tsx = extraer_errores_sintaxis(arbol_tsx.root_node)

    errores = errores_ts if len(errores_ts) <= len(errores_tsx) else errores_tsx
    if not errores:
        linea = arbol_ts.root_node.start_point.row + 1
        return [f"línea {linea}: error de sintaxis"]
    return errores
