"""``analizar()``, ``objetivos()`` y ``llama_a`` de JavaScript y TypeScript (#176).

Todo es estático: se escriben fuentes en una carpeta temporal y se leen con
tree-sitter, sin Node.js, sin Docker y sin red.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from qagent.lenguajes import JavaScriptAdapter, TypeScriptAdapter
from qagent.lenguajes.javascript import es_prueba
from qagent.lenguajes.javascript_llamadas import resolver_modulo


def _escribir(raiz: Path, archivos: dict[str, str]) -> None:
    for relativa, codigo in archivos.items():
        ruta = raiz / relativa
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(codigo, encoding="utf-8")


def _funciones(estructura: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        f"{m['ruta']}::{f['nombre']}": f
        for m in estructura["modulos"]
        for f in m["funciones"]
    }


# --- Forma de la estructura -----------------------------------------------------------


def test_misma_forma_que_python_mas_lenguaje(tmp_path: Path) -> None:
    _escribir(
        tmp_path,
        {
            "src/precios.ts": (
                "/** Precio con IVA. @returns {number} */\n"
                "export function conIva(p: number): number { return p * 1.18; }\n"
                "export const sinTipos = (x) => x;\n"
            )
        },
    )
    estructura = TypeScriptAdapter().analizar(tmp_path)

    assert set(estructura) == {"lenguaje", "modulos", "errores", "resumen"}
    assert estructura["lenguaje"] == "typescript"
    [modulo] = estructura["modulos"]
    assert set(modulo) == {"ruta", "huella", "funciones", "endpoints"}
    assert modulo["ruta"] == "src/precios.ts"
    assert len(modulo["huella"]) == 64
    assert modulo["endpoints"] == []
    claves_python = {
        "nombre",
        "linea",
        "firma",
        "parametros",
        "retorno",
        "docstring",
        "ramas",
        "tipada",
        "es_async",
        "llama_a",
    }
    for funcion in modulo["funciones"]:
        assert claves_python <= set(funcion)
    assert estructura["resumen"] == {
        "total_modulos": 1,
        "total_funciones_publicas": 2,
        "total_endpoints": 0,
        "total_errores": 0,
        "inconsistencias": {
            "sin_docstring": {"cantidad": 1, "porcentaje": 50.0},
            "sin_tipos": {"cantidad": 1, "porcentaje": 50.0},
            "con_alguna": {"cantidad": 1, "porcentaje": 50.0},
        },
    }


def test_no_es_una_carpeta(tmp_path: Path) -> None:
    with pytest.raises(NotADirectoryError):
        JavaScriptAdapter().analizar(tmp_path / "no-existe")


# --- Qué archivos se analizan ---------------------------------------------------------


def test_cada_adaptador_lee_sus_extensiones_esm_y_commonjs(tmp_path: Path) -> None:
    _escribir(
        tmp_path,
        {
            "a.js": "export function a() {}",
            "b.mjs": "export function b() {}",
            "c.cjs": "exports.c = function () {};",
            "d.ts": "export function d(): void {}",
            "tipos.d.ts": "export declare function e(): void;",
        },
    )
    js = JavaScriptAdapter().analizar(tmp_path)
    ts = TypeScriptAdapter().analizar(tmp_path)

    assert [m["ruta"] for m in js["modulos"]] == ["a.js", "b.mjs", "c.cjs"]
    assert [m["ruta"] for m in ts["modulos"]] == ["d.ts"]


def test_ignora_dependencias_compilados_y_pruebas_existentes(tmp_path: Path) -> None:
    _escribir(
        tmp_path,
        {
            "src/util.ts": "export function util(): number { return 1; }",
            "node_modules/lib/index.ts": "export function lib() {}",
            "dist/util.js": "export function util() {}",
            "build/util.ts": "export function util() {}",
            "coverage/x.ts": "export function x() {}",
            ".cache/y.ts": "export function y() {}",
            "src/util.test.ts": "export function prueba() {}",
            "src/util.spec.ts": "export function prueba() {}",
            "src/__tests__/caso.ts": "export function caso() {}",
            "src/__mocks__/doble.ts": "export function doble() {}",
            "test/e2e.ts": "export function e2e() {}",
            "tests/unidad.ts": "export function unidad() {}",
        },
    )
    estructura = TypeScriptAdapter().analizar(tmp_path)
    assert [m["ruta"] for m in estructura["modulos"]] == ["src/util.ts"]


def test_carpetas_ignoradas_compartidas_con_python(tmp_path: Path) -> None:
    """``dependencias/`` (#196) también se omite en JS/TS: la lista es compartida."""
    _escribir(
        tmp_path,
        {
            "src/dependencias/pago.ts": "export function pagar(): void {}",
            "src/pago.ts": "export function pagar(): void {}",
        },
    )
    estructura = TypeScriptAdapter().analizar(tmp_path)
    assert [m["ruta"] for m in estructura["modulos"]] == ["src/pago.ts"]


@pytest.mark.parametrize(
    ("ruta", "esperado"),
    [
        ("src/a.test.ts", True),
        ("src/a.spec.mjs", True),
        ("src/A.Test.JSX", True),
        ("src/__tests__/a.ts", True),
        ("test/a.js", True),
        ("src/testing.ts", False),
        ("src/latest.ts", False),
        ("src/test.ts", False),
    ],
)
def test_es_prueba(ruta: str, esperado: bool) -> None:
    assert es_prueba(ruta) is esperado


def test_tsx_y_jsx_con_su_gramatica(tmp_path: Path) -> None:
    _escribir(
        tmp_path,
        {
            "Boton.tsx": "export function Boton(p: { t: string }) { return <b>{p.t}</b>; }",
            "Caja.jsx": "export function Caja(p) { return <div>{p.x}</div>; }",
        },
    )
    assert TypeScriptAdapter().analizar(tmp_path)["errores"] == []
    assert JavaScriptAdapter().analizar(tmp_path)["errores"] == []


def test_errores_de_sintaxis_no_detienen_el_analisis(tmp_path: Path) -> None:
    _escribir(
        tmp_path,
        {
            "bien.ts": "export function bien(): number { return 1; }",
            "mal.ts": "export function mal( {\n  return 1;\n",
        },
    )
    (tmp_path / "binario.ts").write_bytes(b"\xff\xfe\x00export")
    estructura = TypeScriptAdapter().analizar(tmp_path)

    assert [m["ruta"] for m in estructura["modulos"]] == ["bien.ts"]
    errores = {e["ruta"]: e for e in estructura["errores"]}
    assert set(errores) == {"mal.ts", "binario.ts"}
    assert errores["mal.ts"]["tipo"] == "SyntaxError"
    assert isinstance(errores["mal.ts"]["linea"], int)
    assert errores["binario.ts"]["tipo"] == "UnicodeDecodeError"
    assert estructura["resumen"]["total_errores"] == 2


def test_no_sigue_enlaces_simbolicos(tmp_path: Path) -> None:
    fuera = tmp_path / "fuera"
    _escribir(fuera, {"secreto.ts": "export function secreto(): void {}"})
    proyecto = tmp_path / "proyecto"
    _escribir(proyecto, {"a.ts": "export function a(): void {}"})
    try:
        (proyecto / "enlace.ts").symlink_to(fuera / "secreto.ts")
    except OSError:
        pytest.skip("el sistema no permite crear enlaces simbólicos")
    estructura = TypeScriptAdapter().analizar(proyecto)
    assert [m["ruta"] for m in estructura["modulos"]] == ["a.ts"]


def test_bom_utf8(tmp_path: Path) -> None:
    (tmp_path / "a.js").write_bytes("﻿export function á() { return 'ñ'; }".encode())
    [modulo] = JavaScriptAdapter().analizar(tmp_path)["modulos"]
    assert modulo["funciones"][0]["nombre"] == "á"


# --- objetivos() ----------------------------------------------------------------------


def test_objetivos_marca_criticas_las_que_tienen_una_decision(tmp_path: Path) -> None:
    _escribir(
        tmp_path,
        {
            "m.ts": (
                "export function lineal(a: number): number { return a + 1; }\n"
                "export function decide(a: number): number { return a > 0 ? a : -a; }\n"
                "export class C { m(x: number) { if (x) { return 1; } return 0; } }\n"
            )
        },
    )
    adaptador = TypeScriptAdapter()
    assert adaptador.objetivos(adaptador.analizar(tmp_path)) == [
        {"modulo": "m.ts", "tipo": "funcion", "objetivo": "lineal", "critical": False},
        {"modulo": "m.ts", "tipo": "funcion", "objetivo": "decide", "critical": True},
        {"modulo": "m.ts", "tipo": "funcion", "objetivo": "C.m", "critical": True},
    ]


# --- llama_a --------------------------------------------------------------------------


def test_llama_a_mismo_modulo_imports_esm_y_alias(tmp_path: Path) -> None:
    _escribir(
        tmp_path,
        {
            "src/impuestos.ts": (
                "export function iva(p: number): number { return p * 0.18; }\n"
                "export default function redondear(p: number): number { return p; }\n"
                "function oculta() { return 1; }\n"
            ),
            "src/util/index.ts": "export function limpiar(x: number) { return x; }",
            "src/precios.ts": (
                "import redondeo, { iva as impuesto } from './impuestos.js';\n"
                "import * as util from './util';\n"
                "import { externo } from 'lodash';\n"
                "export function base(p: number): number { return p; }\n"
                "export function total(p: number): number {\n"
                "  const xs = [p].map((x) => impuesto(x));\n"
                "  return redondeo(base(p) + xs[0] + util.limpiar(p) + externo(p));\n"
                "}\n"
                "export function recursiva(n: number): number {\n"
                "  return n ? recursiva(n - 1) : 0;\n"
                "}\n"
            ),
        },
    )
    funciones = _funciones(TypeScriptAdapter().analizar(tmp_path))

    assert funciones["src/precios.ts::total"]["llama_a"] == [
        "src/impuestos.ts::iva",
        "src/impuestos.ts::redondear",
        "src/precios.ts::base",
        "src/util/index.ts::limpiar",
    ]
    assert funciones["src/precios.ts::recursiva"]["llama_a"] == []
    assert funciones["src/impuestos.ts::iva"]["llama_a"] == []


def test_llama_a_con_require(tmp_path: Path) -> None:
    _escribir(
        tmp_path,
        {
            "lib/formato.cjs": (
                "function moneda(x) { return x; }\n"
                "function fecha(x) { return x; }\n"
                "module.exports = { moneda, fecha };\n"
            ),
            "lib/calcular.js": "module.exports = function calcular(x) { return x; };",
            "lib/main.js": (
                "const { moneda, fecha: dia } = require('./formato.cjs');\n"
                "const formato = require('./formato.cjs');\n"
                "const calcular = require('./calcular');\n"
                "exports.informe = function (x) {\n"
                "  return moneda(x) + dia(x) + formato.fecha(x) + calcular(x);\n"
                "};\n"
            ),
        },
    )
    funciones = _funciones(JavaScriptAdapter().analizar(tmp_path))
    assert funciones["lib/main.js::informe"]["llama_a"] == [
        "lib/calcular.js::calcular",
        "lib/formato.cjs::fecha",
        "lib/formato.cjs::moneda",
    ]


def test_llama_a_metodos_de_la_clase_y_estaticos(tmp_path: Path) -> None:
    _escribir(
        tmp_path,
        {
            "carrito.ts": (
                "export class Carrito {\n"
                "  static nuevo(): Carrito { return new Carrito(); }\n"
                "  subtotal(): number { return 1; }\n"
                "  private impuesto(): number { return 0; }\n"
                "  total(): number {\n"
                "    Carrito.nuevo();\n"
                "    return this.subtotal() + this.impuesto();\n"
                "  }\n"
                "}\n"
            )
        },
    )
    funciones = _funciones(TypeScriptAdapter().analizar(tmp_path))
    assert funciones["carrito.ts::Carrito.total"]["llama_a"] == [
        "carrito.ts::Carrito.nuevo",
        "carrito.ts::Carrito.subtotal",
    ]


@pytest.mark.parametrize(
    ("origen", "especificador", "esperado"),
    [
        ("src/a.ts", "./b", "src/b.ts"),
        ("src/a.ts", "./b.js", "src/b.ts"),
        ("src/a.ts", "../lib/c", "lib/c.js"),
        ("src/a.ts", "./d", "src/d/index.ts"),
        ("src/a.ts", "lodash", None),
        ("src/a.ts", "../../fuera", None),
        ("src/a.ts", "./no-existe", None),
    ],
)
def test_resolver_modulo(origen: str, especificador: str, esperado: str | None) -> None:
    rutas = {"src/b.ts", "lib/c.js", "src/d/index.ts"}
    assert resolver_modulo(origen, especificador, rutas) == esperado
