"""Assertion Laundering en pruebas Vitest (EP-11a, parte 2).

Sin Docker, sin red y sin IA: un caso por cada tipo de laundering, en JavaScript y
en TypeScript, cambios que no son laundering y el rechazo en el Reviewer antes de
ejecutar, registrado en ``laundering_detectado``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qagent import contracts
from qagent.agents.reviewer import ReviewerAgent
from qagent.lenguajes import JavaScriptAdapter, TypeScriptAdapter
from qagent.lenguajes.javascript_laundering import comparar_vitest
from qagent.llm import TokenTracker

ORIGINAL = """import { describe, expect, it } from "vitest";
import { calcularDescuento } from "../proyecto/src/tienda/precios";

describe("calcularDescuento", () => {
  it("descuento_normal", () => {
    expect(calcularDescuento(100, 20)).toBe(80);
  });
  it("porcentaje_invalido", () => {
    expect(() => calcularDescuento(100, 150)).toThrow(RangeError);
  });
});
"""

NORMAL = "expect(calcularDescuento(100, 20)).toBe(80);"

LAUNDERING = {
    "asercion_eliminada": (ORIGINAL.replace(NORMAL, ""), "Aserción eliminada"),
    "valor_esperado_cambiado": (
        ORIGINAL.replace("toBe(80)", "toBe(81)"),
        "Valor esperado cambiado",
    ),
    "toBe_por_toBeDefined": (
        ORIGINAL.replace("toBe(80)", "toBeDefined()"),
        "debilitada de toBe a toBeDefined",
    ),
    "toBe_por_toBeTruthy": (
        ORIGINAL.replace("toBe(80)", "toBeTruthy()"),
        "debilitada de toBe a toBeTruthy",
    ),
    "not_agregado": (
        ORIGINAL.replace(").toBe(80)", ").not.toBe(80)"),
        "Se agregó .not",
    ),
    "try_catch_que_traga": (
        ORIGINAL.replace(NORMAL, f"try {{\n      {NORMAL}\n    }} catch (e) {{}}"),
        "try/catch que se traga el error",
    ),
    "excepcion_generica": (
        ORIGINAL.replace("toThrow(RangeError)", "toThrow()"),
        "Se quitó el valor esperado",
    ),
    "prueba_omitida": (
        ORIGINAL.replace('it("descuento_normal"', 'it.skip("descuento_normal"'),
        "it.skip",
    ),
    "expect_sobre_literal": (
        ORIGINAL.replace(NORMAL, "expect(80).toBe(80);"),
        "literal",
    ),
}


@pytest.mark.parametrize("lenguaje", ["javascript", "typescript"])
@pytest.mark.parametrize("caso", sorted(LAUNDERING))
def test_detecta_cada_tipo_de_laundering(caso: str, lenguaje: str) -> None:
    reparado, motivo = LAUNDERING[caso]

    resultado = comparar_vitest(ORIGINAL, reparado, lenguaje)

    assert resultado.es_laundering is True
    assert resultado.resumen.startswith("Assertion Laundering detectado")
    assert any(motivo in d for d in resultado.diferencias), resultado.diferencias


def test_toEqual_reemplazado_por_toBeDefined() -> None:
    original = ORIGINAL.replace("toBe(80)", "toEqual({ total: 80 })")
    reparado = ORIGINAL.replace("toBe(80)", "toBeDefined()")

    resultado = comparar_vitest(original, reparado, "typescript")

    assert resultado.es_laundering
    assert "debilitada de toEqual a toBeDefined" in resultado.resumen


@pytest.mark.parametrize(
    "reparado",
    [
        ORIGINAL,
        # formato, comillas, comentarios y título
        ORIGINAL.replace(
            NORMAL,
            "// según el JSDoc\n    expect( calcularDescuento(100,20) ).toBe( 80 );",
        ).replace('it("descuento_normal"', "it('aplica el descuento'"),
        # orden de las pruebas
        ORIGINAL.replace(
            '  it("descuento_normal", () => {\n    ' + NORMAL + "\n  });\n", ""
        ).replace(
            "});\n});",
            '});\n  it("descuento_normal", () => {\n    ' + NORMAL + "\n  });\n});",
        ),
        # variable const intermedia
        ORIGINAL.replace(
            NORMAL,
            "const total = calcularDescuento(100, 20);\n    expect(total).toBe(80);",
        ),
        # matcher más estricto
        ORIGINAL.replace("toBe(80)", "toStrictEqual(80)"),
        # try/catch que relanza el error
        ORIGINAL.replace(
            NORMAL, f"try {{\n      {NORMAL}\n    }} catch (e) {{ throw e; }}"
        ),
        # aserción extra
        ORIGINAL.replace(
            NORMAL, NORMAL + "\n    expect(calcularDescuento(0, 0)).toBe(0);"
        ),
    ],
    ids=["identica", "formato", "orden", "alias", "mas_estricto", "relanza", "extra"],
)
def test_cambios_que_no_son_laundering(reparado: str) -> None:
    resultado = comparar_vitest(ORIGINAL, reparado, "typescript")

    assert resultado.es_laundering is False, resultado.diferencias
    assert resultado.resumen.startswith("Sin Assertion Laundering")


def test_un_codigo_que_no_parsea_lanza_syntax_error() -> None:
    with pytest.raises(SyntaxError):
        comparar_vitest(ORIGINAL, "expect(1).toBe(", "javascript")


def test_typescript_admite_anotaciones_de_tipo() -> None:
    reparado = ORIGINAL.replace(
        NORMAL,
        "const total: number = calcularDescuento(100, 20) as number;\n"
        "    expect(total).toBe(81);",
    )

    resultado = comparar_vitest(ORIGINAL, reparado, "typescript")

    assert resultado.es_laundering
    assert TypeScriptAdapter().comparar_aserciones(ORIGINAL, reparado).es_laundering
    assert not JavaScriptAdapter().comparar_aserciones(ORIGINAL, ORIGINAL).es_laundering


# --- Reviewer: se rechaza igual que en Python ------------------------------------

EJEMPLO = (
    Path(__file__).resolve().parents[2]
    / "src/qagent/contracts/ejemplos/planner_contract.v3.typescript.json"
)


def test_el_reviewer_rechaza_el_laundering_antes_de_ejecutar(tmp_path: Path) -> None:
    contrato = json.loads(EJEMPLO.read_text(encoding="utf-8"))
    anterior = contracts.generated_test_para(contrato, 1, ORIGINAL, "generado.test.ts")
    reparado = contracts.generated_test_para(
        contrato, 2, ORIGINAL.replace("toBe(80)", "toBeTruthy()"), "generado.test.ts"
    )

    def ejecutor(*_):
        raise AssertionError("el guardrail corre antes de ejecutar")

    revision = ReviewerAgent(
        TokenTracker(), tmp_path, "img", ejecutor=ejecutor
    ).revisar(contrato, reparado, anterior)

    contracts.validar(contracts.REVIEW_RESULT, revision)
    assert revision["laundering_detectado"] is True
    assert revision["tipo_fallo"] == "error_test"
    assert revision["decision"] == "retry"
    assert "toBeTruthy" in revision["feedback"]
