"""TA-16: ``texto_ts`` escribe las expresiones igual que ``ast.unparse``.

Cada caso salió de una diferencia real encontrada al comparar con la biblioteca
estándar de Python o de un defecto de la gramática de tree-sitter. ``ast`` solo se
usa aquí como referencia: QAgent ya no lo usa para leer el código del usuario.
Los casos cuyo formato o sintaxis dependen de la versión tienen comprobaciones
propias: la salida normalizada de tree-sitter no cambia con el intérprete anfitrión.
"""

from __future__ import annotations

import ast
import sys

import pytest

from qagent.analysis import texto_ts

CASOS = [
    # Precedencia de ^ y & invertida en la gramática.
    "a << 1 | b >> 2 ^ c & d",
    "c & s[0] ^ 1 and c % ~a & b",
    "not f(z) ^ 1 >> c & s[0]",
    "-a ** 2",
    "(-a) ** 2",
    "2 ** 3 ** 2",
    "(2 ** 3) ** 2",
    # Cadenas: comillas, escapes, crudas que terminan en barra, bytes, u"".
    "'it\\'s'",
    "r'\\\\'",
    "r'\\\\\\\\'",
    "'a' \"b\"",
    "b'\\x00\\n'",
    "u'x'",
    "'\\N{GREEK SMALL LETTER ALPHA}'",
    # f-strings, incluida la de depuración con espacios.
    "f'{x!r:>{w}} y {{literal}}'",
    "f'{x = }'",
    "f'{x=}'",
    "f'{x = !s}'",
    "f\"{'anidada'}\" 'x'",
    # Números.
    "0x10 + 1_000 + 1e3 + 3j + 1e400",
    # Comprensiones, lambdas, ternarios, :=.
    "[i for i in range(3) if i if i > 1]",
    "f(x for x in y)",
    "lambda x, *a, k=1, **kw: (x, a)",
    "(coeff := lhs if lhs not in pending else rhs)",
    "a if b else c if d else e",
    # Subíndices y desempaques.
    "a[1:2, ::3, 4]",
    "a[()]",
    "a[(1, 2)]",
    "a[1,]",
    "f(*a, k=1, **kw)",
    "f(k=1, *a)",
    # Identificadores Unicode: ast los normaliza con NFKC.
    "µ + 𝔘𝔫𝔦𝔠𝔬𝔡𝔢",
]


@pytest.mark.parametrize("codigo", CASOS)
def test_expresion_igual_que_ast_unparse(codigo: str) -> None:
    nodo = texto_ts.expresion_de_texto(codigo)
    assert nodo is not None
    assert texto_ts.expresion(nodo) == ast.unparse(ast.parse(codigo, mode="eval"))


def test_comprension_diccionario_conserva_texto_y_estructura() -> None:
    """Conserva el formato 3.11 y verifica el AST también con unparse de 3.10."""
    codigo = "{k: v for k, v in d.items()}"
    nodo = texto_ts.expresion_de_texto(codigo)
    assert nodo is not None
    salida = texto_ts.expresion(nodo)
    assert salida == codigo

    original = ast.parse(codigo, mode="eval")
    referencia = ast.unparse(original)
    esperado = (
        "{k: v for (k, v) in d.items()}" if sys.version_info < (3, 11) else codigo
    )
    assert referencia == esperado
    assert ast.dump(ast.parse(salida, mode="eval")) == ast.dump(original)
    assert ast.dump(ast.parse(referencia, mode="eval")) == ast.dump(original)


def test_desempaque_subindice_segun_version_python() -> None:
    """Verifica tree-sitter siempre y la aceptación de ast desde Python 3.11."""
    codigo = "Generic[*Ts]"
    nodo = texto_ts.expresion_de_texto(codigo)
    assert nodo is not None
    salida = texto_ts.expresion(nodo)
    # ast 3.11 normaliza el índice desempaquetado como una tupla de un elemento.
    assert salida == "Generic[*Ts,]"

    if sys.version_info < (3, 11):
        with pytest.raises(SyntaxError):
            ast.parse(codigo, mode="eval")
        with pytest.raises(SyntaxError):
            ast.parse(salida, mode="eval")
    else:
        original = ast.parse(codigo, mode="eval")
        assert ast.unparse(original) == salida
        assert ast.dump(ast.parse(salida, mode="eval")) == ast.dump(original)


@pytest.mark.parametrize(
    "objetivo",
    ["for i, (x) in z: pass", "for (a, b), ((c, d)) in z: pass"],
)
def test_destino_de_for_entre_parentesis(objetivo: str) -> None:
    from qagent.analysis.arbol_ts import parsear, sentencias

    nodo = sentencias(parsear(objetivo).root_node)[0].child_by_field_name("left")
    esperado = ast.unparse(ast.parse(objetivo).body[0].target)
    assert texto_ts.expresion(nodo) == esperado


@pytest.mark.parametrize(
    "codigo",
    ["1", "-1.5", "'x' 'y'", "(1, -2)", "[1, {'a': None}]", "{1, 2}", "set()", "1+2j"],
)
def test_literal_igual_que_ast_literal_eval(codigo: str) -> None:
    assert texto_ts.literal_de_texto(codigo) == ast.literal_eval(codigo)


@pytest.mark.parametrize("codigo", ["x", "f(1)", "1 + 2", "f'{x}'", "1; 2", "a = 1"])
def test_literal_rechaza_lo_que_no_es_literal(codigo: str) -> None:
    with pytest.raises(ValueError):
        texto_ts.literal_de_texto(codigo)
