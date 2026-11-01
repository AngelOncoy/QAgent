"""Extracción estática de funciones JS/TS, JSDoc y decisiones con tree-sitter (#176)."""

from __future__ import annotations

from typing import Any

import pytest

from qagent.lenguajes.javascript_estructura import (
    desglosar_jsdoc,
    extraer_funciones,
    gramatica_de,
)
from qagent.lenguajes.treesitter import obtener_parser


def _funciones(codigo: str, gramatica: str = "typescript") -> dict[str, dict[str, Any]]:
    raiz = obtener_parser(gramatica).parse(codigo.encode("utf-8")).root_node
    assert not raiz.has_error
    return {f["nombre"]: f for f in extraer_funciones(raiz)}


@pytest.mark.parametrize(
    ("ruta", "esperada"),
    [
        ("a.ts", "typescript"),
        ("a.mts", "typescript"),
        ("a.cts", "typescript"),
        ("A.TSX", "tsx"),
        ("a.js", "javascript"),
        ("a.mjs", "javascript"),
        ("a.cjs", "javascript"),
        ("a.jsx", "javascript"),
    ],
)
def test_gramatica_por_extension(ruta: str, esperada: str) -> None:
    assert gramatica_de(ruta) == esperada


# --- Exportaciones ESM ----------------------------------------------------------------


def test_exportaciones_esm_declaraciones_flechas_y_clausulas() -> None:
    funciones = _funciones(
        """
export function sumar(a: number, b: number): number { return a + b; }
export const doble = (x: number): number => x * 2;
export const triple = x => x * 3;
const interna = function (y: string) { return y; };
function privada() {}
export { interna, interna as alias };
export default function principal() {}
export * from './otro';
export { reexportada } from './otro';
"""
    )
    assert list(funciones) == [
        "sumar",
        "doble",
        "triple",
        "interna",
        "alias",
        "principal",
    ]
    assert funciones["sumar"]["exportacion"] == "nombrada"
    assert funciones["principal"]["exportacion"] == "default"
    assert "privada" not in funciones


def test_export_default_anonima_e_identificador() -> None:
    assert list(_funciones("export default (a: number) => a;")) == ["default"]
    funciones = _funciones("function f(a) { return a; }\nexport default f;")
    assert funciones["f"]["exportacion"] == "default"


def test_metodos_publicos_de_clases_exportadas() -> None:
    funciones = _funciones(
        """
export class Carrito {
  constructor(private items: number[]) {}
  total(): number { return 0; }
  static vacio(): Carrito { return new Carrito([]); }
  async cargar(id: string): Promise<void> {}
  private secreto() {}
  protected interno() {}
  #oculto() {}
  get cantidad() { return 0; }
  set cantidad(v) {}
}
export abstract class Base { abstract m(): void; concreto(): number { return 1; } }
class NoExportada { visible() {} }
"""
    )
    assert list(funciones) == [
        "Carrito.total",
        "Carrito.vacio",
        "Carrito.cargar",
        "Base.concreto",
    ]
    assert funciones["Carrito.vacio"]["es_static"] is True
    assert funciones["Carrito.total"]["es_static"] is False
    assert funciones["Carrito.cargar"]["es_async"] is True
    assert funciones["Carrito.total"]["clase"] == "Carrito"
    assert funciones["Carrito.total"]["firma"] == "total(): number"


def test_sobrecargas_de_typescript_quedan_como_una_funcion() -> None:
    funciones = _funciones(
        """
export function f(a: string): string;
export function f(a: number): number;
export function f(a: any): any { return a; }
"""
    )
    assert list(funciones) == ["f"]
    assert funciones["f"]["linea"] == 4


# --- Exportaciones CommonJS -----------------------------------------------------------


def test_exportaciones_commonjs() -> None:
    funciones = _funciones(
        """
function dividir(a, b) { return a / b; }
function restar(a, b) { return a - b; }
module.exports = { dividir, menos: restar, porDos: (x) => x * 2, mitad(x) { return x / 2; } };
exports.cuadrado = function (x) { return x * x; };
module.exports.cubo = async ({ x }) => x ** 3;
""",
        "javascript",
    )
    assert list(funciones) == [
        "dividir",
        "menos",
        "porDos",
        "mitad",
        "cuadrado",
        "cubo",
    ]
    assert {f["exportacion"] for f in funciones.values()} == {"commonjs"}
    assert funciones["menos"]["firma"] == "menos(a, b)"
    assert funciones["cubo"]["parametros"][0]["nombre"] == "{ x }"


def test_module_exports_de_una_sola_funcion() -> None:
    funciones = _funciones(
        "function calcular(a) { return a; }\nmodule.exports = calcular;", "javascript"
    )
    assert funciones["calcular"]["exportacion"] == "commonjs_modulo"


def test_codigo_sin_exportaciones_no_tiene_objetivos() -> None:
    assert _funciones("function suelta(a) { return a; }", "javascript") == {}


# --- Parámetros, firma y tipos --------------------------------------------------------


def test_parametros_con_tipos_defectos_opcionales_y_resto() -> None:
    funcion = _funciones(
        "export function f(a: number, b = 2, c?: string, ...resto: number[]): "
        "number { return a; }"
    )["f"]
    assert funcion["parametros"] == [
        {"nombre": "a", "tipo": "number", "por_defecto": None, "opcional": False},
        {"nombre": "b", "tipo": None, "por_defecto": "2", "opcional": True},
        {"nombre": "c", "tipo": "string", "por_defecto": None, "opcional": True},
        {
            "nombre": "...resto",
            "tipo": "number[]",
            "por_defecto": None,
            "opcional": False,
        },
    ]
    assert funcion["retorno"] == "number"
    assert funcion["firma"] == (
        "f(a: number, b = 2, c?: string, ...resto: number[]): number"
    )


def test_parametros_javascript_con_defecto() -> None:
    funcion = _funciones("export function f(a, b = 1) {}", "javascript")["f"]
    assert funcion["parametros"][1] == {
        "nombre": "b",
        "tipo": None,
        "por_defecto": "1",
        "opcional": True,
    }


def test_tipada_con_typescript_o_con_jsdoc() -> None:
    ts = _funciones("export function f(a: number): number { return a; }")["f"]
    sin_retorno = _funciones("export function f(a: number) { return a; }")["f"]
    js = _funciones(
        """
/**
 * @param {number} a valor
 * @returns {number} el mismo valor
 */
export function f(a) { return a; }
""",
        "javascript",
    )["f"]
    js_sin_tipos = _funciones("export function f(a) { return a; }", "javascript")["f"]
    assert ts["tipada"] is True
    assert sin_retorno["tipada"] is False
    assert js["tipada"] is True
    assert js_sin_tipos["tipada"] is False


def test_firma_async_de_flecha() -> None:
    funcion = _funciones(
        "export const f = async (x?: string): Promise<'a' | 'b'> => 'a';"
    )["f"]
    assert funcion["firma"] == "async f(x?: string): Promise<'a' | 'b'>"
    assert funcion["retorno"] == "Promise<'a' | 'b'>"
    assert funcion["es_async"] is True


# --- JSDoc ----------------------------------------------------------------------------


def test_jsdoc_pegado_a_la_exportacion_con_lineas() -> None:
    funcion = _funciones(
        """
/**
 * Divide dos números.
 * @param {number} a dividendo
 * @param {number} [b=1] - divisor
 * @returns {number} el cociente
 * @throws {RangeError} si b es 0
 * @example
 * dividir(6, 3) // => 2
 */
export function dividir(a: number, b = 1): number { return a / b; }
"""
    )["dividir"]
    assert funcion["docstring"].startswith("/**")
    assert funcion["jsdoc"] == {
        "descripcion": "Divide dos números.",
        "parametros": {
            "a": {"tipo": "number", "descripcion": "dividendo", "por_defecto": None},
            "b": {"tipo": "number", "descripcion": "divisor", "por_defecto": "1"},
        },
        "retorno": {"tipo": "number", "descripcion": "el cociente", "linea": 6},
        "excepciones": [{"tipo": "RangeError", "descripcion": "si b es 0", "linea": 7}],
        "ejemplos": [{"texto": "dividir(6, 3) // => 2", "linea": 8, "linea_fin": 9}],
        "otras_etiquetas": {},
    }


def test_jsdoc_de_metodo_y_de_commonjs() -> None:
    funciones = _funciones(
        """
class Calc {
  /** @returns {number} siempre cero */
  cero() { return 0; }
}
/** Suma uno. */
exports.inc = function (x) { return x + 1; };
module.exports.Calc = Calc;
""",
        "javascript",
    )
    assert funciones["Calc.cero"]["jsdoc"]["retorno"]["descripcion"] == "siempre cero"
    assert funciones["inc"]["jsdoc"]["descripcion"] == "Suma uno."


def test_comentario_normal_o_lejano_no_es_jsdoc() -> None:
    funciones = _funciones(
        """
/* comentario de bloque */
export function a() {}

/** Lejano. */



export function b() {}
// línea
export function c() {}
""",
        "javascript",
    )
    assert all(
        f["jsdoc"] is None and f["docstring"] is None for f in funciones.values()
    )


def test_desglosar_jsdoc_tipos_anidados_y_otras_etiquetas() -> None:
    jsdoc = desglosar_jsdoc(
        "/**\n * @param {{a: number}} opciones configuración\n"
        " * @return {Array<{id: string}>} lista\n * @deprecated usar otra\n */",
        10,
    )
    assert jsdoc["parametros"]["opciones"]["tipo"] == "{a: number}"
    assert jsdoc["retorno"] == {
        "tipo": "Array<{id: string}>",
        "descripcion": "lista",
        "linea": 12,
    }
    assert jsdoc["otras_etiquetas"] == {"deprecated": ["usar otra"]}
    assert desglosar_jsdoc(None) is None


# --- Ramas ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cuerpo", "ramas"),
    [
        ("return a;", 0),
        ("if (a) { return 1; } else if (b) { return 2; } return 3;", 2),
        ("return a ? 1 : 2;", 1),
        (
            "for (let i = 0; i < a; i++) {} for (const x of b) {} for (const k in b) {}",
            3,
        ),
        ("while (a) {} do {} while (b);", 2),
        ("try { a(); } catch (e) { b(); } finally {}", 1),
        ("switch (a) { case 1: case 2: break; default: return 0; }", 2),
        ("return (a && b || c) ?? d;", 3),
        ("return a + b * c;", 0),
        ("const f = () => { if (a) {} }; function g() { if (b) {} } return f;", 0),
        ("class X { m() { if (a) {} } } return 1;", 0),
    ],
)
def test_conteo_de_ramas(cuerpo: str, ramas: int) -> None:
    codigo = f"export function f(a, b, c, d) {{ {cuerpo} }}"
    assert _funciones(codigo, "javascript")["f"]["ramas"] == ramas


def test_ramas_de_flecha_con_cuerpo_de_expresion() -> None:
    assert (
        _funciones("export const f = (a) => a ? 1 : 2;", "javascript")["f"]["ramas"]
        == 1
    )
