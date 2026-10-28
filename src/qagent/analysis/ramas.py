"""Conteo de ramas (puntos de decisión) de una función, con tree-sitter (TA-16).

Vive aparte para que lo usen tanto :mod:`qagent.analysis.analyzer` (funciones) como
:mod:`qagent.analysis.rutas` (manejadores de endpoints, #74) sin importarse entre sí.
"""

from __future__ import annotations

from tree_sitter import Node

from qagent.analysis.arbol_ts import NODOS_DEFINICION, cuerpo, hijos

#: Un punto de decisión cada uno: ``if``, cada ``elif``, el ternario, los bucles, cada
#: ``except`` (también ``except*``) y cada ``case``.
_NODOS_RAMA = frozenset(
    {
        "if_statement",
        "elif_clause",
        "conditional_expression",
        "for_statement",
        "while_statement",
        "except_clause",
        "except_group_clause",
        "case_clause",
    }
)
_COMPRENSIONES = frozenset(
    {
        "list_comprehension",
        "set_comprehension",
        "dictionary_comprehension",
        "generator_expression",
    }
)


def contar_ramas(funcion: Node) -> int:
    """Cuenta los puntos de decisión propios de una función.

    Cada condición ``if`` de una comprensión también cuenta (la guarda ``if`` de un
    ``case`` no). No desciende a funciones ni clases anidadas: sus ramas no son de
    ``funcion``.
    """
    total = 0
    bloque = cuerpo(funcion)
    pendientes: list[Node] = [] if bloque is None else hijos(bloque)
    while pendientes:
        nodo = pendientes.pop()
        if nodo.type in NODOS_DEFINICION:
            continue
        if nodo.type in _NODOS_RAMA:
            total += 1
        elif nodo.type in _COMPRENSIONES:
            total += sum(1 for h in hijos(nodo) if h.type == "if_clause")
        pendientes.extend(hijos(nodo))
    return total
