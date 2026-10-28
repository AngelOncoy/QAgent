"""Texto normalizado de nodos tree-sitter de Python (TA-16).

El Planner recibe tipos, valores por defecto y firmas tal como los escribía
``ast.unparse``: sin comentarios ni espacios de más, con los paréntesis justos y las
cadenas con ``repr()``. Este módulo reproduce ese texto leyendo el árbol de
tree-sitter, sin importar ni ejecutar nada:

* :func:`expresion` equivale a ``ast.unparse`` de una expresión;
* :func:`argumentos` equivale a ``ast.unparse`` de ``ast.arguments`` (la firma);
* :func:`docstring` equivale a ``ast.get_docstring`` (con ``inspect.cleandoc``);
* :func:`literal` equivale a ``ast.literal_eval`` de un nodo, y :func:`literal_de_texto`
  al de un texto.

Las reglas (precedencias, elección de comillas, f-strings) son las de ``_Unparser`` de
la biblioteca estándar de Python 3.11.
"""

from __future__ import annotations

import inspect
import sys
import unicodedata
from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from tree_sitter import Node

from qagent.analysis.arbol_ts import (
    KWARGS,
    POSICIONAL,
    POSICIONAL_SOLO,
    SOLO_NOMBRE,
    VARARGS,
    Importacion,
    Parametro,
    campo,
    error_de_sintaxis,
    hijos,
    nombrados,
    parametros,
    parsear,
    sentencias,
    sin_envoltura,
    texto,
)


class _P(IntEnum):
    """Precedencias de ``ast._Precedence``."""

    NAMED_EXPR = 1
    TUPLE = 2
    YIELD = 3
    TEST = 4
    OR = 5
    AND = 6
    NOT = 7
    CMP = 8
    EXPR = 9
    BXOR = 10
    BAND = 11
    SHIFT = 12
    ARITH = 13
    TERM = 14
    FACTOR = 15
    POWER = 16
    AWAIT = 17
    ATOM = 18

    def siguiente(self) -> _P:
        return _P(min(self + 1, _P.ATOM))


_BINARIOS = {
    "+": _P.ARITH,
    "-": _P.ARITH,
    "*": _P.TERM,
    "@": _P.TERM,
    "/": _P.TERM,
    "%": _P.TERM,
    "//": _P.TERM,
    "<<": _P.SHIFT,
    ">>": _P.SHIFT,
    "|": _P.EXPR,
    "^": _P.BXOR,
    "&": _P.BAND,
    "**": _P.POWER,
}
_COMPRENSIONES = {
    "list_comprehension": ("[", "]"),
    "set_comprehension": ("{", "}"),
    "generator_expression": ("(", ")"),
    "dictionary_comprehension": ("{", "}"),
}
_TUPLAS = frozenset(
    {
        "tuple",
        "expression_list",
        "pattern_list",
        "tuple_pattern",
        "expression_statement",  # «a, b» suelto (ver expresion_de_texto)
    }
)
_LISTAS = frozenset({"list", "list_pattern"})
_COMILLAS_SIMPLES = ("'", '"')
_COMILLAS_TRIPLES = ('"""', "'''")
_COMILLAS = (*_COMILLAS_SIMPLES, *_COMILLAS_TRIPLES)
_INFINITO = "1e" + repr(sys.float_info.max_10_exp + 1)


class NoEsLiteral(ValueError):
    """El nodo no es un literal que ``ast.literal_eval`` acepte."""


# --------------------------------------------------------------------------- #
# Interfaz
# --------------------------------------------------------------------------- #
def expresion(nodo: Node | None) -> str | None:
    """``ast.unparse`` de una expresión; None si no hay nodo."""
    if nodo is None:
        return None
    return _Escritor().escribir(nodo, _P.TEST)


def argumentos(lista: list[Parametro]) -> str:
    """``ast.unparse`` de los argumentos de una función (sin los paréntesis)."""
    return _Escritor().argumentos(lista)


def firma(funcion: Node) -> str:
    """``(argumentos) -> retorno`` de una ``function_definition``, como en ``ast``."""
    texto_firma = f"({argumentos(parametros(campo(funcion, 'parameters')))})"
    retorno = expresion(campo(funcion, "return_type"))
    return texto_firma if retorno is None else f"{texto_firma} -> {retorno}"


def sentencia_import(importado: Importacion) -> str:
    """``ast.unparse`` de un ``import`` o ``from ... import``."""
    nombres = ", ".join(
        original if alias is None else f"{original} as {alias}"
        for original, alias in importado.nombres
    )
    if not importado.desde:
        return f"import {nombres}"
    origen = "." * importado.nivel + (importado.modulo or "")
    return f"from {origen} import {nombres}"


def docstring(bloque: Node | None) -> str | None:
    """``ast.get_docstring`` (limpio) del cuerpo de una función, clase o módulo."""
    primeras = sentencias(bloque)[:1]
    if not primeras or primeras[0].type != "expression_statement":
        return None
    valores = nombrados(primeras[0])
    if len(valores) != 1:
        return None
    valor = sin_envoltura(valores[0])
    if valor is None or valor.type not in ("string", "concatenated_string"):
        return None
    cadena = _cadena(valor)
    if not isinstance(cadena, _Constante) or not isinstance(cadena.valor, str):
        return None
    return inspect.cleandoc(cadena.valor)


def literal(nodo: Node | None) -> Any:
    """``ast.literal_eval`` de un nodo.

    Raises:
        NoEsLiteral: si el nodo no es un literal (por ejemplo, un nombre o una llamada).
    """
    nodo = sin_envoltura(nodo)
    if nodo is None:
        raise NoEsLiteral("no hay valor")
    tipo = nodo.type
    if tipo in ("integer", "float"):
        return _numero(nodo)
    if tipo in ("true", "false", "none", "ellipsis"):
        return {"true": True, "false": False, "none": None, "ellipsis": ...}[tipo]
    if tipo in ("string", "concatenated_string"):
        cadena = _cadena(nodo)
        if not isinstance(cadena, _Constante):
            raise NoEsLiteral("f-string")
        return cadena.valor
    if tipo in _TUPLAS:
        return tuple(literal(e) for e in _elementos(nodo))
    if tipo in _LISTAS:
        return [literal(e) for e in _elementos(nodo)]
    if tipo == "set":
        return {literal(e) for e in _elementos(nodo)}
    if tipo == "dictionary":
        resultado = {}
        for par in nombrados(nodo):
            if par.type != "pair":
                raise NoEsLiteral("desempaque en un diccionario")
            resultado[literal(campo(par, "key"))] = literal(campo(par, "value"))
        return resultado
    if tipo == "call":
        funcion = sin_envoltura(campo(nodo, "function"))
        args = campo(nodo, "arguments")
        if (
            funcion is not None
            and funcion.type == "identifier"
            and texto(funcion) == "set"
            and args is not None
            and args.type == "argument_list"
            and not nombrados(args)
        ):
            return set()
    if tipo == "unary_operator":
        return _con_signo(nodo)
    if tipo == "binary_operator":
        operador = texto(campo(nodo, "operator"))
        if operador in ("+", "-"):
            izquierdo = _con_signo(campo(nodo, "left"))
            derecho = _numero_literal(campo(nodo, "right"))
            if isinstance(izquierdo, (int, float)) and isinstance(derecho, complex):
                return izquierdo + derecho if operador == "+" else izquierdo - derecho
    raise NoEsLiteral(f"no es un literal: {tipo}")


def literal_de_texto(codigo: str) -> Any:
    """``ast.literal_eval`` de un texto.

    Raises:
        NoEsLiteral: si el texto no es una sola expresión literal.
    """
    nodo = expresion_de_texto(codigo.lstrip(" \t"))
    if nodo is None:
        raise NoEsLiteral("no es una expresión")
    return literal(nodo)


def expresion_de_texto(codigo: str) -> Node | None:
    """El nodo de ``codigo`` si es una sola expresión válida (``mode="eval"``)."""
    if codigo[:1] in (" ", "\t"):
        return None  # ast.parse(mode="eval") lo rechaza por sangría
    arbol = parsear(codigo)
    if error_de_sintaxis(arbol, codigo) is not None:
        return None
    todas = sentencias(arbol.root_node)
    if len(todas) != 1 or todas[0].type != "expression_statement":
        return None
    valores = nombrados(todas[0])
    if not valores or any(
        v.type in ("assignment", "augmented_assignment") for v in valores
    ):
        return None
    # «a, b» sin paréntesis: tree-sitter deja los elementos sueltos en la sentencia.
    return valores[0] if len(valores) == 1 else todas[0]


def es_constante_puntos(nodo: Node | None) -> bool:
    """Si el nodo es ``...`` (``ast.Constant(value=Ellipsis)``)."""
    nodo = sin_envoltura(nodo)
    return nodo is not None and nodo.type == "ellipsis"


def partes_subindice(nodo: Node | None) -> tuple[Node, bool, list[Node]] | None:
    """``(valor, es_tupla, elementos)`` de ``valor[...]``; None si no es un subíndice.

    Admite ``subscript`` y ``generic_type`` (así deja tree-sitter ``List[int]`` en las
    anotaciones). ``a[x, y]`` y ``a[(x, y)]`` son una tupla en ``ast``; ``a[x]`` no.
    """
    nodo = sin_envoltura(nodo)
    if nodo is None:
        return None
    if nodo.type == "subscript":
        valor = campo(nodo, "value")
        es_tupla, indices = elementos_subindice(nodo)
    elif nodo.type == "generic_type":
        internos = nombrados(nodo)
        parametro = next((h for h in internos if h.type == "type_parameter"), None)
        if not internos or parametro is None:
            return None
        valor = internos[0]
        es_tupla, indices = _indices(nombrados(parametro), parametro)
    else:
        return None
    if valor is None:
        return None
    return valor, es_tupla, indices


def elementos_subindice(subindice: Node) -> tuple[bool, list[Node]]:
    """``(es_tupla, elementos)`` del índice de un ``subscript``."""
    indices = [
        h
        for i, h in enumerate(subindice.children)
        if subindice.field_name_for_child(i) == "subscript"
    ]
    return _indices(indices, subindice)


def _indices(indices: list[Node], contenedor: Node) -> tuple[bool, list[Node]]:
    coma = any(h.type == "," for h in contenedor.children)
    if len(indices) == 1 and indices[0].type == "list_splat":
        return True, indices  # «a[*b]» es una tupla de un elemento en ast
    if len(indices) == 1 and not coma:
        unico = sin_envoltura(indices[0])
        if unico is not None and unico.type == "tuple":
            return True, _elementos(unico)
        return False, indices
    return True, indices


# --------------------------------------------------------------------------- #
# Literales
# --------------------------------------------------------------------------- #
def _numero(nodo: Node) -> int | float | complex:
    limpio = texto(nodo).replace("_", "")
    if limpio[-1:] in ("j", "J"):
        return complex(0, float(limpio[:-1]))
    if nodo.type == "float":
        return float(limpio)
    try:
        return int(limpio, 0)
    except ValueError:
        return int(limpio)  # «007» no es válido en Python 3, «000» sí


def _numero_literal(nodo: Node | None) -> int | float | complex:
    nodo = sin_envoltura(nodo)
    if nodo is None or nodo.type not in ("integer", "float"):
        raise NoEsLiteral("no es un número")
    return _numero(nodo)


def _con_signo(nodo: Node | None) -> int | float | complex:
    nodo = sin_envoltura(nodo)
    if nodo is not None and nodo.type == "unary_operator":
        operador = texto(campo(nodo, "operator"))
        if operador in ("+", "-"):
            valor = _numero_literal(campo(nodo, "argument"))
            return valor if operador == "+" else -valor
        raise NoEsLiteral("operador no literal")
    return _numero_literal(nodo)


def _elementos(nodo: Node) -> list[Node]:
    return nombrados(nodo)


# --------------------------------------------------------------------------- #
# Cadenas
# --------------------------------------------------------------------------- #
@dataclass
class _Constante:
    valor: str | bytes
    kind_u: bool = False


@dataclass
class _Formateado:
    """``ast.FormattedValue``: la parte ``{expr!c:formato}`` de una f-string."""

    expresion: Node
    conversion: str | None
    formato: list[str | _Formateado] | None


def _cadena(nodo: Node) -> _Constante | list[str | _Formateado]:
    """Valor de un literal de cadena: constante, o las partes de una f-string."""
    piezas = [nodo] if nodo.type == "string" else nombrados(nodo)
    piezas = [p for p in piezas if p.type == "string"]
    prefijos = [_prefijo_de(p) for p in piezas]
    if not any("f" in p for p in prefijos):
        if any("b" in p for p in prefijos):
            return _Constante(b"".join(_contenido_bytes(p) for p in piezas))
        return _Constante(
            "".join(_contenido_texto(p) for p in piezas), "u" in prefijos[0]
        )
    partes: list[str | _Formateado] = []
    for pieza, prefijo in zip(piezas, prefijos):
        if "f" in prefijo:
            partes.extend(_partes_fstring(pieza, prefijo))
        else:
            partes.append(_contenido_texto(pieza))
    return _unir(partes)


def _prefijo_de(cadena: Node) -> str:
    inicio = cadena.children[0] if cadena.children else None
    if inicio is None or inicio.type != "string_start":
        return ""
    return texto(inicio).rstrip("'\"").lower()


def _limites(cadena: Node) -> tuple[int, int]:
    """Bytes donde empieza y termina el contenido de la cadena, sin comillas.

    Se calculan con la comilla de apertura y no con el nodo de cierre: en una cadena
    cruda que termina en barras (``r'\\\\'``) tree-sitter deja el contenido dentro del
    token de cierre.
    """
    hijos_cadena = cadena.children
    if not hijos_cadena or hijos_cadena[0].type != "string_start":
        return cadena.start_byte, cadena.end_byte
    apertura = texto(hijos_cadena[0])
    comillas = len(apertura) - len(apertura.rstrip("'\""))
    return hijos_cadena[0].end_byte, max(
        hijos_cadena[0].end_byte, cadena.end_byte - comillas
    )


def _crudo(cadena: Node) -> str:
    """El texto entre las comillas de una cadena sin interpolaciones."""
    inicio, fin = _limites(cadena)
    return (cadena.text or b"")[
        inicio - cadena.start_byte : fin - cadena.start_byte
    ].decode("utf-8")


def _contenido_texto(cadena: Node) -> str:
    crudo = _crudo(cadena)
    return crudo if "r" in _prefijo_de(cadena) else _decodificar(crudo, False)


def _contenido_bytes(cadena: Node) -> bytes:
    crudo = _crudo(cadena)
    if "r" in _prefijo_de(cadena):
        return crudo.encode("latin-1", "backslashreplace")
    return _decodificar(crudo, True).encode("latin-1", "backslashreplace")


_ESCAPES = {
    "\\": "\\",
    "'": "'",
    '"': '"',
    "a": "\a",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
    "v": "\v",
}


def _decodificar(crudo: str, es_bytes: bool, llaves: bool = False) -> str:
    """Resuelve los escapes de un literal (y ``{{``/``}}`` si es una f-string)."""
    salida: list[str] = []
    i, total = 0, len(crudo)
    while i < total:
        caracter = crudo[i]
        if llaves and caracter in "{}" and crudo[i + 1 : i + 2] == caracter:
            salida.append(caracter)
            i += 2
            continue
        if caracter != "\\" or i + 1 >= total:
            salida.append(caracter)
            i += 1
            continue
        siguiente = crudo[i + 1]
        if siguiente == "\n":
            i += 2
        elif siguiente in _ESCAPES:
            salida.append(_ESCAPES[siguiente])
            i += 2
        elif siguiente in "01234567":
            fin = i + 2
            while fin < min(i + 4, total) and crudo[fin] in "01234567":
                fin += 1
            salida.append(chr(int(crudo[i + 1 : fin], 8)))
            i = fin
        elif siguiente == "x" and _hexadecimal(crudo[i + 2 : i + 4], 2):
            salida.append(chr(int(crudo[i + 2 : i + 4], 16)))
            i += 4
        elif (
            not es_bytes and siguiente == "u" and _hexadecimal(crudo[i + 2 : i + 6], 4)
        ):
            salida.append(chr(int(crudo[i + 2 : i + 6], 16)))
            i += 6
        elif (
            not es_bytes and siguiente == "U" and _hexadecimal(crudo[i + 2 : i + 10], 8)
        ):
            salida.append(chr(int(crudo[i + 2 : i + 10], 16)))
            i += 10
        elif not es_bytes and siguiente == "N" and crudo[i + 2 : i + 3] == "{":
            cierre = crudo.find("}", i + 3)
            try:
                salida.append(unicodedata.lookup(crudo[i + 3 : cierre]))
                i = cierre + 1
            except (KeyError, ValueError):
                salida.append("\\")
                i += 1
        else:
            salida.append("\\")
            i += 1
    return "".join(salida)


def _hexadecimal(digitos: str, cantidad: int) -> bool:
    return len(digitos) == cantidad and all(
        c in "0123456789abcdefABCDEF" for c in digitos
    )


def _partes_fstring(cadena: Node, prefijo: str) -> list[str | _Formateado]:
    crudo = "r" in prefijo
    partes: list[str | _Formateado] = []
    inicio, fin = _limites(cadena)
    interpolaciones = [h for h in cadena.children if h.type == "interpolation"]
    cursor = inicio
    for interpolacion in interpolaciones:
        partes.append(_tramo(cadena, cursor, interpolacion.start_byte, crudo))
        partes.extend(_interpolacion(interpolacion, crudo))
        cursor = interpolacion.end_byte
    partes.append(_tramo(cadena, cursor, fin, crudo))
    return partes


def _tramo(nodo: Node, desde: int, hasta: int, crudo: bool) -> str:
    """Texto literal entre dos interpolaciones de una f-string, ya decodificado."""
    bruto = (nodo.text or b"")[desde - nodo.start_byte : hasta - nodo.start_byte]
    valor = bruto.decode("utf-8")
    if crudo:
        return valor.replace("{{", "{").replace("}}", "}")
    return _decodificar(valor, False, llaves=True)


def _interpolacion(nodo: Node, crudo: bool) -> list[str | _Formateado]:
    expresion_nodo = campo(nodo, "expression")
    conversion_nodo = campo(nodo, "type_conversion")
    formato_nodo = campo(nodo, "format_specifier")
    conversion = texto(conversion_nodo)[1:] if conversion_nodo is not None else None
    formato = _formato(formato_nodo, crudo) if formato_nodo is not None else None
    partes: list[str | _Formateado] = []
    igual = next((h for h in nodo.children if h.type == "="), None)
    if igual is not None:
        # f"{x=}": ast agrega el texto «x=» y, sin conversión ni formato, usa repr.
        siguiente = igual.next_sibling
        fin = siguiente.start_byte if siguiente is not None else igual.end_byte
        bruto = (nodo.text or b"")[1 : fin - nodo.start_byte]  # «x = » con espacios
        partes.append(bruto.decode("utf-8"))
        if conversion is None and formato is None:
            conversion = "r"
    if expresion_nodo is not None:
        partes.append(_Formateado(expresion_nodo, conversion, formato))
    return partes


def _formato(nodo: Node, crudo: bool) -> list[str | _Formateado]:
    partes: list[str | _Formateado] = []
    cursor = nodo.start_byte
    for hijo in nodo.children:
        if hijo.type == ":" and hijo.start_byte == nodo.start_byte:
            cursor = hijo.end_byte
            continue
        if hijo.type == "format_expression":
            partes.append(_tramo(nodo, cursor, hijo.start_byte, crudo))
            partes.extend(_interpolacion(hijo, crudo))
            cursor = hijo.end_byte
    partes.append(_tramo(nodo, cursor, nodo.end_byte, crudo))
    return _unir(partes)


def _unir(partes: list[str | _Formateado]) -> list[str | _Formateado]:
    """Junta los textos seguidos y quita los vacíos, como ``ast.JoinedStr``."""
    resultado: list[str | _Formateado] = []
    for parte in partes:
        if isinstance(parte, str):
            if not parte:
                continue
            if resultado and isinstance(resultado[-1], str):
                resultado[-1] += parte
                continue
        resultado.append(parte)
    return resultado


def _ayuda_comillas(
    cadena: str, tipos: list[str] | tuple[str, ...], escapar_blancos: bool = False
) -> tuple[str, list[str]]:
    """``_Unparser._str_literal_helper``: el texto escapado y las comillas posibles."""

    def escapar(c: str) -> str:
        if not escapar_blancos and c in "\n\t":
            return c
        if c == "\\" or not c.isprintable():
            return c.encode("unicode_escape").decode("ascii")
        return c

    escapado = "".join(map(escapar, cadena))
    posibles = list(tipos)
    if "\n" in escapado:
        posibles = [q for q in posibles if q in _COMILLAS_TRIPLES]
    posibles = [q for q in posibles if q not in escapado]
    if not posibles:
        representacion = repr(cadena)
        comilla = next((q for q in tipos if representacion[0] in q), representacion[0])
        return representacion[1:-1], [comilla]
    if escapado:
        posibles.sort(key=lambda q: q[0] == escapado[-1])
        if posibles[0][0] == escapado[-1]:
            escapado = escapado[:-1] + "\\" + escapado[-1]
    return escapado, posibles


# --------------------------------------------------------------------------- #
# Operadores binarios
# --------------------------------------------------------------------------- #
@dataclass
class _Binaria:
    """Operación binaria reagrupada con las precedencias de Python."""

    operador: str
    izquierda: Node | _Binaria
    derecha: Node | _Binaria


def _reagrupar(nodo: Node) -> Node | _Binaria:
    """Vuelve a agrupar una cadena de operadores binarios sin paréntesis.

    La gramática de tree-sitter-python invierte la precedencia de ``^`` y ``&``:
    ``a ^ b & c`` queda ``(a ^ b) & c`` en lugar de ``a ^ (b & c)``. Se aplana la
    cadena en el orden del código y se agrupa de nuevo como lo hace Python.
    """
    operandos: list[Node] = []
    operadores: list[str] = []

    def aplanar(actual: Node) -> None:
        if actual.type == "binary_operator":
            aplanar(campo(actual, "left"))
            operadores.append(texto(campo(actual, "operator")))
            aplanar(campo(actual, "right"))
        else:
            operandos.append(actual)

    aplanar(nodo)
    posicion = 0

    def agrupar(minima: int) -> Node | _Binaria:
        nonlocal posicion
        izquierda: Node | _Binaria = operandos[posicion]
        while posicion < len(operadores):
            operador = operadores[posicion]
            propia = _BINARIOS.get(operador, _P.EXPR)
            if propia < minima:
                break
            posicion += 1
            derecha = agrupar(propia if operador == "**" else propia + 1)
            izquierda = _Binaria(operador, izquierda, derecha)
        return izquierda

    return agrupar(0)


# --------------------------------------------------------------------------- #
# Escritor (ast._Unparser)
# --------------------------------------------------------------------------- #
class _Escritor:
    def __init__(self, evitar_barras: bool = False) -> None:
        self.evitar_barras = evitar_barras

    def escribir(self, nodo: Node | _Binaria, precedencia: _P) -> str:
        if isinstance(nodo, _Binaria):
            return self._binaria(nodo, precedencia)
        tipo = nodo.type
        metodo = getattr(self, f"_n_{tipo}", None)
        if metodo is None:
            return texto(nodo)
        return metodo(nodo, precedencia)

    def _parentesis(self, texto_nodo: str, condicion: bool) -> str:
        return f"({texto_nodo})" if condicion else texto_nodo

    # --- envolturas ---------------------------------------------------------
    def _n_parenthesized_expression(self, nodo: Node, precedencia: _P) -> str:
        internos = nombrados(nodo)
        if len(internos) != 1:
            return texto(nodo)
        return self.escribir(internos[0], precedencia)

    _n_type = _n_parenthesized_expression

    # --- átomos -------------------------------------------------------------
    def _n_identifier(self, nodo: Node, precedencia: _P) -> str:
        return texto(nodo)

    def _n_true(self, nodo: Node, precedencia: _P) -> str:
        return "True"

    def _n_false(self, nodo: Node, precedencia: _P) -> str:
        return "False"

    def _n_none(self, nodo: Node, precedencia: _P) -> str:
        return "None"

    def _n_ellipsis(self, nodo: Node, precedencia: _P) -> str:
        return "..."

    def _n_integer(self, nodo: Node, precedencia: _P) -> str:
        valor = _numero(nodo)
        if isinstance(valor, (float, complex)):
            return (
                repr(valor)
                .replace("inf", _INFINITO)
                .replace("nan", f"({_INFINITO}-{_INFINITO})")
            )
        return repr(valor)

    _n_float = _n_integer

    def _n_string(self, nodo: Node, precedencia: _P) -> str:
        valor = _cadena(nodo)
        if isinstance(valor, _Constante):
            prefijo = "u" if valor.kind_u else ""
            if self.evitar_barras and isinstance(valor.valor, str):
                return prefijo + self._cadena_sin_barras(valor.valor)
            return prefijo + repr(valor.valor)
        return self._fstring(valor)

    _n_concatenated_string = _n_string

    def _cadena_sin_barras(self, valor: str, tipos: tuple[str, ...] = _COMILLAS) -> str:
        escapado, posibles = _ayuda_comillas(valor, tipos)
        return f"{posibles[0]}{escapado}{posibles[0]}"

    def _fstring(self, partes: list[str | _Formateado]) -> str:
        if self.evitar_barras:
            interno = "".join(self._interno(p) for p in partes)
            return "f" + self._cadena_sin_barras(interno)
        escritos: list[str] = []
        tipos: list[str] = list(_COMILLAS)
        for parte in partes:
            escapado, tipos = _ayuda_comillas(
                self._interno(parte), tipos, escapar_blancos=isinstance(parte, str)
            )
            escritos.append(escapado)
        return f"f{tipos[0]}{''.join(escritos)}{tipos[0]}"

    def _interno(self, parte: str | _Formateado) -> str:
        if isinstance(parte, str):
            return parte.replace("{", "{{").replace("}", "}}")
        interno = _Escritor(evitar_barras=True).escribir(
            parte.expresion, _P.TEST.siguiente()
        )
        salida = "{" + (" " if interno.startswith("{") else "") + interno
        if parte.conversion is not None:
            salida += f"!{parte.conversion}"
        if parte.formato is not None:
            salida += ":" + "".join(self._interno(p) for p in parte.formato)
        return salida + "}"

    # --- colecciones --------------------------------------------------------
    def _lista(self, elementos: list[Node]) -> str:
        return ", ".join(self.escribir(e, _P.TEST) for e in elementos)

    def _tupla(self, elementos: list[Node], precedencia: _P) -> str:
        if len(elementos) == 1:
            interno = self.escribir(elementos[0], _P.TEST) + ","
        else:
            interno = self._lista(elementos)
        return self._parentesis(interno, not elementos or precedencia > _P.TUPLE)

    def _n_tuple(self, nodo: Node, precedencia: _P) -> str:
        elementos = _elementos(nodo)
        if (
            nodo.type == "tuple_pattern"
            and len(elementos) == 1
            and not any(h.type == "," for h in nodo.children)
        ):
            # «for i, (x) in ...»: tree-sitter lo deja como tupla; es solo «x».
            return self.escribir(elementos[0], precedencia)
        return self._tupla(elementos, precedencia)

    _n_expression_list = _n_tuple
    _n_pattern_list = _n_tuple
    _n_tuple_pattern = _n_tuple
    _n_expression_statement = _n_tuple

    def _n_list(self, nodo: Node, precedencia: _P) -> str:
        return f"[{self._lista(_elementos(nodo))}]"

    _n_list_pattern = _n_list

    def _n_set(self, nodo: Node, precedencia: _P) -> str:
        return "{" + self._lista(_elementos(nodo)) + "}"

    def _n_dictionary(self, nodo: Node, precedencia: _P) -> str:
        items = []
        for elemento in nombrados(nodo):
            if elemento.type == "pair":
                clave = self.escribir(campo(elemento, "key"), _P.TEST)
                valor = self.escribir(campo(elemento, "value"), _P.TEST)
                items.append(f"{clave}: {valor}")
            else:
                items.append(self._doble_asterisco(elemento, _P.EXPR))
        return "{" + ", ".join(items) + "}"

    def _comprension(self, nodo: Node, precedencia: _P) -> str:
        abre, cierra = _COMPRENSIONES[nodo.type]
        cuerpo_nodo = campo(nodo, "body")
        if nodo.type == "dictionary_comprehension":
            clave = self.escribir(campo(cuerpo_nodo, "key"), _P.TEST)
            valor = self.escribir(campo(cuerpo_nodo, "value"), _P.TEST)
            salida = f"{clave}: {valor}"
        else:
            salida = self.escribir(cuerpo_nodo, _P.TEST)
        for clausula in nombrados(nodo)[1:]:
            if clausula.type == "for_in_clause":
                asincrono = any(h.type == "async" for h in clausula.children)
                objetivo = self._objetivo(campo(clausula, "left"))
                fuente = self.escribir(campo(clausula, "right"), _P.TEST.siguiente())
                salida += (
                    f" {'async for' if asincrono else 'for'} {objetivo} in {fuente}"
                )
            elif clausula.type == "if_clause":
                condicion = nombrados(clausula)[0]
                salida += " if " + self.escribir(condicion, _P.TEST.siguiente())
        return f"{abre}{salida}{cierra}"

    _n_list_comprehension = _comprension
    _n_set_comprehension = _comprension
    _n_generator_expression = _comprension
    _n_dictionary_comprehension = _comprension

    def _objetivo(self, nodo: Node | None) -> str:
        """Destino de un ``for``: varios nombres son una tupla sin paréntesis."""
        if nodo is None:
            return ""
        return self.escribir(nodo, _P.TUPLE)

    # --- operadores ---------------------------------------------------------
    def _n_binary_operator(self, nodo: Node, precedencia: _P) -> str:
        return self.escribir(_reagrupar(nodo), precedencia)

    def _binaria(self, nodo: _Binaria, precedencia: _P) -> str:
        operador = nodo.operador
        propia = _BINARIOS.get(operador, _P.EXPR)
        if operador == "**":
            izquierda, derecha = propia.siguiente(), propia
        else:
            izquierda, derecha = propia, propia.siguiente()
        salida = (
            f"{self.escribir(nodo.izquierda, izquierda)} {operador} "
            f"{self.escribir(nodo.derecha, derecha)}"
        )
        return self._parentesis(salida, precedencia > propia)

    def _n_unary_operator(self, nodo: Node, precedencia: _P) -> str:
        operador = texto(campo(nodo, "operator"))
        salida = operador + self.escribir(campo(nodo, "argument"), _P.FACTOR)
        return self._parentesis(salida, precedencia > _P.FACTOR)

    def _n_not_operator(self, nodo: Node, precedencia: _P) -> str:
        salida = "not " + self.escribir(campo(nodo, "argument"), _P.NOT)
        return self._parentesis(salida, precedencia > _P.NOT)

    def _n_boolean_operator(self, nodo: Node, precedencia: _P) -> str:
        operador = texto(campo(nodo, "operator"))
        valores = self._valores_bool(nodo, operador)
        actual = _P.AND if operador == "and" else _P.OR
        propia = actual
        escritos = []
        for valor in valores:
            actual = actual.siguiente()
            escritos.append(self.escribir(valor, actual))
        return self._parentesis(f" {operador} ".join(escritos), precedencia > propia)

    def _valores_bool(self, nodo: Node, operador: str) -> list[Node]:
        """``a or b or c`` es un solo ``BoolOp`` en ``ast`` (sin paréntesis de por medio)."""
        izquierdo = campo(nodo, "left")
        derecho = campo(nodo, "right")
        valores: list[Node] = []
        if (
            izquierdo is not None
            and izquierdo.type == "boolean_operator"
            and texto(campo(izquierdo, "operator")) == operador
        ):
            valores.extend(self._valores_bool(izquierdo, operador))
        elif izquierdo is not None:
            valores.append(izquierdo)
        if derecho is not None:
            valores.append(derecho)
        return valores

    def _n_comparison_operator(self, nodo: Node, precedencia: _P) -> str:
        partes = []
        for hijo in hijos(nodo):
            if hijo.is_named:
                partes.append(self.escribir(hijo, _P.CMP.siguiente()))
            else:  # operador: «not  in» queda «not in»
                partes.append(" " + " ".join(texto(hijo).split()) + " ")
        return self._parentesis("".join(partes), precedencia > _P.CMP)

    def _n_conditional_expression(self, nodo: Node, precedencia: _P) -> str:
        cuerpo_nodo, condicion, alternativa = nombrados(nodo)[:3]
        if cuerpo_nodo.type == "named_expression":
            # «(x := a if b else c)»: tree-sitter deja el ternario dentro del «:=»
            # al revés; en Python el «:=» abarca todo el ternario.
            salida = (
                f"{self.escribir(campo(cuerpo_nodo, 'name'), _P.ATOM)} := "
                f"({self.escribir(campo(cuerpo_nodo, 'value'), _P.TEST.siguiente())}"
                f" if {self.escribir(condicion, _P.TEST.siguiente())} else "
                f"{self.escribir(alternativa, _P.TEST)})"
            )
            return self._parentesis(salida, precedencia > _P.NAMED_EXPR)
        salida = (
            f"{self.escribir(cuerpo_nodo, _P.TEST.siguiente())} if "
            f"{self.escribir(condicion, _P.TEST.siguiente())} else "
            f"{self.escribir(alternativa, _P.TEST)}"
        )
        return self._parentesis(salida, precedencia > _P.TEST)

    def _n_named_expression(self, nodo: Node, precedencia: _P) -> str:
        salida = (
            f"{self.escribir(campo(nodo, 'name'), _P.ATOM)} := "
            f"{self.escribir(campo(nodo, 'value'), _P.ATOM)}"
        )
        return self._parentesis(salida, precedencia > _P.NAMED_EXPR)

    def _n_lambda(self, nodo: Node, precedencia: _P) -> str:
        argumentos_texto = self.argumentos(parametros(campo(nodo, "parameters")))
        salida = "lambda" + (f" {argumentos_texto}" if argumentos_texto else "")
        salida += ": " + self.escribir(campo(nodo, "body"), _P.TEST)
        return self._parentesis(salida, precedencia > _P.TEST)

    def _n_await(self, nodo: Node, precedencia: _P) -> str:
        internos = nombrados(nodo)
        salida = "await" + (
            " " + self.escribir(internos[0], _P.ATOM) if internos else ""
        )
        return self._parentesis(salida, precedencia > _P.AWAIT)

    def _n_yield(self, nodo: Node, precedencia: _P) -> str:
        desde = any(h.type == "from" for h in nodo.children)
        internos = nombrados(nodo)
        salida = "yield from " if desde else "yield"
        if internos:
            valor = self.escribir(internos[0], _P.ATOM)
            salida = salida + valor if desde else f"{salida} {valor}"
        return self._parentesis(salida, precedencia > _P.YIELD)

    def _n_list_splat(self, nodo: Node, precedencia: _P) -> str:
        return "*" + self.escribir(nombrados(nodo)[0], _P.EXPR)

    _n_list_splat_pattern = _n_list_splat

    def _doble_asterisco(self, nodo: Node, precedencia: _P) -> str:
        return "**" + self.escribir(nombrados(nodo)[0], precedencia)

    # --- acceso -------------------------------------------------------------
    def _n_attribute(self, nodo: Node, precedencia: _P) -> str:
        objeto = campo(nodo, "object")
        salida = self.escribir(objeto, _P.ATOM)
        base = sin_envoltura(objeto)
        if base is not None and (
            base.type in ("true", "false")
            or (base.type == "integer" and isinstance(_numero(base), int))
        ):
            salida += " "  # «3 .real»: «3.real» sería un número mal escrito
        return f"{salida}.{texto(campo(nodo, 'attribute'))}"

    def _n_call(self, nodo: Node, precedencia: _P) -> str:
        funcion = self.escribir(campo(nodo, "function"), _P.ATOM)
        argumentos_nodo = campo(nodo, "arguments")
        if argumentos_nodo is None:
            return f"{funcion}()"
        if argumentos_nodo.type == "generator_expression":
            return f"{funcion}({self.escribir(argumentos_nodo, _P.TEST)})"
        posicionales, por_nombre = [], []
        for argumento in nombrados(argumentos_nodo):
            if argumento.type == "keyword_argument":
                valor = self.escribir(campo(argumento, "value"), _P.TEST)
                por_nombre.append(f"{texto(campo(argumento, 'name'))}={valor}")
            elif argumento.type == "dictionary_splat":
                por_nombre.append(self._doble_asterisco(argumento, _P.TEST))
            else:
                posicionales.append(self.escribir(argumento, _P.TEST))
        return f"{funcion}({', '.join(posicionales + por_nombre)})"

    def _n_subscript(self, nodo: Node, precedencia: _P) -> str:
        partes = partes_subindice(nodo)
        if partes is None:
            return texto(nodo)
        valor_nodo, es_tupla, indices = partes
        valor = self.escribir(valor_nodo, _P.ATOM)
        if es_tupla and indices:
            if len(indices) == 1:
                interno = self.escribir(indices[0], _P.TEST) + ","
            else:
                interno = self._lista(indices)
        elif es_tupla:
            interno = "()"
        else:
            interno = self.escribir(indices[0], _P.TEST)
        return f"{valor}[{interno}]"

    _n_generic_type = _n_subscript

    def _n_union_type(self, nodo: Node, precedencia: _P) -> str:
        """``A | B`` en una anotación: un ``BinOp`` con ``|`` en ``ast``.

        tree-sitter agrupa ``A | B | C`` por la derecha; ``ast``, por la izquierda.
        """
        operandos = self._operandos_union(nodo)
        if len(operandos) < 2:
            return texto(nodo)
        salida = " | ".join(
            self.escribir(o, _P.EXPR if i == 0 else _P.EXPR.siguiente())
            for i, o in enumerate(operandos)
        )
        return self._parentesis(salida, precedencia > _P.EXPR)

    def _operandos_union(self, nodo: Node) -> list[Node]:
        """Operandos de una cadena de ``|`` sin paréntesis (``union_type`` o ``BinOp``)."""
        if nodo.type == "binary_operator":
            internos = [campo(nodo, "left"), campo(nodo, "right")]
        else:
            internos = nombrados(nodo)
        operandos: list[Node] = []
        for interno in internos:
            if interno is None:
                continue
            base = nombrados(interno)[0] if interno.type == "type" else interno
            if base.type == "union_type" or (
                base.type == "binary_operator" and texto(campo(base, "operator")) == "|"
            ):
                operandos.extend(self._operandos_union(base))
            else:
                operandos.append(interno)
        return operandos

    def _n_splat_type(self, nodo: Node, precedencia: _P) -> str:
        internos = nombrados(nodo)
        asteriscos = "**" if any(h.type == "**" for h in nodo.children) else "*"
        if not internos:
            return texto(nodo)
        return asteriscos + self.escribir(internos[0], _P.EXPR)

    def _n_member_type(self, nodo: Node, precedencia: _P) -> str:
        internos = nombrados(nodo)
        if len(internos) != 2:
            return texto(nodo)
        return f"{self.escribir(internos[0], _P.ATOM)}.{texto(internos[1])}"

    def _n_slice(self, nodo: Node, precedencia: _P) -> str:
        secciones: list[Node | None] = [None]
        for hijo in hijos(nodo):
            if hijo.type == ":":
                secciones.append(None)
            elif hijo.is_named:
                secciones[-1] = hijo
        inferior = secciones[0]
        superior = secciones[1] if len(secciones) > 1 else None
        paso = secciones[2] if len(secciones) > 2 else None
        salida = self.escribir(inferior, _P.TEST) if inferior is not None else ""
        salida += ":"
        if superior is not None:
            salida += self.escribir(superior, _P.TEST)
        if paso is not None:
            salida += ":" + self.escribir(paso, _P.TEST)
        return salida

    # --- argumentos ---------------------------------------------------------
    def _arg(self, parametro: Parametro) -> str:
        if parametro.tipo is None:
            return parametro.nombre
        return f"{parametro.nombre}: {self.escribir(parametro.tipo, _P.TEST)}"

    def argumentos(self, lista: list[Parametro]) -> str:
        posicionales = [p for p in lista if p.clase in (POSICIONAL_SOLO, POSICIONAL)]
        solo_posicion = sum(1 for p in lista if p.clase == POSICIONAL_SOLO)
        varargs = next((p for p in lista if p.clase == VARARGS), None)
        solo_nombre = [p for p in lista if p.clase == SOLO_NOMBRE]
        kwargs = next((p for p in lista if p.clase == KWARGS), None)
        salida = ""
        primero = True
        for indice, parametro in enumerate(posicionales, 1):
            salida += "" if primero else ", "
            primero = False
            salida += self._arg(parametro)
            if parametro.defecto is not None:
                salida += "=" + self.escribir(parametro.defecto, _P.TEST)
            if indice == solo_posicion:
                salida += ", /"
        if varargs is not None or solo_nombre:
            salida += "" if primero else ", "
            primero = False
            salida += "*"
            if varargs is not None:
                salida += self._arg(varargs)
        for parametro in solo_nombre:
            salida += ", " + self._arg(parametro)
            if parametro.defecto is not None:
                salida += "=" + self.escribir(parametro.defecto, _P.TEST)
        if kwargs is not None:
            salida += "" if primero else ", "
            salida += "**" + self._arg(kwargs)
        return salida
