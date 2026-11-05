"""Generación de pruebas Vitest y su oráculo (EP-11a, parte 2).

Sin Docker ni red y con la IA simulada: el Generator escribe la prueba a partir del
contrato y las reglas del adaptador revisan su sintaxis y su oráculo sin ejecutarla.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from qagent import contracts
from qagent.agents.generator import ErrorRespuestaGenerator, GeneratorAgent
from qagent.lenguajes import JavaScriptAdapter, TypeScriptAdapter
from qagent.lenguajes.javascript_generacion import (
    codigo_vitest,
    contexto_vitest,
    ruta_importacion,
    validar_vitest,
)
from qagent.llm import TokenTracker
from qagent.llm.fake import FakeLLMClient
from qagent.llm.modelos import RespuestaLLM

EJEMPLO = (
    Path(__file__).resolve().parents[2]
    / "src/qagent/contracts/ejemplos/planner_contract.v3.typescript.json"
)


def _contrato_ts() -> dict[str, Any]:
    return json.loads(EJEMPLO.read_text(encoding="utf-8"))


def _contrato_js() -> dict[str, Any]:
    contrato = _contrato_ts()
    contrato.update(
        lenguaje="javascript",
        modulo="src/tienda/precios.js",
        firma="calcularDescuento(precio, porcentaje)",
    )
    return contrato


class ClienteFijo:
    """Devuelve siempre el mismo código y guarda los prompts."""

    def __init__(self, contenido: str) -> None:
        self.contenido = contenido
        self.prompts: list[str] = []

    def generar(self, prompt: str, rol: str = "generator") -> RespuestaLLM:
        self.prompts.append(prompt)
        return RespuestaLLM(self.contenido, 0, 0, 0.0, "fijo")


# --- archivo_de_prueba -----------------------------------------------------------


def test_archivo_de_prueba_segun_el_lenguaje() -> None:
    assert TypeScriptAdapter().archivo_de_prueba("calcularDescuento") == (
        "generado.test.ts"
    )
    assert JavaScriptAdapter().archivo_de_prueba("calcularDescuento") == (
        "generado.test.js"
    )


def test_ruta_de_importacion_desde_la_carpeta_de_pruebas() -> None:
    assert ruta_importacion("src/precios.ts") == "../proyecto/src/precios"
    assert ruta_importacion("src/vista.tsx") == "../proyecto/src/vista"
    assert ruta_importacion("lib/precios.js") == "../proyecto/lib/precios.js"
    with pytest.raises(ValueError):
        ruta_importacion("../fuera.ts")


# --- Generator con la IA simulada ------------------------------------------------


@pytest.mark.parametrize(
    ("contrato", "archivo", "importacion"),
    [
        (_contrato_ts(), "generado.test.ts", '"../proyecto/src/tienda/precios"'),
        (_contrato_js(), "generado.test.js", '"../proyecto/src/tienda/precios.js"'),
    ],
)
def test_el_generator_produce_generated_test_v2_con_vitest(
    contrato: dict[str, Any], archivo: str, importacion: str
) -> None:
    generado = GeneratorAgent(
        FakeLLMClient(), TokenTracker(), es_simulado=True
    ).generar(contrato, 1, None)

    contracts.validar(contracts.GENERATED_TEST_V2, generado)
    assert generado["lenguaje"] == contrato["lenguaje"]
    assert generado["framework_pruebas"] == "vitest"
    assert generado["archivo"] == archivo
    codigo = generado["codigo"]
    assert 'import { describe, expect, it } from "vitest";' in codigo
    assert f"import {{ calcularDescuento }} from {importacion};" in codigo
    assert 'describe("calcularDescuento"' in codigo
    assert "expect(calcularDescuento(100, 20)).toBe(80);" in codigo
    assert "expect(() => calcularDescuento(100, 150)).toThrow(RangeError);" in codigo
    adaptador = (
        TypeScriptAdapter()
        if contrato["lenguaje"] == "typescript"
        else (JavaScriptAdapter())
    )
    assert adaptador.validar_oraculo(contrato, codigo, Path(".")) is None


def test_el_prompt_lleva_reglas_contexto_y_contrato() -> None:
    prompt = TypeScriptAdapter().prompt_generator(_contrato_ts(), 2, "falló", None)

    assert "Vitest en TypeScript" in prompt
    assert "Prohibido: .not, toBeDefined, toBeTruthy" in prompt
    assert "Este es el intento 2." in prompt
    assert "falló" in prompt
    assert "CONTRATO_JSON:" in prompt


def test_un_error_de_sintaxis_se_rechaza_y_vuelve_como_intento() -> None:
    malo = 'import { expect, it } from "vitest";\nit("x", () => { expect(1).toBe(\n'
    agente = GeneratorAgent(ClienteFijo(malo), TokenTracker())

    with pytest.raises(ErrorRespuestaGenerator, match="TypeScript inválido") as error:
        agente.generar(_contrato_ts(), 1, None)
    assert error.value.codigo == malo  # el orquestador lo reenvía como feedback
    assert TypeScriptAdapter().reglas_revision().error_de_sintaxis(malo)


def test_el_generator_quita_la_cerca_markdown() -> None:
    contrato = _contrato_ts()
    codigo = codigo_vitest(contrato, contexto_vitest(contrato, None))
    agente = GeneratorAgent(ClienteFijo(f"```ts\n{codigo}```"), TokenTracker())

    assert agente.generar(contrato, 1, None)["codigo"] == codigo


# --- Contexto desde la fuente ----------------------------------------------------


def test_exportacion_default_y_metodo_de_instancia_salen_de_la_fuente(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src/carrito.ts").write_text(
        "export default class Carrito {\n"
        "  /** @example new Carrito().total(2) // => 4 */\n"
        "  total(n: number): number { return n * 2; }\n"
        "}\n",
        encoding="utf-8",
    )
    contrato = {
        **_contrato_ts(),
        "modulo": "src/carrito.ts",
        "objetivo": "Carrito.total",
        "firma": "total(n: number): number",
        "casos": [
            {
                "id": "doble",
                "entrada": {"n": 2},
                "valor_esperado": 4,
                "origen": "docstring",
            }
        ],
    }

    contexto = contexto_vitest(contrato, tmp_path)

    assert contexto["importacion"] == 'import Carrito from "../proyecto/src/carrito";'
    codigo = codigo_vitest(contrato, contexto)
    assert "expect(new Carrito().total(2)).toBe(4);" in codigo
    assert validar_vitest(contrato, codigo, contexto) is None


def test_funcion_async_usa_resolves_y_rejects() -> None:
    contrato = {
        **_contrato_ts(),
        "firma": "async calcularDescuento(p: number, q: number): Promise<number>",
    }

    codigo = codigo_vitest(contrato, contexto_vitest(contrato, None))

    assert 'it("descuento_normal", async () => {' in codigo
    assert "await expect(calcularDescuento(100, 20)).resolves.toBe(80);" in codigo
    assert (
        "await expect(calcularDescuento(100, 150)).rejects.toThrow(RangeError);"
        in codigo
    )
    assert validar_vitest(contrato, codigo) is None


def test_valores_decimales_objetos_y_null() -> None:
    contrato = _contrato_ts()
    contrato["casos"] = [
        {
            "id": "decimal",
            "entrada": [1, 3],
            "valor_esperado": 0.5,
            "origen": "docstring",
        },
        {
            "id": "objeto",
            "entrada": [1, 2],
            "valor_esperado": {"a": [1]},
            "origen": "docstring",
        },
        {
            "id": "nulo",
            "entrada": [0, 0],
            "valor_esperado": None,
            "origen": "docstring",
        },
    ]

    codigo = codigo_vitest(contrato, contexto_vitest(contrato, None))

    assert "toBeCloseTo(0.5)" in codigo
    assert 'toEqual({"a": [1]})' in codigo
    assert "toBe(null)" in codigo
    assert validar_vitest(contrato, codigo) is None


# --- Oráculo ---------------------------------------------------------------------


def _valido() -> str:
    contrato = _contrato_ts()
    return codigo_vitest(contrato, contexto_vitest(contrato, None))


@pytest.mark.parametrize(
    ("cambio", "motivo"),
    [
        (lambda c: c.replace("toBe(80)", "toBe(81)"), "descuento_normal"),
        (lambda c: c.replace("toBe(80)", "toBeDefined()"), "descuento_normal"),
        (lambda c: c.replace(").toBe(80)", ").not.toBe(80)"), "descuento_normal"),
        (lambda c: c.replace("RangeError", "TypeError"), "porcentaje_invalido"),
        (lambda c: c.replace('it("descuento', 'it.skip("descuento'), "it.skip"),
        (lambda c: c.replace('"vitest"', '"jest"'), "vitest"),
        (
            lambda c: c.replace("../proyecto/src/tienda/precios", "./precios"),
            "importar la función",
        ),
        (lambda c: c.replace("calcularDescuento(100, 20)", "80"), "literal"),
    ],
)
def test_el_oraculo_rechaza_pruebas_que_no_comprueban_el_contrato(
    cambio, motivo: str
) -> None:
    contrato = _contrato_ts()

    error = validar_vitest(contrato, cambio(_valido()))

    assert error is not None and error.startswith("Oráculo inválido")
    assert motivo in error


def test_el_reviewer_rechaza_un_oraculo_invalido_sin_ejecutar(tmp_path: Path) -> None:
    from qagent.agents.reviewer import ReviewerAgent

    contrato = _contrato_ts()
    test = contracts.generated_test_para(
        contrato, 1, _valido().replace("toBe(80)", "toBe(81)"), "generado.test.ts"
    )

    def ejecutor(*_):
        raise AssertionError("no debe ejecutar")

    revision = ReviewerAgent(
        TokenTracker(), tmp_path, "img", ejecutor=ejecutor
    ).revisar(contrato, test, None)

    assert revision["decision"] == "retry"
    assert revision["tipo_fallo"] == "error_test"
    assert revision["laundering_detectado"] is False
    assert "descuento_normal" in revision["feedback"]


def test_el_contrato_no_se_modifica() -> None:
    contrato = _contrato_ts()
    copia = copy.deepcopy(contrato)
    TypeScriptAdapter().prompt_generator(contrato, 1, None, None)
    assert contrato == copia
