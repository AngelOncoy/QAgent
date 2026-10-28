"""TA-16: ``texto_ts`` escribe las expresiones igual que ``ast.unparse``.

Cada caso salió de una diferencia real encontrada al comparar con la biblioteca
estándar de Python o de un defecto de la gramática de tree-sitter. ``ast`` solo se
usa aquí como referencia: QAgent ya no lo usa para leer el código del usuario.
"""

from __future__ import annotations

import ast

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
    "{k: v for k, v in d.items()}",
    "f(x for x in y)",
    "lambda x, *a, k=1, **kw: (x, a)",
    "(coeff := lhs if lhs not in pending else rhs)",
    "a if b else c if d else e",
    # Subíndices y desempaques.
    "a[1:2, ::3, 4]",
    "a[()]",
    "a[(1, 2)]",
    "a[1,]",
    "Generic[*Ts]",
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
