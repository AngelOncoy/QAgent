"""Aserciones Vitest de una prueba, leídas con tree-sitter y sin IA (EP-11a, parte 2).

Reconoce cada cadena ``expect(sujeto)[.not][.resolves|.rejects].matcher(esperado)``
con la prueba (``describe > it``) a la que pertenece, y las evasiones que harían
pasar una prueba sin comprobar nada: ``it.skip``/``it.todo``/``it.fails``,
``xit``, ``expect`` sobre un literal o ``expect`` dentro de un ``try`` cuyo
``catch`` se traga el error. Nunca ejecuta el código: solo lo parsea.

Lo usan el guardrail de Assertion Laundering (:mod:`javascript_laundering`) y el
oráculo de la prueba generada (:mod:`javascript_generacion`).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field

from tree_sitter import Node

from qagent.lenguajes.javascript_oraculo import NO_REPRESENTABLE, literal, normalizar
from qagent.lenguajes.treesitter import obtener_parser

#: Tamaño máximo de una prueba generada que el guardrail acepta analizar.
LIMITE_BYTES = 250_000
#: Profundidad máxima al sustituir alias (``const r = f(1)``) en un sujeto.
_PROFUNDIDAD_ALIAS = 20

#: Matchers de igualdad: se pueden intercambiar si no baja el rigor.
IGUALDAD = frozenset({"toBe", "toEqual", "toStrictEqual"})
#: Matchers de excepción equivalentes.
EXCEPCION = frozenset({"toThrow", "toThrowError"})
#: Modificadores de la cadena ``expect(...)``.
MODIFICADORES = frozenset({"not", "resolves", "rejects"})

#: Rigor de cada matcher (mayor = más estricto). Un matcher desconocido vale 0.
RIGOR: dict[str, int] = {
    "toStrictEqual": 10,
    "toEqual": 9,
    "toBe": 9,
    "toThrow": 9,
    "toThrowError": 9,
    "toBeCloseTo": 8,
    "toMatchObject": 7,
    "toContainEqual": 7,
    "toContain": 7,
    "toHaveLength": 7,
    "toHaveProperty": 6,
    "toMatch": 6,
    "toBeNull": 6,
    "toBeUndefined": 6,
    "toBeNaN": 6,
    "toBeInstanceOf": 5,
    "toBeGreaterThan": 4,
    "toBeGreaterThanOrEqual": 4,
    "toBeLessThan": 4,
    "toBeLessThanOrEqual": 4,
    "toBeTypeOf": 3,
    "toBeDefined": 2,
    "toBeTruthy": 1,
    "toBeFalsy": 1,
}
#: Rigor de ``toThrow()`` sin excepción: acepta cualquier error.
RIGOR_EXCEPCION_GENERICA = 4

_PRUEBAS = frozenset({"it", "test"})
_GRUPOS = frozenset({"describe", "suite"})
#: ``xit``, ``xtest`` y ``xdescribe`` omiten la prueba.
_OMITIDAS = frozenset({"xit", "xtest", "xdescribe"})
#: ``it.skip``, ``it.todo``, ``it.fails`` (invierte el resultado), ``it.skipIf``…
_EVASIONES = frozenset({"skip", "todo", "fails", "skipIf", "runIf"})
_COMENTARIOS = frozenset({"comment", "line_comment", "block_comment"})
_SEPARADORES = frozenset({",", ";"})


@dataclass(frozen=True)
class AsercionVitest:
    """Una aserción ``expect`` reconocida.

    Atributos:
        prueba: ``describe > it`` que la contiene ("" si está fuera de una prueba).
        sujeto: forma canónica del argumento de ``expect`` (alias sustituidos).
        matcher: ``toBe``, ``toEqual``, ``toThrow``…
        negada: si la cadena lleva ``.not``.
        modificadores: ``resolves``/``rejects`` en orden.
        esperado: forma canónica de los argumentos del matcher; None si no tiene.
        linea: línea de la aserción (desde 1).
        texto: código de la aserción tal como está escrito.
        silenciada: si está en un ``try`` cuyo ``catch`` se traga el error.
        argumentos: nodos de los argumentos del matcher (para el oráculo).
        sujeto_nodo: nodo del argumento de ``expect``.
    """

    prueba: str
    sujeto: str
    matcher: str
    negada: bool
    modificadores: tuple[str, ...]
    esperado: str | None
    linea: int
    texto: str
    silenciada: bool = False
    argumentos: tuple[Node, ...] = field(default=(), repr=False, compare=False)
    sujeto_nodo: Node | None = field(default=None, repr=False, compare=False)

    @property
    def rigor(self) -> int:
        """Rigor del matcher; ``toThrow()`` sin excepción es genérico."""
        if self.matcher in EXCEPCION and self.esperado is None:
            return RIGOR_EXCEPCION_GENERICA
        return RIGOR.get(self.matcher, 0)


@dataclass
class AnalisisVitest:
    """Aserciones, evasiones e imports de una prueba Vitest."""

    aserciones: list[AsercionVitest]
    evasiones: list[str]
    importaciones: dict[str, set[str]]


def gramatica_de_prueba(lenguaje: str) -> str:
    """Gramática con la que se parsea una prueba de ``lenguaje``."""
    return "typescript" if lenguaje == "typescript" else "javascript"


def parsear(codigo: str, lenguaje: str) -> Node:
    """Raíz del árbol de la prueba; TypeScript prueba también la gramática TSX.

    Raises:
        ValueError: si la prueba supera :data:`LIMITE_BYTES`.
        SyntaxError: si no se puede parsear.
    """
    datos = codigo.encode("utf-8")
    if len(datos) > LIMITE_BYTES:
        raise ValueError("La prueba Vitest es demasiado grande para el guardrail.")
    gramaticas = ["typescript", "tsx"] if lenguaje == "typescript" else ["javascript"]
    for gramatica in gramaticas:
        raiz = obtener_parser(gramatica).parse(datos).root_node
        if not raiz.has_error:
            return raiz
    raise SyntaxError("La prueba Vitest no se puede parsear.")


def texto(nodo: Node | None) -> str:
    """Texto literal de un nodo, o cadena vacía si no existe."""
    return nodo.text.decode("utf-8") if nodo is not None else ""


def argumentos(nodo: Node | None) -> list[Node]:
    """Argumentos con nombre de un nodo ``arguments``, sin comentarios."""
    if nodo is None:
        return []
    return [h for h in nodo.named_children if h.type not in _COMENTARIOS]


def valor_literal(nodo: Node | None) -> object:
    """Valor JSON normalizado de un literal JS, o ``NO_REPRESENTABLE``."""
    valor = literal(nodo)
    return valor if valor is NO_REPRESENTABLE else normalizar(valor)


def canon(nodo: Node | None, alias: dict[str, Node], profundidad: int = 0) -> str:
    """Forma canónica de una expresión: sin formato ni comentarios y con alias.

    Los literales se escriben como JSON (``'a'`` y ``"a"`` son iguales), y una
    variable ``const`` de asignación única se reemplaza por su valor.
    """
    if nodo is None or nodo.type in _COMENTARIOS:
        return ""
    if (
        nodo.type == "identifier"
        and profundidad < _PROFUNDIDAD_ALIAS
        and texto(nodo) in alias
    ):
        return canon(alias[texto(nodo)], alias, profundidad + 1)
    valor = valor_literal(nodo)
    if valor is not NO_REPRESENTABLE:
        return "lit:" + json.dumps(valor, sort_keys=True, ensure_ascii=False)
    if nodo.child_count == 0:
        return texto(nodo)
    partes = (
        canon(h, alias, profundidad + 1)
        for h in nodo.children
        if h.type not in _SEPARADORES
    )
    return " ".join(p for p in partes if p)


def _nombre_llamada(funcion: Node | None) -> tuple[str, list[str]] | None:
    """``it.skip.each`` -> (``it``, [``skip``, ``each``]); None si no es un nombre."""
    propiedades: list[str] = []
    while funcion is not None and funcion.type in {
        "member_expression",
        "call_expression",
    }:
        if funcion.type == "call_expression":  # it.each([...])("título", fn)
            funcion = funcion.child_by_field_name("function")
            continue
        propiedades.append(texto(funcion.child_by_field_name("property")))
        funcion = funcion.child_by_field_name("object")
    if funcion is None or funcion.type != "identifier":
        return None
    return texto(funcion), list(reversed(propiedades))


def _es_prueba(llamada: Node) -> tuple[str, list[str]] | None:
    """Base y propiedades si ``llamada`` es ``it``/``test``/``describe`` (o ``xit``)."""
    nombre = _nombre_llamada(llamada.child_by_field_name("function"))
    if nombre is None or nombre[0] not in _PRUEBAS | _GRUPOS | _OMITIDAS:
        return None
    return nombre


def _titulo(llamada: Node) -> str:
    """Título de ``it("título", ...)``; el texto del argumento si no es un literal."""
    primeros = argumentos(llamada.child_by_field_name("arguments"))
    if not primeros:
        return "?"
    valor = valor_literal(primeros[0])
    return valor if isinstance(valor, str) else texto(primeros[0])


def _traga_el_error(intento: Node) -> bool:
    """Si el ``catch`` de un ``try`` no relanza el error (lo silencia)."""
    manejador = intento.child_by_field_name("handler")
    if manejador is None:
        return False
    cuerpo = manejador.child_by_field_name("body")
    return not any(n.type == "throw_statement" for n in _todos(cuerpo))


def _todos(raiz: Node | None) -> Iterator[Node]:
    """Todos los nodos bajo ``raiz``, sin recursión."""
    pendientes = [raiz] if raiz is not None else []
    while pendientes:
        nodo = pendientes.pop()
        yield nodo
        pendientes.extend(reversed(nodo.children))


def _recorrer(raiz: Node) -> Iterator[tuple[Node, str, bool]]:
    """Cada nodo con su prueba (``describe > it``) y si está en un try silenciador."""
    pendientes: list[tuple[Node, str, bool]] = [(raiz, "", False)]
    while pendientes:
        nodo, prueba, silenciada = pendientes.pop()
        if nodo.type in _COMENTARIOS:
            continue
        yield nodo, prueba, silenciada
        if nodo.type == "call_expression" and _es_prueba(nodo) is not None:
            titulo = _titulo(nodo)
            prueba = f"{prueba} > {titulo}" if prueba else titulo
        if nodo.type == "try_statement" and _traga_el_error(nodo):
            cuerpo = nodo.child_by_field_name("body")
            for hijo in reversed(nodo.children):
                pendientes.append((hijo, prueba, silenciada or hijo == cuerpo))
            continue
        for hijo in reversed(nodo.children):
            pendientes.append((hijo, prueba, silenciada))


def _alias(raiz: Node) -> dict[str, dict[str, Node]]:
    """Variables ``const`` de asignación única por prueba ("" = nivel de archivo)."""
    vistos: dict[str, dict[str, list[Node]]] = {}
    for nodo, prueba, _ in _recorrer(raiz):
        if nodo.type != "lexical_declaration":
            continue
        if texto(nodo.child_by_field_name("kind")) != "const":
            continue
        for declarador in nodo.named_children:
            if declarador.type != "variable_declarator":
                continue
            nombre = declarador.child_by_field_name("name")
            valor = declarador.child_by_field_name("value")
            if nombre is None or valor is None or nombre.type != "identifier":
                continue
            vistos.setdefault(prueba, {}).setdefault(texto(nombre), []).append(valor)
    return {
        prueba: {n: valores[0] for n, valores in nombres.items() if len(valores) == 1}
        for prueba, nombres in vistos.items()
    }


def _alias_de(alias: dict[str, dict[str, Node]], prueba: str) -> dict[str, Node]:
    """Alias visibles en ``prueba``: los de sus ``describe`` y los propios."""
    visibles = dict(alias.get("", {}))
    partes = prueba.split(" > ") if prueba else []
    for i in range(1, len(partes) + 1):
        visibles.update(alias.get(" > ".join(partes[:i]), {}))
    return visibles


def _leer_expect(
    llamada: Node, prueba: str, silenciada: bool, alias: dict[str, Node]
) -> AsercionVitest | None:
    """La aserción de ``expect(x)[.not].matcher(y)``; None si no es una."""
    funcion = llamada.child_by_field_name("function")
    if funcion is None or funcion.type != "member_expression":
        return None
    matcher = texto(funcion.child_by_field_name("property"))
    modificadores: list[str] = []
    objeto = funcion.child_by_field_name("object")
    while objeto is not None and objeto.type == "member_expression":
        modificadores.append(texto(objeto.child_by_field_name("property")))
        objeto = objeto.child_by_field_name("object")
    if objeto is None or objeto.type != "call_expression":
        return None
    raiz = objeto.child_by_field_name("function")
    if raiz is None or texto(raiz) not in {"expect", "expect.soft"}:
        return None
    if any(m not in MODIFICADORES for m in modificadores) or matcher in MODIFICADORES:
        return None
    modificadores.reverse()
    sujetos = argumentos(objeto.child_by_field_name("arguments"))
    sujeto = sujetos[0] if sujetos else None
    esperados = argumentos(llamada.child_by_field_name("arguments"))
    return AsercionVitest(
        prueba=prueba,
        sujeto=canon(sujeto, alias),
        matcher=matcher,
        negada="not" in modificadores,
        modificadores=tuple(m for m in modificadores if m != "not"),
        esperado=" , ".join(canon(e, alias) for e in esperados) if esperados else None,
        linea=llamada.start_point.row + 1,
        texto=" ".join(texto(llamada).split())[:160],
        silenciada=silenciada,
        argumentos=tuple(esperados),
        sujeto_nodo=sujeto,
    )


def _importaciones(raiz: Node) -> dict[str, set[str]]:
    """Fuente de cada ``import`` -> nombres locales que importa."""
    resultado: dict[str, set[str]] = {}
    for sentencia in raiz.named_children:
        if sentencia.type != "import_statement":
            continue
        fuente = valor_literal(sentencia.child_by_field_name("source"))
        if not isinstance(fuente, str):
            continue
        nombres = resultado.setdefault(fuente, set())
        for nodo in _todos(sentencia):
            if nodo.type == "import_specifier":
                local = nodo.child_by_field_name("alias") or nodo.child_by_field_name(
                    "name"
                )
                nombres.add(texto(local))
            elif nodo.type == "import_clause" or nodo.type == "namespace_import":
                nombres.update(
                    texto(h) for h in nodo.named_children if h.type == "identifier"
                )
    return resultado


def analizar_vitest(codigo: str, lenguaje: str) -> AnalisisVitest:
    """Aserciones, evasiones e imports de una prueba Vitest.

    Raises:
        SyntaxError: si la prueba no se puede parsear.
        ValueError: si la prueba es demasiado grande.
    """
    raiz = parsear(codigo, lenguaje)
    alias = _alias(raiz)
    aserciones: list[AsercionVitest] = []
    evasiones: list[str] = []
    for nodo, prueba, silenciada in _recorrer(raiz):
        if nodo.type != "call_expression":
            continue
        linea = nodo.start_point.row + 1
        nombre = _es_prueba(nodo)
        if nombre is not None:
            base, propiedades = nombre
            evasion = next((p for p in propiedades if p in _EVASIONES), None)
            if base in _OMITIDAS or evasion is not None:
                llamada = base + "".join(f".{p}" for p in propiedades)
                evasiones.append(
                    f"Prueba omitida o invertida con {llamada} (línea {linea})."
                )
            continue
        asercion = _leer_expect(nodo, prueba, silenciada, _alias_de(alias, prueba))
        if asercion is None:
            continue
        aserciones.append(asercion)
        if asercion.silenciada:
            evasiones.append(
                f"expect envuelto en un try/catch que se traga el error (línea {linea}): "
                f"{asercion.texto}"
            )
        if valor_literal(asercion.sujeto_nodo) is not NO_REPRESENTABLE:
            evasiones.append(
                f"expect sobre un literal no comprueba el código (línea {linea}): "
                f"{asercion.texto}"
            )
    aserciones.sort(key=lambda a: a.linea)
    return AnalisisVitest(aserciones, evasiones, _importaciones(raiz))
