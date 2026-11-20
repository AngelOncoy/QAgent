"""Prueba estática conservadora de la sobrecarga invocada por JUnit (#299)."""

from __future__ import annotations

import re
from typing import Any

from tree_sitter import Node

from qagent.lenguajes.java_aserciones import NO_LITERAL, literal, resolver, texto
from qagent.lenguajes.java_firmas import tipo_borrado


def entradas_exactas(
    argumentos: list[Node], alias: dict[str, Node], identidad: str, esperados: list[Any]
) -> bool:
    """Exige tipos exactos sin inferir promociones, boxing ni despacho dinámico.

    Un null admite exclusivamente un cast al tipo declarado. No admite casts
    numéricos, helpers, arrays de tamaño calculado ni conversiones de entradas.
    Varargs se invoca en forma fija con un único array explícito.
    """
    parametros = identidad.partition("(")[2][:-1]
    tipos = parametros.split(",") if parametros else []
    if len(argumentos) != len(tipos) or len(esperados) != len(tipos):
        return False
    for argumento, tipo, esperado in zip(argumentos, tipos, esperados):
        original = argumento
        vistos = set()
        while original.type == "parenthesized_expression":
            original = original.named_children[0]
        while original.type == "identifier" and texto(original) in alias:
            nombre = texto(original)
            if nombre in vistos:
                return False
            vistos.add(nombre)
            original = alias[nombre]
            declarador = original.parent
            declaracion = declarador.parent if declarador is not None else None
            if declaracion is None or declaracion.type != "local_variable_declaration":
                return False
            declarado = tipo_borrado(texto(declaracion.child_by_field_name("type")))
            dimensiones = declarador.child_by_field_name("dimensions")
            if dimensiones is not None:
                declarado += texto(dimensiones).replace(" ", "")
            if declarado == "String" or declarado.startswith("String["):
                declarado = "java.lang." + declarado
            if declarado not in {"var", tipo}:
                return False
            while original.type == "parenthesized_expression":
                original = original.named_children[0]
        nodo = resolver(argumento, alias)
        valor = literal(nodo, alias)
        if nodo.type == "cast_expression":
            destino = tipo_borrado(texto(nodo.child_by_field_name("type")))
            operando = nodo.child_by_field_name("value")
            if not (
                esperado is None
                and operando is not None
                and resolver(operando, alias).type == "null_literal"
                and destino == tipo
                and tipo
                not in {
                    "boolean",
                    "byte",
                    "char",
                    "short",
                    "int",
                    "long",
                    "float",
                    "double",
                }
            ):
                return False
            continue
        if valor is NO_LITERAL or valor is None:
            return False
        actual = None
        if nodo.type == "string_literal":
            actual = "java.lang.String"
        elif nodo.type == "character_literal":
            actual = "char"
        elif nodo.type in {"true", "false"}:
            actual = "boolean"
        elif nodo.type.endswith("integer_literal") or nodo.type == "unary_expression":
            escrito = texto(nodo)
            if re.search(r"[lL]$", escrito):
                actual = "long"
                if not -(2**63) <= valor < 2**63:
                    return False
            elif nodo.type != "unary_expression" or nodo.child_by_field_name(
                "operand"
            ).type.endswith("integer_literal"):
                actual = "int"
                if not -(2**31) <= valor < 2**31:
                    return False
        if nodo.type == "decimal_floating_point_literal" or (
            nodo.type == "unary_expression"
            and nodo.child_by_field_name("operand").type
            == "decimal_floating_point_literal"
        ):
            actual = "float" if re.search(r"[fF]$", texto(nodo)) else "double"
        if nodo.type == "array_creation_expression":
            cabecera = texto(nodo).split("{", 1)[0]
            if not re.fullmatch(r"new\s+[\w.$]+(?:\s*\[\s*\])+\s*", cabecera):
                return False
            actual = tipo_borrado(cabecera.removeprefix("new").strip())
            if actual.startswith("String["):
                actual = "java.lang." + actual
        if actual != tipo:
            return False
    return True
