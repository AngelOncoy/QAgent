"""Árbol de sintaxis de Python con tree-sitter (TA-16, ADR-009).

Base común de todo lo que lee el código del usuario: el analizador (EN-02, EN-14), el
contexto del Generator, el aislamiento de manejadores para mutmut y las huellas de la
regresión. Solo parsea: nunca importa ni ejecuta el código.

tree-sitter tolera los errores de sintaxis (deja nodos ``ERROR`` o ``MISSING`` y sigue)
y además acepta algunas construcciones que Python 3 rechaza, como ``print "x"``.
:func:`error_de_sintaxis` las detecta para que un archivo inválido se siga reportando
en ``errores`` como hacía ``ast.parse``.

El parser de Python vive aquí y no en ``qagent.lenguajes.treesitter``: ese paquete
importa ``qagent.analysis`` (el adaptador de Python delega en él), así que importarlo
desde aquí sería circular.
"""

from __future__ import annotations

import functools
import hashlib
import threading
from collections.abc import Iterator
from dataclasses import dataclass

import tree_sitter_python
from tree_sitter import Language, Node, Parser, Tree

#: Nodos que abren un ámbito propio: lo que hay dentro no es de la función que los contiene.
NODOS_DEFINICION = frozenset(
    {"function_definition", "class_definition", "decorated_definition"}
)
_ENVOLTURAS = frozenset({"parenthesized_expression", "type"})
#: Nodos que tree-sitter intercala en cualquier lugar y que no son código.
_EXTRAS = frozenset({"comment", "line_continuation"})
_local = threading.local()


@functools.cache
def _lenguaje() -> Language:
    return Language(tree_sitter_python.language())


def _parser() -> Parser:
    """Un parser por hilo: el análisis puede correr mientras se arma el sandbox (TA-15)."""
    parser = getattr(_local, "parser", None)
    if parser is None:
        parser = _local.parser = Parser(_lenguaje())
    return parser


def parsear(fuente: str) -> Tree:
    """Parsea código Python (texto ya decodificado) sin ejecutarlo."""
    return _parser().parse(fuente.encode("utf-8"))


# --------------------------------------------------------------------------- #
# Ayudas sobre nodos
# --------------------------------------------------------------------------- #
def texto(nodo: Node) -> str:
    """Texto fuente exacto del nodo."""
    return (nodo.text or b"").decode("utf-8")


def hijos(nodo: Node) -> list[Node]:
    """Hijos del nodo sin comentarios ni continuaciones de línea."""
    return [h for h in nodo.children if h.type not in _EXTRAS]


def nombrados(nodo: Node) -> list[Node]:
    """Hijos con nombre del nodo, sin comentarios ni continuaciones de línea."""
    return [h for h in nodo.named_children if h.type not in _EXTRAS]


def campo(nodo: Node, nombre: str) -> Node | None:
    return nodo.child_by_field_name(nombre)


def sin_envoltura(nodo: Node | None) -> Node | None:
    """Quita paréntesis y la envoltura ``type`` de las anotaciones.

    ``ast`` no conserva los paréntesis: ``(app).get`` es lo mismo que ``app.get``.
    """
    while nodo is not None and nodo.type in _ENVOLTURAS:
        internos = nombrados(nodo)
        if len(internos) != 1:
            break
        nodo = internos[0]
    return nodo


def linea(nodo: Node) -> int:
    """Línea (desde 1) donde empieza el nodo."""
    return nodo.start_point.row + 1


def ultimo_hoja(nodo: Node) -> Node:
    """Último nodo con contenido real (sin comentarios) dentro de ``nodo``."""
    actual = nodo
    while True:
        internos = [h for h in hijos(actual) if h.end_byte > h.start_byte]
        if not internos:
            return actual
        actual = internos[-1]


def linea_fin(nodo: Node) -> int:
    """Última línea con código del nodo, como ``end_lineno`` de ``ast``.

    tree-sitter puede dejar dentro del bloque los comentarios que lo cierran;
    ``ast`` termina en la última sentencia.
    """
    return ultimo_hoja(nodo).end_point.row + 1


def sentencias(bloque: Node | None) -> list[Node]:
    """Sentencias de un módulo o de un bloque, en orden."""
    return [] if bloque is None else nombrados(bloque)


def definicion(nodo: Node) -> Node:
    """La función o clase de un ``decorated_definition``; el mismo nodo si no lo es."""
    if nodo.type == "decorated_definition":
        interna = campo(nodo, "definition")
        if interna is not None:
            return interna
    return nodo


def es_funcion(nodo: Node) -> bool:
    return definicion(nodo).type == "function_definition"


def es_clase(nodo: Node) -> bool:
    return definicion(nodo).type == "class_definition"


def nombre(nodo: Node) -> str:
    """Nombre de una función o clase (admite el ``decorated_definition``)."""
    identificador = campo(definicion(nodo), "name")
    return "" if identificador is None else texto(identificador)


def cuerpo(nodo: Node) -> Node | None:
    """Bloque del cuerpo de una función, clase o sentencia compuesta."""
    return campo(definicion(nodo), "body")


def decoradores(funcion: Node) -> list[Node]:
    """Expresiones de los decoradores de una función o clase, en orden."""
    padre = funcion.parent
    if padre is None or padre.type != "decorated_definition":
        return []
    return [
        expresion
        for decorador in nombrados(padre)
        if decorador.type == "decorator"
        for expresion in nombrados(decorador)[:1]
    ]


def nodos_decorador(funcion: Node) -> list[Node]:
    """Nodos ``decorator`` (con su ``@``) de una función o clase."""
    padre = funcion.parent
    if padre is None or padre.type != "decorated_definition":
        return []
    return [d for d in nombrados(padre) if d.type == "decorator"]


def es_async(funcion: Node) -> bool:
    """Si la función, el ``for`` o el ``with`` es asíncrono."""
    return any(h.type == "async" for h in definicion(funcion).children)


def recorrer(nodo: Node) -> Iterator[Node]:
    """Todos los nodos bajo ``nodo`` (incluido), en orden del código."""
    pendientes = [nodo]
    while pendientes:
        actual = pendientes.pop()
        yield actual
        pendientes.extend(reversed(actual.children))


def huella_de_definicion(definicion_nodo: Node) -> str:
    """SHA-256 de la estructura de una función o clase, con sus decoradores.

    Cambia si cambia el código o el docstring, y no si cambian los comentarios, la
    sangría, los espacios o la línea donde está (como pasaba con ``ast.dump``).
    """
    padre = definicion_nodo.parent
    raiz = (
        padre
        if padre is not None and padre.type == "decorated_definition"
        else definicion_nodo
    )
    partes: list[str] = []
    pendientes: list[Node | str] = [raiz]
    while pendientes:
        actual = pendientes.pop()
        if isinstance(actual, str):
            partes.append(actual)
        elif actual.type in _EXTRAS:
            continue
        elif actual.type == "string" or actual.child_count == 0:
            partes.append(f"{actual.type}:{texto(actual)}")
        else:
            partes.append(f"({actual.type}")
            pendientes.append(")")
            pendientes.extend(reversed(actual.children))
    return hashlib.sha256("\x1f".join(partes).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Importacion:
    """Un ``import`` o ``from ... import``, como ``ast.Import`` y ``ast.ImportFrom``."""

    desde: bool
    nivel: int
    modulo: str | None
    #: (nombre, alias); el nombre es ``*`` en ``from x import *``.
    nombres: tuple[tuple[str, str | None], ...]


def _punteado(nodo: Node) -> str:
    return ".".join(texto(h) for h in nombrados(nodo) if h.type == "identifier")


def importacion(nodo: Node) -> Importacion | None:
    """Describe una sentencia de import; None si ``nodo`` no lo es."""
    if nodo.type not in (
        "import_statement",
        "import_from_statement",
        "future_import_statement",
    ):
        return None
    nombres: list[tuple[str, str | None]] = []
    for indice, hijo in enumerate(nodo.children):
        if hijo.type == "wildcard_import":
            nombres.append(("*", None))
        elif nodo.field_name_for_child(indice) == "name":
            if hijo.type == "aliased_import":
                original, alias = campo(hijo, "name"), campo(hijo, "alias")
                nombres.append(
                    (
                        _punteado(original) if original is not None else "",
                        texto(alias) if alias is not None else None,
                    )
                )
            else:
                nombres.append((_punteado(hijo), None))
    if nodo.type == "import_statement":
        return Importacion(False, 0, None, tuple(nombres))
    if nodo.type == "future_import_statement":
        return Importacion(True, 0, "__future__", tuple(nombres))
    modulo_nodo = campo(nodo, "module_name")
    nivel, modulo = 0, None
    if modulo_nodo is not None and modulo_nodo.type == "relative_import":
        prefijo = next(
            (h for h in modulo_nodo.children if h.type == "import_prefix"), None
        )
        nivel = texto(prefijo).count(".") if prefijo is not None else 0
        punteado = next(
            (h for h in nombrados(modulo_nodo) if h.type == "dotted_name"), None
        )
        modulo = _punteado(punteado) if punteado is not None else None
    elif modulo_nodo is not None:
        modulo = _punteado(modulo_nodo)
    return Importacion(True, nivel, modulo, tuple(nombres))


# --------------------------------------------------------------------------- #
# Parámetros
# --------------------------------------------------------------------------- #
#: Clases de parámetro, en el orden en que pueden aparecer en una firma.
POSICIONAL_SOLO = "posicional_solo"
POSICIONAL = "posicional"
VARARGS = "varargs"
SOLO_NOMBRE = "solo_nombre"
KWARGS = "kwargs"


@dataclass(frozen=True)
class Parametro:
    """Un parámetro de una función o ``lambda``, como lo describe ``ast.arguments``."""

    nombre: str
    clase: str
    tipo: Node | None
    defecto: Node | None
    nodo: Node


def parametros(nodo: Node | None) -> list[Parametro]:
    """Parámetros de un nodo ``parameters`` o ``lambda_parameters``, en orden."""
    resultado: list[Parametro] = []
    if nodo is None:
        return resultado
    solo_nombre = False
    for hijo in nombrados(nodo):
        tipo_nodo = hijo.type
        if tipo_nodo == "positional_separator":
            resultado = [
                Parametro(p.nombre, POSICIONAL_SOLO, p.tipo, p.defecto, p.nodo)
                if p.clase == POSICIONAL
                else p
                for p in resultado
            ]
            continue
        if tipo_nodo == "keyword_separator":
            solo_nombre = True
            continue
        anotacion = campo(hijo, "type")
        defecto = campo(hijo, "value")
        objetivo = hijo
        if tipo_nodo in ("typed_parameter",):
            objetivo = nombrados(hijo)[0]
        elif tipo_nodo in ("default_parameter", "typed_default_parameter"):
            objetivo = campo(hijo, "name") or hijo
        if objetivo.type == "list_splat_pattern":
            solo_nombre = True
            clase = VARARGS
            objetivo = nombrados(objetivo)[0] if nombrados(objetivo) else objetivo
        elif objetivo.type == "dictionary_splat_pattern":
            clase = KWARGS
            objetivo = nombrados(objetivo)[0] if nombrados(objetivo) else objetivo
        else:
            clase = SOLO_NOMBRE if solo_nombre else POSICIONAL
        resultado.append(Parametro(texto(objetivo), clase, anotacion, defecto, hijo))
    return resultado


# --------------------------------------------------------------------------- #
# Errores de sintaxis
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ErrorSintaxis:
    """Primer error de sintaxis de un archivo, como lo reportaba ``ast.parse``."""

    tipo: str  # "SyntaxError" o "IndentationError"
    linea: int
    mensaje: str


def error_de_sintaxis(arbol: Tree, fuente: str) -> ErrorSintaxis | None:
    """El primer error de sintaxis del árbol, o None si el código es válido.

    Además de los nodos ``ERROR``/``MISSING`` de tree-sitter, detecta lo que la
    gramática acepta pero Python 3 rechaza: ``print``/``exec`` de Python 2, ``<>``,
    ``except A, e``, un ``:=`` suelto, parámetros sin valor por defecto después de uno
    con valor, ``*`` sin parámetros por nombre, argumentos posicionales después de uno
    por nombre, bloques vacíos y sangría inconsistente.
    """
    if "\x00" in fuente:
        fila = fuente[: fuente.index("\x00")].count("\n")
        return ErrorSintaxis(
            "SyntaxError", fila + 1, "el código no puede tener bytes nulos"
        )
    errores: list[ErrorSintaxis] = []
    lineas = fuente.encode("utf-8").split(b"\n")
    for nodo in recorrer(arbol.root_node):
        error = _revisar(nodo, lineas)
        if error is not None:
            errores.append(error)
    if not errores:
        return None
    return min(errores, key=lambda e: e.linea)


def validar(arbol: Tree, fuente: str, archivo: str = "<desconocido>") -> None:
    """Lanza ``SyntaxError`` (o ``IndentationError``) si el código no es válido.

    Mismas excepciones que ``ast.parse``, con ``lineno`` y ``msg``, para que quien las
    reporte no cambie.
    """
    error = error_de_sintaxis(arbol, fuente)
    if error is None:
        return
    clase = IndentationError if error.tipo == "IndentationError" else SyntaxError
    raise clase(error.mensaje, (archivo, error.linea, 0, None))


def _revisar(nodo: Node, lineas: list[bytes]) -> ErrorSintaxis | None:
    tipo = nodo.type
    if nodo.is_missing:
        return ErrorSintaxis("SyntaxError", linea(nodo), f"falta «{tipo}»")
    if tipo == "ERROR":
        return ErrorSintaxis("SyntaxError", linea(nodo), "sintaxis inválida")
    if tipo in ("print_statement", "exec_statement"):
        return ErrorSintaxis(
            "SyntaxError", linea(nodo), f"falta el paréntesis de {tipo[:-10]}(...)"
        )
    if tipo == "comparison_operator" and any(h.type == "<>" for h in nodo.children):
        return ErrorSintaxis("SyntaxError", linea(nodo), "el operador <> no existe")
    if tipo == "except_clause" and any(h.type == "," for h in nodo.children):
        return ErrorSintaxis(
            "SyntaxError", linea(nodo), "varias excepciones van entre paréntesis"
        )
    if tipo == "expression_statement":
        primero = nombrados(nodo)[:1]
        if primero and primero[0].type == "named_expression":
            return ErrorSintaxis("SyntaxError", linea(nodo), "«:=» suelto")
    if tipo in ("parameters", "lambda_parameters"):
        return _revisar_parametros(nodo)
    if tipo == "argument_list":
        return _revisar_argumentos(nodo)
    if tipo == "concatenated_string":
        prefijos = {"b" in _prefijo(h) for h in nombrados(nodo) if h.type == "string"}
        if len(prefijos) > 1:
            return ErrorSintaxis(
                "SyntaxError", linea(nodo), "no se pueden unir bytes y texto"
            )
    if tipo == "block" and not sentencias(nodo):
        return ErrorSintaxis(
            "IndentationError", _linea_siguiente(nodo), "se esperaba un bloque sangrado"
        )
    if tipo in ("block", "module"):
        return _revisar_sangria(nodo, lineas)
    return None


def _prefijo(cadena: Node) -> str:
    inicio = cadena.children[0] if cadena.children else None
    if inicio is None or inicio.type != "string_start":
        return ""
    return texto(inicio).rstrip("'\"").lower()


def _revisar_parametros(nodo: Node) -> ErrorSintaxis | None:
    con_defecto = solo_nombre = False
    asterisco: Node | None = None
    for hijo in nombrados(nodo):
        if hijo.type == "keyword_separator":
            asterisco = hijo
            solo_nombre = True
            continue
        if asterisco is not None and hijo.type != "dictionary_splat_pattern":
            asterisco = None  # el «*» suelto ya tiene un parámetro por nombre
        es_splat = hijo.type in ("list_splat_pattern", "dictionary_splat_pattern") or (
            hijo.type == "typed_parameter"
            and nombrados(hijo)[0].type
            in ("list_splat_pattern", "dictionary_splat_pattern")
        )
        if es_splat or solo_nombre:
            solo_nombre = True
            continue
        if hijo.type in ("default_parameter", "typed_default_parameter"):
            con_defecto = True
        elif hijo.type in ("identifier", "typed_parameter") and con_defecto:
            return ErrorSintaxis(
                "SyntaxError",
                linea(hijo),
                "un parámetro sin valor por defecto sigue a uno con valor",
            )
    if asterisco is not None:
        return ErrorSintaxis(
            "SyntaxError", linea(asterisco), "después de «*» van parámetros por nombre"
        )
    return None


def _revisar_argumentos(nodo: Node) -> ErrorSintaxis | None:
    por_nombre = desempaque_dict = False
    for hijo in nombrados(nodo):
        if hijo.type == "keyword_argument":
            por_nombre = True
        elif hijo.type == "dictionary_splat":
            desempaque_dict = True
        elif hijo.type == "list_splat":
            if desempaque_dict:
                return ErrorSintaxis(
                    "SyntaxError", linea(hijo), "«*» después de «**» en una llamada"
                )
        elif por_nombre or desempaque_dict:
            return ErrorSintaxis(
                "SyntaxError",
                linea(hijo),
                "un argumento posicional sigue a uno por nombre",
            )
    return None


def _linea_siguiente(bloque: Node) -> int:
    """Línea donde Python esperaba el bloque: la del primer código que le sigue."""
    actual: Node | None = bloque
    while actual is not None:
        siguiente = actual.next_sibling
        while siguiente is not None and siguiente.type in _EXTRAS:
            siguiente = siguiente.next_sibling
        if siguiente is not None:
            return linea(siguiente)
        actual = actual.parent
    anterior = bloque.prev_sibling
    return linea(anterior) if anterior is not None else linea(bloque)


def _revisar_sangria(nodo: Node, lineas: list[bytes]) -> ErrorSintaxis | None:
    """Las sentencias que empiezan una línea deben tener la misma sangría."""
    referencia = 0 if nodo.type == "module" else None
    for sentencia in sentencias(nodo):
        fila, columna = sentencia.start_point
        if lineas[fila][:columna].strip():
            continue  # comparte línea con otra sentencia («a; b» o «if x: a»)
        if referencia is None:
            referencia = columna
        elif columna != referencia:
            mensaje = (
                "sangría inesperada"
                if columna > referencia
                else "la sangría no coincide con ningún nivel"
            )
            return ErrorSintaxis("IndentationError", fila + 1, mensaje)
    return None
