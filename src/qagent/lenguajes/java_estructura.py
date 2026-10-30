"""Javadoc y decisiones Java, obtenidos estáticamente con tree-sitter (#181)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from tree_sitter import Node

_DECISIONES = frozenset(
    {
        "if_statement",
        "ternary_expression",
        "for_statement",
        "enhanced_for_statement",
        "while_statement",
        "do_statement",
        "catch_clause",
    }
)
_AMBITOS = frozenset(
    {
        "class_declaration",
        "interface_declaration",
        "enum_declaration",
        "record_declaration",
        "class_body",
        "lambda_expression",
    }
)


def desglosar_javadoc(texto: str | None) -> dict[str, Any] | None:
    """Separa descripción y etiquetas sin interpretar ni inventar su significado.

    Conserva descripciones multilínea, parámetros de tipo como <T>, @return,
    @throws y su alias @exception. Las demás etiquetas se guardan por nombre.
    None significa que no existe Javadoc; un comentario vacío sigue siendo vacío.
    El texto literal original se mantiene en docstring, fuera de esta función.
    """
    if texto is None:
        return None
    limpio = texto.removeprefix("/**").removesuffix("*/")
    bloques: list[tuple[str | None, list[str]]] = [(None, [])]
    for linea in limpio.splitlines():
        linea = re.sub(r"^\s*\* ?", "", linea).strip()
        etiqueta = re.match(r"^@(\w+)\s*(.*)$", linea)
        if etiqueta:
            bloques.append((etiqueta[1], [etiqueta[2]]))
        else:
            bloques[-1][1].append(linea)
    resultado: dict[str, Any] = {
        "descripcion": "\n".join(bloques[0][1]).strip(),
        "parametros": {},
        "retorno": None,
        "excepciones": [],
        "otras_etiquetas": {},
    }
    for etiqueta, lineas in bloques[1:]:
        contenido = "\n".join(lineas).strip()
        if etiqueta == "param":
            partes = contenido.split(maxsplit=1)
            if partes:
                resultado["parametros"][partes[0]] = (
                    partes[1] if len(partes) > 1 else ""
                )
        elif etiqueta == "return":
            resultado["retorno"] = contenido
        elif etiqueta in {"throws", "exception"}:
            partes = contenido.split(maxsplit=1)
            if partes:
                resultado["excepciones"].append(
                    {
                        "tipo": partes[0],
                        "descripcion": partes[1] if len(partes) > 1 else "",
                    }
                )
        else:
            resultado["otras_etiquetas"].setdefault(etiqueta, []).append(contenido)
    return resultado


def nodos_del_cuerpo(declaracion: Node) -> Iterator[Node]:
    """Visita el cuerpo propio, excluyendo clases, objetos anónimos y lambdas.

    Las decisiones y llamadas de esos ámbitos no pertenecen al método exterior.
    El recorrido es iterativo y nunca evalúa el código Java.
    """
    cuerpo = declaracion.child_by_field_name("body")
    pendientes = list(reversed(cuerpo.named_children)) if cuerpo is not None else []
    while pendientes:
        nodo = pendientes.pop()
        if nodo.type in _AMBITOS:
            continue
        yield nodo
        pendientes.extend(reversed(nodo.named_children))


def contar_decisiones(declaracion: Node) -> int:
    """Cuenta if, ternarios, bucles, catch, case y operadores &&/|| del cuerpo.

    Cada etiqueta case cuenta una vez; default no añade otra decisión. Una
    secuencia case A, B cuenta como una etiqueta. No es cobertura ni ejecución.
    Los cortocircuitos cuentan porque deciden si se evalúa el siguiente operando.
    """
    total = 0
    for nodo in nodos_del_cuerpo(declaracion):
        if nodo.type in _DECISIONES:
            total += 1
        elif nodo.type == "switch_label":
            total += any(h.type == "case" for h in nodo.children)
        elif nodo.type == "binary_expression":
            operador = nodo.child_by_field_name("operator")
            total += operador is not None and operador.text in {b"&&", b"||"}
    return total
