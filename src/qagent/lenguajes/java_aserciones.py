"""Extracción estática de aserciones JUnit 5 para el guardrail Java (#184).

No evalúa Java. Reconoce imports de JUnit, literales y alias locales de una sola
asignación. Ante construcciones no demostrables, el oráculo rechaza el test.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from tree_sitter import Node

from qagent.lenguajes.treesitter import obtener_parser

NO_LITERAL = object()
_ASERCIONES = {
    "assertEquals",
    "assertArrayEquals",
    "assertNotEquals",
    "assertTrue",
    "assertFalse",
    "assertNull",
    "assertNotNull",
    "assertThrows",
    "assertThrowsExactly",
}
_EVASIONES = {
    "assert_statement",
    "try_statement",
    "try_with_resources_statement",
    "if_statement",
    "for_statement",
    "enhanced_for_statement",
    "while_statement",
    "do_statement",
    "switch_expression",
    "return_statement",
    "throw_statement",
    "assignment_expression",
    "update_expression",
}


def texto(nodo: Node | None) -> str:
    """Texto literal de un nodo, o cadena vacía si el campo no existe."""
    return nodo.text.decode("utf-8") if nodo is not None else ""


def nodos(raiz: Node) -> list[Node]:
    """Recorrido acotado sin recursión, omitiendo comentarios."""
    pendientes, resultado = [raiz], []
    while pendientes:
        nodo = pendientes.pop()
        if nodo.type in {"line_comment", "block_comment"}:
            continue
        resultado.append(nodo)
        if len(resultado) > 20_000:
            raise ValueError("La prueba Java excede el límite del análisis estático.")
        pendientes.extend(reversed(nodo.named_children))
    return resultado


def argumentos(nodo: Node) -> list[Node]:
    """Argumentos de una invocación, en su orden original."""
    lista = nodo.child_by_field_name("arguments")
    return (
        [
            h
            for h in lista.named_children
            if h.type not in {"line_comment", "block_comment"}
        ]
        if lista is not None
        else []
    )


def resolver(
    nodo: Node, alias: dict[str, Node], vistos: frozenset[str] = frozenset()
) -> Node:
    """Resuelve paréntesis y variables locales estables sin ejecutar expresiones."""
    visitados = set(vistos)
    for _ in range(128):
        if nodo.type == "parenthesized_expression" and len(nodo.named_children) == 1:
            nodo = nodo.named_children[0]
            continue
        nombre = texto(nodo)
        if nodo.type == "identifier" and nombre in alias and nombre not in visitados:
            visitados.add(nombre)
            nodo = alias[nombre]
            continue
        return nodo
    raise ValueError(
        "La prueba excede el límite de anidamiento de expresiones o alias."
    )


def literal(
    nodo: Node | None, alias: dict[str, Node] | None = None, profundidad: int = 0
) -> Any:
    """Convierte únicamente literales Java y fábricas conocidas de colecciones.

    Devuelve NO_LITERAL para llamadas arbitrarias, operaciones o valores no
    finitos. Nunca usa eval, ejecuta constructores ni importa clases del usuario.
    """
    if nodo is None or profundidad > 32:
        return NO_LITERAL
    alias = alias or {}
    nodo = resolver(nodo, alias)
    valor = texto(nodo)
    if len(valor) > 1000 and nodo.type.endswith("literal"):
        return NO_LITERAL
    if nodo.type == "true":
        return True
    if nodo.type == "false":
        return False
    if nodo.type == "null_literal":
        return None
    if nodo.type == "string_literal":
        try:
            return json.loads(valor)
        except (ValueError, json.JSONDecodeError):
            return NO_LITERAL
    if nodo.type == "character_literal" and len(valor) == 3:
        return valor[1]
    if nodo.type == "unary_expression":
        operando = nodo.child_by_field_name("operand")
        signo = valor[:1]
        numero = literal(operando, alias, profundidad + 1)
        return (
            (-numero if signo == "-" else numero)
            if signo in {"+", "-"} and isinstance(numero, Decimal)
            else NO_LITERAL
        )
    if nodo.type.endswith("integer_literal"):
        numero = re.sub(r"[lL]$", "", valor.replace("_", ""))
        try:
            base = (
                16
                if numero.lower().startswith("0x")
                else 2
                if numero.lower().startswith("0b")
                else 8
                if len(numero) > 1 and numero.startswith("0")
                else 10
            )
            return Decimal(int(numero, base))
        except ValueError:
            return NO_LITERAL
    if nodo.type == "decimal_floating_point_literal":
        try:
            numero = Decimal(re.sub(r"[fFdD]$", "", valor.replace("_", "")))
            return numero if numero.is_finite() else NO_LITERAL
        except InvalidOperation:
            return NO_LITERAL
    elementos = None
    if nodo.type == "method_invocation":
        receptor = texto(nodo.child_by_field_name("object"))
        nombre = texto(nodo.child_by_field_name("name"))
        if receptor in alias:
            return NO_LITERAL
        if (receptor, nombre) in {
            ("List", "of"),
            ("java.util.List", "of"),
            ("Arrays", "asList"),
            ("java.util.Arrays", "asList"),
        }:
            elementos = argumentos(nodo)
        elif (receptor, nombre) in {
            ("Collections", "emptyList"),
            ("java.util.Collections", "emptyList"),
        } and not argumentos(nodo):
            return []
    if nodo.type == "array_creation_expression":
        inicializador = next(
            (h for h in nodo.named_children if h.type == "array_initializer"), None
        )
        if inicializador is not None:
            elementos = list(inicializador.named_children)
    if elementos is not None:
        valores = [literal(e, alias, profundidad + 1) for e in elementos]
        return valores if all(v is not NO_LITERAL for v in valores) else NO_LITERAL
    return NO_LITERAL


def canon(nodo: Node | None, alias: dict[str, Node], profundidad: int = 0) -> str:
    """Forma estable por AST: ignora formato/comentarios y conserva sujetos y valores."""
    if nodo is None or profundidad > 32:
        return "?"
    nodo = resolver(nodo, alias)
    valor = literal(nodo, alias)
    if valor is not NO_LITERAL:
        return _valor_canon(valor)
    if not nodo.children:
        return nodo.type + ":" + texto(nodo)
    return (
        nodo.type
        + "("
        + " ".join(
            canon(h, alias, profundidad + 1)
            for h in nodo.children
            if h.type not in {"line_comment", "block_comment"}
        )
        + ")"
    )


def _valor_canon(valor: Any) -> str:
    """Distingue tipos, normaliza números y conserva el contenido de las cadenas."""
    if isinstance(valor, Decimal):
        signo, digitos, exponente = valor.as_tuple()
        digitos = list(digitos)
        while len(digitos) > 1 and digitos[-1] == 0:
            digitos.pop()
            exponente += 1
        if not any(digitos):
            signo, digitos, exponente = 0, [0], 0
        return f"numero:{signo}:{''.join(map(str, digitos))}:{exponente}"
    if isinstance(valor, list):
        return "lista:" + repr([_valor_canon(v) for v in valor])
    return type(valor).__name__ + ":" + repr(valor)


@dataclass(frozen=True)
class AsercionJava:
    """Aserción reconocida, su sujeto y los nodos necesarios para validar el contrato."""

    tipo: str
    sujeto: str
    esperado: str | None
    tolerancia: str | None
    linea: int
    prueba: str
    actual: Node = field(repr=False, compare=False)
    valor: Node | None = field(repr=False, compare=False)
    delta: Node | None = field(repr=False, compare=False)
    alias: dict[str, Node] = field(repr=False, compare=False)


@dataclass
class AnalisisJUnit:
    """Resultado acotado del parseo: aserciones, métodos @Test y evasiones detectadas."""

    raiz: Node
    aserciones: list[AsercionJava]
    evasiones: list[str]
    pruebas: list[str]


def analizar_junit(codigo: str) -> AnalisisJUnit:
    """Reconoce JUnit 5 con imports reales y variables locales de asignación única.

    El subconjunto admitido usa @Test y aserciones directas, sin control de flujo,
    helpers, inicializadores ni clases anidadas que pudieran ocultar verificaciones.
    """
    if len(codigo.encode("utf-8")) > 250_000:
        raise ValueError("La prueba Java es demasiado grande para el guardrail.")
    raiz = obtener_parser("java").parse(codigo.encode("utf-8")).root_node
    if raiz.has_error:
        raise SyntaxError("La prueba Java no se puede parsear.")
    todos = nodos(raiz)
    imports = [
        texto(n).replace(" ", "").removeprefix("import").removesuffix(";")
        for n in raiz.named_children
        if n.type == "import_declaration"
    ]
    estaticos = {
        i.removeprefix("staticorg.junit.jupiter.api.Assertions.")
        for i in imports
        if i.startswith("staticorg.junit.jupiter.api.Assertions.")
    }
    ambiguos = any(
        i.startswith("static")
        and not i.startswith("staticorg.junit.jupiter.api.Assertions.")
        and (
            i.endswith(".*")
            and not i.startswith("staticorg.mockito.Mockito.")
            or i.rsplit(".", 1)[-1] in _ASERCIONES
        )
        for i in imports
    )
    reconoce_test = any(
        i in {"org.junit.jupiter.api.Test", "org.junit.jupiter.api.*"} for i in imports
    )
    reconoce_assertions = any(
        i in {"org.junit.jupiter.api.Assertions", "org.junit.jupiter.api.*"}
        for i in imports
    )
    evasiones: list[str] = []
    aserciones: list[AsercionJava] = []
    pruebas: list[str] = []
    if any(
        n.type
        not in {
            "package_declaration",
            "import_declaration",
            "class_declaration",
            "line_comment",
            "block_comment",
        }
        for n in raiz.named_children
    ):
        evasiones.append(
            "No se admiten tipos auxiliares ni anotaciones propias que sustituyan JUnit."
        )
    clases = [
        n
        for n in todos
        if n.type
        in {
            "class_declaration",
            "interface_declaration",
            "enum_declaration",
            "record_declaration",
        }
    ]
    if len(clases) != 1:
        evasiones.append(
            "Se requiere una única clase de prueba, sin clases auxiliares o anidadas."
        )
    for clase in clases:
        if any(
            clase.child_by_field_name(campo) is not None
            for campo in ("superclass", "interfaces", "type_parameters")
        ):
            evasiones.append(
                "La clase de prueba no puede heredar helpers ni reemplazar aserciones de JUnit."
            )
        cuerpo_clase = clase.child_by_field_name("body")
        if cuerpo_clase is not None and any(
            h.type not in {"method_declaration", "line_comment", "block_comment"}
            for h in cuerpo_clase.named_children
        ):
            evasiones.append(
                "La clase de prueba usa inicializadores, campos o miembros no verificables."
            )
    for nodo in todos:
        if nodo.type in _EVASIONES:
            evasiones.append(
                f"Construcción que puede ocultar o cambiar aserciones: {nodo.type}, línea {nodo.start_point.row + 1}."
            )
        if nodo.type in {"static_initializer", "constructor_declaration"}:
            evasiones.append(
                "No se admiten inicializadores ni constructores en la clase de prueba."
            )
        if (
            nodo.type == "method_declaration"
            and texto(nodo.child_by_field_name("name")) in _ASERCIONES
        ):
            evasiones.append("La prueba redefine una aserción de JUnit.")
        if nodo.type in {"annotation", "marker_annotation"}:
            nombre = texto(nodo.child_by_field_name("name"))
            if nombre.rsplit(".", 1)[-1] not in {"Test", "DisplayName"}:
                evasiones.append(f"Anotación no admitida por el guardrail: {nombre}.")
        if nodo.type != "method_declaration":
            continue
        modificadores = next(
            (h for h in nodo.named_children if h.type == "modifiers"), None
        )
        anotaciones = (
            [
                texto(h.child_by_field_name("name"))
                for h in modificadores.named_children
                if h.type in {"marker_annotation", "annotation"}
            ]
            if modificadores is not None
            else []
        )
        if not any(
            a == "org.junit.jupiter.api.Test" or a == "Test" and reconoce_test
            for a in anotaciones
        ):
            evasiones.append(
                "Todos los métodos de la prueba deben ser @Test de JUnit 5."
            )
            continue
        nombre_prueba = texto(nodo.child_by_field_name("name"))
        if nombre_prueba in pruebas:
            evasiones.append("Hay métodos de prueba duplicados.")
        pruebas.append(nombre_prueba)
        cuerpo = nodo.child_by_field_name("body")
        if cuerpo is None:
            continue
        parametros = nodo.child_by_field_name("parameters")
        tokens_mod = (
            {h.type for h in modificadores.children}
            if modificadores is not None
            else set()
        )
        if (
            texto(nodo.child_by_field_name("type")) != "void"
            or parametros.named_children
            or tokens_mod & {"private", "static", "abstract"}
        ):
            evasiones.append(
                "Los métodos @Test deben ser void, sin parámetros y no privados ni static."
            )
        interiores = nodos(cuerpo)
        declaraciones = [n for n in interiores if n.type == "variable_declarator"]
        repetidos = Counter(texto(n.child_by_field_name("name")) for n in declaraciones)
        alias = {
            texto(n.child_by_field_name("name")): n.child_by_field_name("value")
            for n in declaraciones
            if n.child_by_field_name("value") is not None
            and repetidos[texto(n.child_by_field_name("name"))] == 1
        }
        for invocacion in interiores:
            if invocacion.type != "method_invocation":
                continue
            nombre = texto(invocacion.child_by_field_name("name"))
            receptor = texto(invocacion.child_by_field_name("object"))
            if receptor in {"List", "Arrays", "Collections"} and not any(
                i in {"java.util." + receptor, "java.util.*"} for i in imports
            ):
                evasiones.append(
                    "Las fábricas de colecciones deben proceder de java.util."
                )
            if nombre in {"assumeTrue", "assumeFalse", "abort", "exit", "halt"}:
                evasiones.append(f"La prueba puede omitir su comprobación: {nombre}.")
            if (
                nombre == "fail"
                or nombre.startswith("assert")
                and nombre not in _ASERCIONES
            ):
                evasiones.append(
                    f"Aserción adicional no trazable al contrato: {nombre}."
                )
            if nombre not in _ASERCIONES:
                continue
            padre = invocacion.parent
            directo = padre is not None and (
                (padre.type == "expression_statement" and padre.parent == cuerpo)
                or (
                    padre.type == "variable_declarator"
                    and padre.parent is not None
                    and padre.parent.type == "local_variable_declaration"
                    and padre.parent.parent == cuerpo
                )
            )
            if not directo:
                evasiones.append(
                    "La aserción debe ejecutarse directamente en el cuerpo de @Test, no en un helper o lambda diferida."
                )
            reconocido = (
                receptor == "org.junit.jupiter.api.Assertions"
                or receptor == "Assertions"
                and reconoce_assertions
                and "Assertions" not in alias
                or not receptor
                and not ambiguos
                and (nombre in estaticos or "*" in estaticos)
            )
            if receptor and receptor.split(".", 1)[0] in alias:
                reconocido = False
            if not reconocido:
                evasiones.append(
                    f"No se puede demostrar que {nombre} pertenece a JUnit 5."
                )
                continue
            args = argumentos(invocacion)
            if not args:
                continue
            valor, delta = None, None
            if nombre in {
                "assertEquals",
                "assertArrayEquals",
                "assertNotEquals",
                "assertThrows",
                "assertThrowsExactly",
            }:
                if len(args) < 2:
                    continue
                valor, actual = args[:2]
                if len(args) >= 3 and isinstance(literal(args[2], alias), Decimal):
                    delta = args[2]
            else:
                actual = args[0]
            esperado = (
                canon(valor, alias)
                if valor is not None
                else {
                    "assertTrue": "bool:True",
                    "assertFalse": "bool:False",
                    "assertNull": "NoneType:None",
                }.get(nombre)
            )
            tipo = {
                "assertEquals": "igualdad",
                "assertArrayEquals": "array",
                "assertNotEquals": "distinto",
                "assertTrue": "booleano",
                "assertFalse": "booleano",
                "assertNull": "nulo",
                "assertNotNull": "no_nulo",
                "assertThrows": "excepcion",
                "assertThrowsExactly": "excepcion_exacta",
            }[nombre]
            sujeto = actual
            if tipo in {"excepcion", "excepcion_exacta"}:
                sujeto = resolver(actual, alias)
                if sujeto.type == "lambda_expression":
                    parametros_lambda = sujeto.child_by_field_name("parameters")
                    cuerpo_lambda = sujeto.child_by_field_name("body")
                    if (
                        parametros_lambda is not None
                        and parametros_lambda.type == "formal_parameters"
                        and not parametros_lambda.named_children
                        and cuerpo_lambda is not None
                    ):
                        if cuerpo_lambda.type == "block":
                            hijos = [
                                h
                                for h in cuerpo_lambda.named_children
                                if h.type not in {"line_comment", "block_comment"}
                            ]
                            if (
                                len(hijos) == 1
                                and hijos[0].type == "expression_statement"
                                and len(hijos[0].named_children) == 1
                            ):
                                sujeto = hijos[0].named_children[0]
                        else:
                            sujeto = cuerpo_lambda
                if valor is not None and valor.type == "class_literal":
                    esperado = "excepcion:" + texto(valor).removeprefix("java.lang.")
            aserciones.append(
                AsercionJava(
                    tipo,
                    canon(sujeto, alias),
                    esperado,
                    canon(delta, alias) if delta is not None else None,
                    invocacion.start_point.row + 1,
                    nombre_prueba,
                    actual,
                    valor,
                    delta,
                    alias,
                )
            )
    if not pruebas:
        evasiones.append("No hay métodos @Test reconocidos de JUnit 5.")
    return AnalisisJUnit(raiz, aserciones, list(dict.fromkeys(evasiones)), pruebas)
