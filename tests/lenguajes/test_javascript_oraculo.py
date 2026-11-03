"""Registro de evidencias JSDoc/TypeScript y oráculos ``oracle.v1`` (#176, EN-18).

El oráculo estricto solo acepta lo que la documentación fija: ``@example`` con
resultado, ``@throws`` y tipos de retorno literales. Todo es estático.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from qagent import contracts
from qagent.lenguajes import JavaScriptAdapter, TypeScriptAdapter
from qagent.lenguajes.javascript_oraculo import (
    NO_REPRESENTABLE,
    compatible,
    literal,
    oraculo_del_caso,
    posicionales,
)
from qagent.lenguajes.treesitter import obtener_parser

CLASIFICAR = """/**
 * Clasifica a una persona por su edad.
 * @param {number} edad años cumplidos
 * @returns {string} la categoría
 * @throws {RangeError} si la edad es negativa
 * @example
 * clasificar(10) // => "menor"
 * clasificar(30); //=> 'adulto'
 * clasificar(-1) // throws RangeError
 */
export function clasificar(edad: number): "menor" | "adulto" | "mayor" {
  if (edad < 0) throw new RangeError("negativa");
  return edad < 18 ? "menor" : edad < 65 ? "adulto" : "mayor";
}

/** Versión del formato. */
export function version(): 'v1' { return 'v1'; }

export function sinDocumentar(a: number, b: number): number { return a + b; }

/**
 * Promedio de una lista.
 * @param {number[]} xs valores
 * @returns {number} el promedio aritmético
 */
export function promedio(xs: number[]): number { return 0; }
"""


def _analizar(tmp_path: Path, codigo: str, archivo: str = "src/a.ts") -> dict[str, Any]:
    ruta = tmp_path / archivo
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(codigo, encoding="utf-8")
    adaptador = TypeScriptAdapter() if archivo.endswith(".ts") else JavaScriptAdapter()
    estructura = adaptador.analizar(tmp_path)
    assert estructura["errores"] == []
    return {f["nombre"]: f for m in estructura["modulos"] for f in m["funciones"]}


def _oraculo(funcion: dict[str, Any], caso: dict[str, Any], lenguaje="typescript"):
    oraculo, motivo = oraculo_del_caso(lenguaje, funcion["modulo"], funcion, caso)
    contracts.validar_versionado(contracts.FAMILIA_ORACLE, oraculo)
    return oraculo, motivo


# --- Literales y tipos ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "valor"),
    [
        ("5", 5),
        ("-1.5", -1.5),
        ("0x1F", 31),
        ("1_000", 1000),
        ("'a\\nb'", "a\nb"),
        ("`plantilla`", "plantilla"),
        ("true", True),
        ("null", None),
        ("[1, [2]]", [1, [2]]),
        ("({ x: 1, 'y': [true] })", {"x": 1, "y": [True]}),
    ],
)
def test_literales_js_a_json(texto: str, valor: Any) -> None:
    raiz = obtener_parser("javascript").parse(texto.encode()).root_node
    assert literal(raiz.named_children[0].named_children[0]) == valor


@pytest.mark.parametrize(
    "texto", ["undefined", "NaN", "Infinity", "a + 1", "`${x}`", "f()", "{ ...x }"]
)
def test_lo_que_no_es_un_literal_json(texto: str) -> None:
    raiz = obtener_parser("javascript").parse(f"({texto})".encode()).root_node
    assert literal(raiz.named_children[0].named_children[0]) is NO_REPRESENTABLE


@pytest.mark.parametrize(
    ("tipo", "valor", "esperado"),
    [
        ("number", 1, True),
        ("number", True, False),
        ("string", "a", True),
        ("boolean", 0, False),
        ("number[]", [1, 2.5], True),
        ("Array<string>", [1], False),
        ("'a' | 'b'", "b", True),
        ("'a' | 'b'", "c", False),
        ("Promise<number>", 2, True),
        ("number | null", None, True),
        ("void", None, False),
        ("Carrito", {"x": 1}, True),
        (None, "lo que sea", True),
    ],
)
def test_compatible(tipo: str | None, valor: Any, esperado: bool) -> None:
    assert compatible(tipo, valor) is esperado


# --- Registro de evidencias -----------------------------------------------------------


def test_registro_desde_ejemplos_throws_returns_y_tipo(tmp_path: Path) -> None:
    funciones = _analizar(tmp_path, CLASIFICAR)
    registro = funciones["clasificar"]["evidencias"]

    assert set(registro) == {
        "jsdoc:clasificar:ejemplo:1",
        "jsdoc:clasificar:ejemplo:2",
        "jsdoc:clasificar:ejemplo:3",
        "jsdoc:clasificar:throws:1",
        "jsdoc:clasificar:returns",
        "typescript:clasificar:retorno",
    }
    primero = registro["jsdoc:clasificar:ejemplo:1"]
    assert primero["entrada_documentada"] == [10]
    assert primero["valor_documentado"] == "menor"
    assert primero["evidencia"] == {
        "id": "jsdoc:clasificar:ejemplo:1",
        "fuente": "jsdoc",
        "caracter": "comportamiento",
        "ubicacion": {"archivo": "src/a.ts", "linea_inicio": 7},
        "referencia": "@example",
        "fragmento": 'clasificar(10) // => "menor"',
    }
    assert registro["jsdoc:clasificar:ejemplo:2"]["valor_documentado"] == "adulto"
    assert registro["jsdoc:clasificar:ejemplo:3"]["excepcion_documentada"] == (
        "RangeError"
    )
    assert registro["jsdoc:clasificar:throws:1"]["excepcion_documentada"] == (
        "RangeError"
    )
    assert "valor_documentado" not in registro["jsdoc:clasificar:returns"]
    union = registro["typescript:clasificar:retorno"]
    assert union["evidencia"]["caracter"] == "tipo_union_literal"
    assert "valor_documentado" not in union

    literal_ts = funciones["version"]["evidencias"]["typescript:version:retorno"]
    assert literal_ts["evidencia"]["caracter"] == "tipo_literal"
    assert literal_ts["valor_documentado"] == "v1"
    assert funciones["sinDocumentar"]["evidencias"]["typescript:sinDocumentar:retorno"][
        "evidencia"
    ]["caracter"] == ("tipo_general")


def test_ejemplos_contradictorios_no_fijan_valor(tmp_path: Path) -> None:
    funciones = _analizar(
        tmp_path,
        """
/**
 * @example
 * doble(2) // => 4
 * doble(2) // => 5
 * doble(3) // => "seis"
 */
export function doble(x: number): number { return x * 2; }
""",
    )
    registro = funciones["doble"]["evidencias"]
    for id_ in ("jsdoc:doble:ejemplo:1", "jsdoc:doble:ejemplo:2"):
        assert registro[id_]["evidencia"]["caracter"] == "contradictoria"
        assert "valor_documentado" not in registro[id_]
    # El ejemplo contradice el tipo de retorno: tampoco fija valor.
    assert registro["jsdoc:doble:ejemplo:3"]["evidencia"]["caracter"] == (
        "contradictoria"
    )


def test_ejemplos_que_no_son_llamadas_literales_se_ignoran(tmp_path: Path) -> None:
    funciones = _analizar(
        tmp_path,
        """
/**
 * @example
 * const r = suma(1, 2);
 * suma(x, 2) // => 3
 * otra(1, 2) // => 3
 * suma(1, undefined) // => 1
 * suma(1, 2) // => resultado
 */
export function suma(a: number, b?: number): number { return a + (b ?? 0); }
""",
    )
    assert not any(
        "entrada_documentada" in e for e in funciones["suma"]["evidencias"].values()
    )


def test_ejemplo_de_metodo_y_de_javascript_con_jsdoc(tmp_path: Path) -> None:
    funciones = _analizar(
        tmp_path,
        """
class Calc {
  /**
   * @param {number} a
   * @returns {number}
   * @example new Calc().mitad(8) // => 4
   */
  mitad(a) { return a / 2; }
}
module.exports = { Calc };
""",
        "lib/calc.js",
    )
    registro = funciones["Calc.mitad"]["evidencias"]
    assert registro["jsdoc:Calc.mitad:ejemplo:1"]["valor_documentado"] == 4
    assert registro["jsdoc:Calc.mitad:retorno"]["evidencia"]["fuente"] == "jsdoc"


# --- Oráculos -------------------------------------------------------------------------


def test_oraculo_verificable_desde_un_ejemplo(tmp_path: Path) -> None:
    funcion = _analizar(tmp_path, CLASIFICAR)["clasificar"]
    oraculo, motivo = _oraculo(
        funcion,
        {"entrada": {"edad": 10}, "valor_esperado": "menor", "origen": "docstring"},
    )
    assert motivo is None
    assert oraculo["estado_evidencia"] == "verificable"
    assert oraculo["comprobacion"] == "igualdad"
    assert oraculo["valor_esperado"] == "menor"
    assert oraculo["evidencia"]["fuente"] == "jsdoc"
    contracts.validar_oraculo_js_ts(oraculo, funcion["evidencias"])


def test_oraculo_de_excepcion_desde_ejemplo_y_desde_throws(tmp_path: Path) -> None:
    funcion = _analizar(tmp_path, CLASIFICAR)["clasificar"]
    for edad in (-1, -40):
        oraculo, motivo = _oraculo(
            funcion,
            {"entrada": [edad], "excepcion": "RangeError", "origen": "docstring"},
        )
        assert motivo is None
        assert oraculo["comprobacion"] == "excepcion"
        assert oraculo["excepcion_esperada"] == "RangeError"


def test_oraculo_verificable_desde_un_tipo_literal(tmp_path: Path) -> None:
    funcion = _analizar(tmp_path, CLASIFICAR)["version"]
    oraculo, motivo = _oraculo(
        funcion, {"entrada": [], "valor_esperado": "v1", "origen": "tipo"}
    )
    assert motivo is None
    assert oraculo["evidencia"]["fuente"] == "typescript"


def test_valor_distinto_al_documentado_se_rechaza(tmp_path: Path) -> None:
    funcion = _analizar(tmp_path, CLASIFICAR)["clasificar"]
    oraculo, motivo = _oraculo(
        funcion,
        {"entrada": [10], "valor_esperado": "adulto", "origen": "docstring"},
    )
    assert oraculo["estado_evidencia"] == "insuficiente"
    assert "no coincide con el valor documentado" in motivo


@pytest.mark.parametrize(
    ("caso", "estado", "fragmento"),
    [
        # Una entrada sin ejemplo: la unión de literales no dice cuál le toca.
        (
            {"entrada": [50], "valor_esperado": "adulto", "origen": "docstring"},
            "insuficiente",
            "no documenta un valor concreto",
        ),
        # Excepción no documentada.
        (
            {"entrada": [-1], "excepcion": "TypeError", "origen": "docstring"},
            "insuficiente",
            "no coincide con la excepción documentada",
        ),
    ],
)
def test_lo_no_documentado_es_insuficiente(
    tmp_path: Path, caso: dict[str, Any], estado: str, fragmento: str
) -> None:
    funcion = _analizar(tmp_path, CLASIFICAR)["clasificar"]
    oraculo, motivo = _oraculo(funcion, caso)
    assert oraculo["estado_evidencia"] == estado
    assert fragmento in motivo
    assert "valor_esperado" not in oraculo and "excepcion_esperada" not in oraculo


def test_returns_en_prosa_no_basta(tmp_path: Path) -> None:
    funcion = _analizar(tmp_path, CLASIFICAR)["promedio"]
    oraculo, motivo = _oraculo(
        funcion, {"entrada": [[1, 3]], "valor_esperado": 2, "origen": "docstring"}
    )
    assert oraculo["estado_evidencia"] == "insuficiente"
    assert motivo.startswith("sin resultado esperado verificable")


def test_funcion_sin_jsdoc_ni_tipos_es_sin_procedencia(tmp_path: Path) -> None:
    funcion = _analizar(
        tmp_path, "export function suma(a, b) { return a + b; }", "src/a.js"
    )["suma"]
    oraculo, motivo = _oraculo(
        funcion,
        {"entrada": [1, 2], "valor_esperado": 3, "origen": "docstring"},
        "javascript",
    )
    assert oraculo["estado_evidencia"] == "sin_procedencia"
    assert "evidencia" not in oraculo
    assert motivo.startswith("sin resultado esperado verificable")


def test_contradiccion_se_conserva(tmp_path: Path) -> None:
    funcion = _analizar(
        tmp_path,
        "/**\n * @example\n * f(1) // => 1\n * f(1) // => 2\n */\n"
        "export function f(x: number): number { return x; }",
    )["f"]
    oraculo, motivo = _oraculo(
        funcion, {"entrada": [1], "valor_esperado": 1, "origen": "docstring"}
    )
    assert oraculo["estado_evidencia"] == "contradictoria"
    assert "se contradice" in motivo


def test_origen_debe_corresponder_a_la_evidencia(tmp_path: Path) -> None:
    funcion = _analizar(tmp_path, CLASIFICAR)["clasificar"]
    _, motivo = _oraculo(
        funcion, {"entrada": [10], "valor_esperado": "menor", "origen": "tipo"}
    )
    assert "origen" in motivo


def test_numeros_enteros_y_flotantes_son_el_mismo_valor(tmp_path: Path) -> None:
    funcion = _analizar(
        tmp_path,
        "/** @example mitad(8) // => 4.0 */\n"
        "export function mitad(x: number): number { return x / 2; }",
    )["mitad"]
    _, motivo = _oraculo(
        funcion, {"entrada": [8.0], "valor_esperado": 4, "origen": "docstring"}
    )
    assert motivo is None


# --- Entrada posicional ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ({"a": 1, "b": 2}, [1, 2]),
        ({"a": 1}, [1]),
        ({"a": 1, "b": 2, "xs": [3, 4]}, [1, 2, 3, 4]),
        ([1, 2, 3], [1, 2, 3]),
        (None, []),
        ({"b": 2}, None),
        ({"a": 1, "xs": [3]}, None),
        ({"a": 1, "z": 0}, None),
        ({"a": 1, "b": 2, "xs": 3}, None),
        ("texto", None),
    ],
)
def test_posicionales(entrada: Any, esperado: list[Any] | None) -> None:
    funcion = {
        "parametros": [
            {"nombre": "a", "opcional": False},
            {"nombre": "b", "opcional": True},
            {"nombre": "...xs", "opcional": False},
        ]
    }
    assert posicionales(funcion, entrada) == esperado
