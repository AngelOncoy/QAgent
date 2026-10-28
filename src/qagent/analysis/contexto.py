"""Contexto estático de una función para el Generator (tree-sitter, nunca se importa).

El Generator recibe el contrato del Planner, pero sin ver el módulo no sabe qué
importar ni qué simular: por ejemplo, que `decode_token` usa `Config.JWT_SECRET_KEY`
y `pyjwt`, o que PyJWT no está instalado en el sandbox. Este módulo junta, leyendo el
archivo con tree-sitter (TA-16), lo mínimo para escribir un test que se pueda
ejecutar:

- los `import` del módulo;
- los nombres globales del módulo que usa la función (a simular con `mock.patch`);
- el código de la función;
- los paquetes del `requirements.txt` del proyecto (los que tendrá el sandbox).

El valor esperado de cada caso **no** sale de aquí: sigue saliendo del contrato
(firma, tipos y docstring), y el Reviewer rechaza cualquier aserción que se aparte.
"""

from __future__ import annotations

import tokenize
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from tree_sitter import Node, Tree

from qagent.analysis import arbol_ts, texto_ts
from qagent.analysis.arbol_ts import campo, definicion, nombrados, sentencias, texto

#: Topes para no inflar el prompt (tokens) con módulos o funciones enormes.
MAX_IMPORTS = 40
MAX_CARACTERES_CODIGO = 6000
MAX_PAQUETES = 40
#: Lo que siempre trae la imagen base del sandbox (src/qagent/sandbox/Dockerfile).
PAQUETES_BASE = ("pytest", "pytest-cov", "coverage", "mutmut", "httpx")


@dataclass(frozen=True)
class ContextoFuncion:
    """Lo que el Generator necesita saber del módulo para escribir el test.

    Atributos:
        imports: sentencias `import` / `from ... import` del módulo, en orden.
        globales_usados: nombres definidos o importados en el módulo que la función
            usa (candidatos a simular).
        codigo: código fuente de la función (recortado si es muy largo).
        paquetes: paquetes que instala el sandbox según `requirements.txt`; vacío si
            el proyecto no tiene ese archivo.
    """

    imports: list[str] = field(default_factory=list)
    globales_usados: list[str] = field(default_factory=list)
    codigo: str = ""
    paquetes: list[str] = field(default_factory=list)


def contexto_de_funcion(
    raiz: str | Path, modulo: str, nombre: str
) -> ContextoFuncion | None:
    """Contexto de la función `nombre` del archivo `modulo` (relativo a `raiz`).

    Returns:
        El contexto, o None si el archivo no se puede leer, no es Python válido o la
        función no está en el nivel superior del módulo. Nunca lanza excepciones:
        sin contexto, el Generator trabaja solo con el contrato, como antes.
    """
    ruta = Path(raiz) / modulo
    try:
        with tokenize.open(ruta) as archivo:  # respeta BOM y cookie de codificación
            fuente = archivo.read()
        arbol = arbol_ts.parsear(fuente)
        arbol_ts.validar(arbol, fuente, modulo)
    except (OSError, SyntaxError, ValueError, UnicodeDecodeError):
        return None
    funcion = next(
        (
            definicion(nodo)
            for nodo in sentencias(arbol.root_node)
            if arbol_ts.es_funcion(nodo) and arbol_ts.nombre(nodo) == nombre
        ),
        None,
    )
    if funcion is None:
        return None
    # Desde el `def` (sin decoradores) hasta la última sentencia, como
    # ast.get_source_segment: los comentarios que cierran el bloque no cuentan.
    fin = arbol_ts.ultimo_hoja(funcion).end_byte
    codigo = fuente.encode("utf-8")[funcion.start_byte : fin].decode("utf-8")
    if len(codigo) > MAX_CARACTERES_CODIGO:
        codigo = codigo[:MAX_CARACTERES_CODIGO] + "\n# […recortado…]"
    return ContextoFuncion(
        imports=_imports(arbol)[:MAX_IMPORTS],
        globales_usados=_globales_usados(arbol, funcion),
        codigo=codigo,
        paquetes=paquetes_del_sandbox(raiz),
    )


def paquetes_del_sandbox(raiz: str | Path) -> list[str]:
    """Paquetes del `requirements.txt` de la raíz (sin comentarios ni opciones de pip)."""
    try:
        lineas = (Path(raiz) / "requirements.txt").read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return []
    paquetes: list[str] = []
    for linea in lineas.splitlines():
        texto_linea = linea.split("#", 1)[0].strip()
        if texto_linea and not texto_linea.startswith("-"):
            paquetes.append(texto_linea)
    return paquetes[:MAX_PAQUETES]


def _imports(arbol: Tree) -> list[str]:
    """Los imports del módulo, en el orden en que los recorre ``ast.walk``."""
    nivel_modulo = _de_nivel_modulo(arbol)
    imports = []
    for nodo in _a_lo_ancho(arbol.root_node):
        importado = arbol_ts.importacion(nodo)
        if importado is not None and nodo.id in nivel_modulo:
            imports.append(texto_ts.sentencia_import(importado))
    return imports


def _de_nivel_modulo(arbol: Tree) -> set[int]:
    """Ids de los nodos del módulo: su cuerpo y todo lo que hay en sus `try`/`if`.

    Un `try` con `except*` no cuenta, como tampoco contaba `ast.TryStar`.
    """
    ids: set[int] = set()
    for sentencia in sentencias(arbol.root_node):
        ids.add(sentencia.id)
        ids.add(definicion(sentencia).id)
        if sentencia.type == "expression_statement":  # «a = 1» es la sentencia en ast
            ids.update(h.id for h in nombrados(sentencia))
        es_try = sentencia.type == "try_statement" and not any(
            h.type == "except_group_clause" for h in sentencia.children
        )
        if sentencia.type == "if_statement" or es_try:
            ids.update(n.id for n in arbol_ts.recorrer(sentencia))
    return ids


def _a_lo_ancho(raiz: Node) -> Iterator[Node]:
    """Sentencias del módulo a lo ancho, en el orden de ``ast.walk``.

    Solo importan las sentencias: un import no puede estar dentro de una expresión.
    Los niveles imitan a ``ast``: un ``elif`` es un ``if`` dentro del ``else`` y cada
    ``except`` es un nodo con su propio cuerpo.
    """
    cola: deque[Node] = deque([raiz])
    while cola:
        nodo = cola.popleft()
        yield nodo
        cola.extend(_hijos_sentencia(nodo))


def _hijos_sentencia(nodo: Node) -> list[Node]:
    tipo = nodo.type
    if tipo == "module":
        return sentencias(nodo)
    if tipo == "decorated_definition":
        return _hijos_sentencia(definicion(nodo))
    if tipo in ("function_definition", "class_definition", "with_statement"):
        return sentencias(campo(nodo, "body"))
    if tipo in ("if_statement", "elif_clause"):
        resultado = sentencias(campo(nodo, "consequence"))
        alternativa = _alternativa(nodo)
        if alternativa is not None and alternativa.type == "elif_clause":
            resultado.append(alternativa)
        elif alternativa is not None:
            resultado.extend(_sentencias_clausula(alternativa))
        return resultado
    if tipo == "try_statement":
        resultado = []
        for hijo in nombrados(nodo):
            if hijo.type == "block":
                resultado.extend(sentencias(hijo))
            elif hijo.type in ("except_clause", "except_group_clause"):
                resultado.append(hijo)
            elif hijo.type in ("else_clause", "finally_clause"):
                resultado.extend(_sentencias_clausula(hijo))
        return resultado
    if tipo in ("except_clause", "except_group_clause", "case_clause"):
        return _sentencias_clausula(nodo)
    if tipo in ("for_statement", "while_statement"):
        resultado = sentencias(campo(nodo, "body"))
        alternativa = campo(nodo, "alternative")
        if alternativa is not None:
            resultado.extend(_sentencias_clausula(alternativa))
        return resultado
    if tipo == "match_statement":
        bloque = campo(nodo, "body")
        return [] if bloque is None else nombrados(bloque)
    return []


def _alternativa(nodo: Node) -> Node | None:
    """El ``elif``/``else`` que sigue a un ``if`` o a un ``elif`` (su ``orelse``)."""
    if nodo.type == "if_statement":
        return next(
            (h for h in nombrados(nodo) if h.type in ("elif_clause", "else_clause")),
            None,
        )
    siguiente = nodo.next_named_sibling
    while siguiente is not None and siguiente.type == "comment":
        siguiente = siguiente.next_named_sibling
    if siguiente is not None and siguiente.type in ("elif_clause", "else_clause"):
        return siguiente
    return None


def _sentencias_clausula(clausula: Node) -> list[Node]:
    bloque = next((h for h in nombrados(clausula) if h.type == "block"), None)
    return sentencias(bloque)


def _nombres_del_modulo(arbol: Tree) -> set[str]:
    """Nombres que el módulo define o importa en su nivel superior."""
    nivel_modulo = _de_nivel_modulo(arbol)
    nombres: set[str] = set()
    for nodo in arbol_ts.recorrer(arbol.root_node):
        if nodo.id not in nivel_modulo:
            continue
        importado = arbol_ts.importacion(nodo)
        if importado is not None:
            for original, alias in importado.nombres:
                nombres.add((alias or original).split(".")[0])
        elif nodo.type in ("function_definition", "class_definition"):
            nombres.add(arbol_ts.nombre(nodo))
        elif nodo.type == "assignment" and nodo.parent is not None:
            if nodo.parent.type != "expression_statement":
                continue  # el resto de «a = b = 1» ya se cuenta desde el primero
            actual: Node | None = nodo
            while actual is not None and actual.type == "assignment":
                nombres.update(n for n, _ in _nombres(campo(actual, "left")))
                if campo(actual, "type") is not None:
                    break
                actual = campo(actual, "right")
    return nombres


def _globales_usados(arbol: Tree, funcion: Node) -> list[str]:
    del_modulo = _nombres_del_modulo(arbol) - {arbol_ts.nombre(funcion)}
    completa = funcion.parent if funcion.parent is not None else funcion
    if completa.type != "decorated_definition":
        completa = funcion
    usados = {nombre for nombre, lectura in _nombres(completa) if lectura}
    return sorted(usados & del_modulo)


# --------------------------------------------------------------------------- #
# Nombres: los ``ast.Name`` de un subárbol, con su contexto
# --------------------------------------------------------------------------- #
#: Contenedores que conservan el contexto de asignación: ``a, (b, *c) = ...``.
_CONTENEDORES_DESTINO = frozenset(
    {
        "pattern_list",
        "tuple_pattern",
        "list_pattern",
        "list_splat_pattern",
        "tuple",
        "list",
        "expression_list",
        "parenthesized_expression",
        "list_splat",
        "as_pattern_target",
    }
)
_SIN_NOMBRES = frozenset(
    {
        "import_statement",
        "import_from_statement",
        "future_import_statement",
        "global_statement",
        "nonlocal_statement",
    }
)


def _nombres(nodo: Node | None, destino: bool = False) -> Iterator[tuple[str, bool]]:
    """``(nombre, es_lectura)`` de cada ``ast.Name`` bajo ``nodo``.

    ``es_lectura`` es el contexto ``Load``: lo que se asigna, se borra o recibe el
    valor de un ``for`` o de un ``with ... as`` no es lectura. Los atributos, los
    argumentos por nombre, los parámetros y los nombres de funciones, clases,
    imports, excepciones (``except E as e``) y capturas de ``match`` no son
    ``ast.Name``.
    """
    if nodo is None:
        return
    tipo = nodo.type
    if tipo in _SIN_NOMBRES:
        return
    if tipo == "identifier":
        yield texto(nodo), not destino
    elif tipo == "attribute":
        yield from _nombres(campo(nodo, "object"))
    elif tipo == "keyword_argument":
        yield from _nombres(campo(nodo, "value"))
    elif tipo in ("function_definition", "class_definition"):
        nombre_nodo = campo(nodo, "name")
        for hijo in nombrados(nodo):
            if hijo != nombre_nodo:
                yield from _nombres(hijo)
    elif tipo in ("parameters", "lambda_parameters"):
        for parametro in arbol_ts.parametros(nodo):
            yield from _nombres(parametro.tipo)
            yield from _nombres(parametro.defecto)
    elif tipo in ("assignment", "augmented_assignment"):
        yield from _nombres(campo(nodo, "left"), destino=True)
        yield from _nombres(campo(nodo, "type"))
        yield from _nombres(campo(nodo, "right"))
    elif tipo in ("for_statement", "for_in_clause"):
        izquierdo = campo(nodo, "left")
        for hijo in nombrados(nodo):
            yield from _nombres(hijo, destino=hijo == izquierdo)
    elif tipo == "named_expression":
        yield from _nombres(campo(nodo, "name"), destino=True)
        yield from _nombres(campo(nodo, "value"))
    elif tipo == "delete_statement":
        for hijo in nombrados(nodo):
            yield from _nombres(hijo, destino=True)
    elif tipo == "as_pattern":
        yield from _nombres_como(nodo)
    elif tipo == "case_pattern":
        yield from _nombres_patron(nodo)
    else:
        hereda = destino and tipo in _CONTENEDORES_DESTINO
        for hijo in nombrados(nodo):
            yield from _nombres(hijo, destino=hereda)


def _nombres_como(nodo: Node) -> Iterator[tuple[str, bool]]:
    """``x as y``: en un ``with``, ``y`` se asigna; en un ``except``, no es un nombre."""
    padre = nodo.parent.type if nodo.parent is not None else ""
    alias = campo(nodo, "alias")
    for hijo in nombrados(nodo):
        if hijo != alias:
            yield from _nombres(hijo)
        elif padre not in ("except_clause", "except_group_clause"):
            yield from _nombres(hijo, destino=True)


def _nombres_patron(nodo: Node) -> Iterator[tuple[str, bool]]:
    """Lecturas de un patrón de ``case``: la clase y los valores con punto, no las capturas."""
    tipo = nodo.type
    if tipo == "dotted_name":
        partes = nombrados(nodo)
        if len(partes) > 1:
            yield texto(partes[0]), True
    elif tipo == "class_pattern":
        internos = nombrados(nodo)
        if internos and internos[0].type == "dotted_name":
            yield texto(nombrados(internos[0])[0]), True
        for interno in internos[1:]:
            yield from _nombres_patron(interno)
    elif tipo == "keyword_pattern":
        for interno in nombrados(nodo)[1:]:
            yield from _nombres_patron(interno)
    elif tipo == "as_pattern":
        internos = nombrados(nodo)
        if internos:
            yield from _nombres_patron(internos[0])
    elif tipo in ("splat_pattern", "identifier"):
        return
    elif tipo in (
        "case_pattern",
        "union_pattern",
        "list_pattern",
        "tuple_pattern",
        "dict_pattern",
    ):
        for interno in nombrados(nodo):
            yield from _nombres_patron(interno)
    else:
        yield from _nombres(nodo)
