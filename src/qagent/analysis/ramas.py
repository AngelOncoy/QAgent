"""Conteo de ramas (puntos de decisión) de una función, solo con ``ast``.

Vive aparte para que lo usen tanto :mod:`qagent.analysis.analyzer` (funciones) como
:mod:`qagent.analysis.rutas` (manejadores de endpoints, #74) sin importarse entre sí.
"""

from __future__ import annotations

import ast

_NODOS_RAMA = (
    ast.If,
    ast.IfExp,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ExceptHandler,
    ast.match_case,
)
_NODOS_ANIDADOS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def contar_ramas(funcion: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Cuenta los puntos de decisión propios de una función.

    No desciende a funciones ni clases anidadas: sus ramas no son de ``funcion``.
    """
    total = 0
    pendientes: list[ast.AST] = list(funcion.body)
    while pendientes:
        nodo = pendientes.pop()
        if isinstance(nodo, _NODOS_ANIDADOS):
            continue
        if isinstance(nodo, _NODOS_RAMA):
            total += 1
        elif isinstance(nodo, ast.comprehension):
            total += len(nodo.ifs)
        pendientes.extend(ast.iter_child_nodes(nodo))
    return total
