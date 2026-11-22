"""Comprueba fábricas y tipos de elementos por AST, sin ejecutar Java (#300)."""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path
from typing import Any

from tree_sitter import Node

from qagent.lenguajes.java_colecciones import (
    TipoValor,
    compatible_coleccion,
    tipo_coleccion,
)


def fabrica(nodo: Node, alias: dict[str, Node]) -> tuple[str, list[Node]] | None:
    """Fábricas de java.util admitidas; no resuelve llamadas ni constructores ajenos."""
    from qagent.lenguajes.java_aserciones import argumentos, resolver, texto

    nodo = resolver(nodo, alias)
    if nodo.type == "method_invocation":
        receptor = texto(nodo.child_by_field_name("object"))
        nombre = texto(nodo.child_by_field_name("name"))
        if (
            receptor.split(".", 1)[0] in alias
            or nodo.child_by_field_name("type_arguments") is not None
        ):
            return None
        args = argumentos(nodo)
        for familia in ("List", "Set"):
            if receptor in {familia, "java.util." + familia} and nombre == "of":
                return familia, args
        if receptor in {"Arrays", "java.util.Arrays"} and nombre == "asList":
            return "List", args
        if receptor in {"Collections", "java.util.Collections"}:
            if nombre in {"emptyList", "emptySet"} and not args:
                return ("Set" if nombre == "emptySet" else "List"), []
            if nombre in {"singleton", "singletonList"} and len(args) == 1:
                return ("Set" if nombre == "singleton" else "List"), args
    if nodo.type == "object_creation_expression":
        clase = re.sub(r"<.*>", "", texto(nodo.child_by_field_name("type")))
        args = argumentos(nodo)
        if (
            clase
            in {
                "HashSet",
                "LinkedHashSet",
                "java.util.HashSet",
                "java.util.LinkedHashSet",
            }
            and len(args) == 1
        ):
            hijo = fabrica(args[0], alias)
            if hijo is not None and hijo[0] == "List":
                return "Set", hijo[1]
    return None


def coincide_coleccion(
    tipo: str,
    nodo: Node,
    esperado: Any,
    alias: dict[str, Node],
    *,
    entrada: bool = False,
) -> bool:
    """Vincula la expresión y sus tipos reales al JSON, incluidos Set anidados."""
    from qagent.lenguajes.java_aserciones import NO_LITERAL, literal, resolver, texto

    modelo = tipo_coleccion(tipo)
    if modelo is None or not compatible_coleccion(tipo, esperado):
        return False
    if entrada and nodo.type == "identifier" and texto(nodo) in alias:
        valor = alias[texto(nodo)]
        declaracion = valor.parent.parent if valor.parent else None
        if declaracion is None or declaracion.type != "local_variable_declaration":
            return False
        escrito = texto(declaracion.child_by_field_name("type"))
        if escrito != "var":
            declarado = tipo_coleccion(escrito)
            familias = (
                {modelo.nombre}
                if modelo.nombre in {"List", "Set"}
                else {"List", "Collection", "Iterable"}
            )
            if (
                declarado is None
                or declarado.nombre not in familias
                or declarado.elemento != modelo.elemento
            ):
                return False

    def escalar(t: TipoValor, n: Node, e: Any) -> bool:
        valor = literal(n, alias)
        if valor is NO_LITERAL:
            return False
        if e is None:
            return n.type == "null_literal"
        if t.nombre == "String":
            return n.type == "string_literal" and valor == e
        if t.nombre == "Character":
            return n.type == "character_literal" and valor == e
        if t.nombre == "Boolean":
            return n.type in {"true", "false"} and type(valor) is bool and valor == e
        original = n
        if n.type == "unary_expression":
            n = n.child_by_field_name("operand")
        if t.nombre in {"Byte", "Short"}:
            return (
                original.type == "cast_expression"
                and texto(original.child_by_field_name("type")) == t.nombre.lower()
                and isinstance(valor, Decimal)
                and valor == Decimal(str(e))
            )
        if t.nombre in {"Integer", "Long"}:
            if n is None or not n.type.endswith("integer_literal"):
                return False
            tiene_l = bool(re.search("[lL]$", texto(n)))
            return (
                tiene_l == (t.nombre == "Long")
                and isinstance(valor, Decimal)
                and valor == Decimal(e)
            )
        if t.nombre in {"Float", "Double"}:
            if n is None or n.type != "decimal_floating_point_literal":
                return False
            es_float = bool(re.search("[fF]$", texto(n)))
            return (
                es_float == (t.nombre == "Float")
                and isinstance(valor, Decimal)
                and not (valor.is_zero() and texto(original).lstrip().startswith("-"))
                and valor == Decimal(str(e))
            )
        return False

    def comprobar(t: TipoValor, n: Node, e: Any) -> bool:
        n = resolver(n, alias)
        if e is None:
            return n.type == "null_literal"
        if t.elemento is None:
            return escalar(t, n, e)
        forma = fabrica(n, alias)
        if forma is None or literal(n, alias) is NO_LITERAL:
            return False
        familia, hijos = forma
        if familia != ("Set" if t.nombre == "Set" else "List") or len(hijos) != len(e):
            return False
        if n.type == "object_creation_expression":
            escrito = re.sub(r"^java\.util\.", "", texto(n.child_by_field_name("type")))
            if not escrito.endswith("<>"):
                declarado = tipo_coleccion(
                    re.sub(r"^(HashSet|LinkedHashSet)", "Set", escrito)
                )
                if declarado != t:
                    return False
        if t.nombre == "Set":
            disponibles = list(e)
            for hijo in hijos:
                i = next(
                    (
                        i
                        for i, v in enumerate(disponibles)
                        if comprobar(t.elemento, hijo, v)
                    ),
                    None,
                )
                if i is None:
                    return False
                disponibles.pop(i)
            return True
        return all(comprobar(t.elemento, h, v) for h, v in zip(hijos, e))

    return comprobar(modelo, nodo, esperado)


def nombre_import(declaracion: str) -> str:
    """Normaliza tokens de import sin permitir que comentarios oculten homónimos."""
    limpio = re.sub(r"/\*.*?\*/|//[^\r\n]*", "", declaracion, flags=re.DOTALL)
    return re.sub(r"\s+", "", limpio).removeprefix("import").removesuffix(";")


def origen_util(tipo: str, imports: list[str]) -> bool:
    """Prueba un nombre simple de fábrica, priorizando imports explícitos."""
    nombres = [nombre_import(i) for i in imports]
    explicitos = [
        i
        for i in nombres
        if not i.startswith("static") and i.rsplit(".", 1)[-1] == tipo
    ]
    if explicitos:
        return all(i == "java.util." + tipo for i in explicitos)
    comodines = {i for i in nombres if i.endswith(".*") and not i.startswith("static")}
    return "java.util.*" in comodines and comodines <= {
        "java.util.*",
        "java.lang.*",
        "org.junit.jupiter.api.*",
        "org.mockito.*",
    }


def problema_origen(
    tipo: str, imports: list[str], clases: list[dict[str, Any]], carpeta: Path
) -> str | None:
    """Rechaza homónimos o resolución ambigua antes de anunciar semántica de colección."""
    from qagent.lenguajes.java_colecciones import FAMILIAS

    if tipo_coleccion(tipo) is None:
        return None
    nombres = [nombre_import(i) for i in imports]
    locales = {c["nombre"].rsplit(".", 1)[-1] for c in clases}
    for escrito in re.findall(r"[\w.]+", tipo):
        simple = escrito.rsplit(".", 1)[-1]
        canonico = FAMILIAS.get(simple, "java.lang." + simple)
        if "." in escrito:
            if escrito != canonico:
                return (
                    "el tipo " + escrito + " no corresponde al tipo estándar admitido"
                )
            continue
        if simple in locales:
            return "un tipo local sustituye " + simple
        explicitos = [
            i
            for i in nombres
            if not i.startswith("static") and i.rsplit(".", 1)[-1] == simple
        ]
        if explicitos:
            if all(i == canonico for i in explicitos):
                continue
            return "un import sustituye " + simple
        if (carpeta / (simple + ".java")).exists():
            return (
                "hay un tipo vecino "
                + simple
                + " cuya identidad estándar no está demostrada"
            )
        comodines = {
            i for i in nombres if not i.startswith("static") and i.endswith(".*")
        }
        if comodines - {
            "java.util.*",
            "java.lang.*",
            "org.junit.jupiter.api.*",
            "org.mockito.*",
        }:
            return "imports comodín no resueltos para " + simple
        if canonico.startswith("java.util.") and "java.util.*" not in comodines:
            return "falta el import estándar de " + simple
    return None
