"""Banco TA-01: Planner, Generator y guardrail reales, sin ejecutar Java (#184)."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from qagent import contracts
from qagent.agents.generator import GeneratorAgent
from qagent.agents.planner import PlannerAgent
from qagent.agents.reviewer import ReviewerAgent
from qagent.lenguajes import JavaAdapter
from qagent.llm import FakeLLMClient, TokenTracker
from tests.agents.test_generator_java import ClienteJUnitGrabado

BANCO = Path(__file__).resolve().parents[2] / "bench_java"
CASOS = {
    "BancoCorrecto.sumarPrecios": (
        {"precios": [10, 20]},
        30,
        "assertEquals(30.0, BancoCorrecto.sumarPrecios(List.of(10.0, 20.0)));",
        "assertEquals(0.0, BancoCorrecto.sumarPrecios(List.of(10.0, 20.0)));",
    ),
    "BancoCorrecto.aplicarDescuento": (
        {"precio": 100, "porcentaje": 20},
        80,
        "assertEquals(80.0, BancoCorrecto.aplicarDescuento(100.0, 20.0));",
        "assertNotNull(BancoCorrecto.aplicarDescuento(100.0, 20.0));",
    ),
    "BancoCorrecto.esMayorDeEdad": (
        {"edad": 18},
        True,
        "assertTrue(BancoCorrecto.esMayorDeEdad(18));",
        "assertTrue(true);",
    ),
    "BancoDefectuoso.calcularPromedio": (
        {"numeros": [2, 3]},
        2.5,
        "assertEquals(2.5, BancoDefectuoso.calcularPromedio(List.of(2, 3)));",
        "assertEquals(2.0, BancoDefectuoso.calcularPromedio(List.of(2, 3)));",
    ),
    "BancoDefectuoso.calcularEnvio": (
        {"importe": 100},
        0,
        "assertEquals(0.0, BancoDefectuoso.calcularEnvio(100.0));",
        "assertEquals(10.0, BancoDefectuoso.calcularEnvio(100.0));",
    ),
    "BancoDefectuoso.calcularTotalConImpuesto": (
        {"subtotal": 100, "porcentaje": 18},
        118,
        "assertEquals(118.0, BancoDefectuoso.calcularTotalConImpuesto(100.0, 18.0));",
        "assertEquals(82.0, BancoDefectuoso.calcularTotalConImpuesto(100.0, 18.0));",
    ),
}


@pytest.fixture(scope="module")
def planes_banco() -> dict[str, dict]:
    """Planifica las fuentes reales; los casos grabados proceden de casos.md/Javadoc."""
    adaptador = JavaAdapter()
    estructura = adaptador.analizar(BANCO)
    assert estructura["errores"] == []
    grabadas = {
        nombre.split(".")[0] + ".java::" + nombre: [
            {
                "id": "caso_contrato",
                "entrada": entrada,
                "valor_esperado": esperado,
                "origen": "docstring",
                "categoria": "limite" if nombre.endswith("calcularEnvio") else "normal",
            }
        ]
        for nombre, (entrada, esperado, _, _) in CASOS.items()
    }
    tracker = TokenTracker()
    planner = PlannerAgent(
        FakeLLMClient(grabaciones=grabadas),
        tracker,
        adaptador=adaptador,
        es_simulado=True,
    )
    planes = {
        p["objetivo"]: p
        for modulo in estructura["modulos"]
        for p in planner.planificar(modulo)
    }
    assert set(planes) == set(CASOS)
    assert tracker.total_tokens == 0
    return planes


@pytest.mark.parametrize("objetivo", list(CASOS))
def test_banco_genera_junit_y_rechaza_debilitamiento(
    planes_banco: dict[str, dict], objetivo: str
) -> None:
    """Seis métodos pasan por generación y validación reales con el ejecutor prohibido.

    Solo el cliente LLM devuelve código grabado. No se reemplazan el Generator,
    oráculo ni comparador. No demuestra ejecución JUnit, que pertenece a #182.
    """
    contrato = planes_banco[objetivo]
    _, esperado, asercion, debilitada = CASOS[objetivo]
    assert contrato["casos"][0]["valor_esperado"] == esperado
    clase = objetivo.split(".")[0]
    codigo = (
        "package org.qagent.bench;\nimport java.util.List;\n"
        "import org.junit.jupiter.api.Test;\nimport static org.junit.jupiter.api.Assertions.*;\n"
        "class " + clase + "Test {\n"
        "    /** Comprueba el resultado declarado en el contrato del Planner. */\n"
        "    @Test void test_caso_contrato() { " + asercion + " }\n}\n"
    )
    tracker = TokenTracker()
    generator = GeneratorAgent(
        ClienteJUnitGrabado(codigo), tracker, es_simulado=True, ruta_proyecto=BANCO
    )
    test = generator.generar(contrato, 1, None)
    contracts.validar_versionado(contracts.FAMILIA_GENERATED_TEST, test)
    assert test["archivo"] == "src/test/java/org/qagent/bench/" + clase + "Test.java"
    assert test["codigo"] == codigo
    adaptador = JavaAdapter()
    assert adaptador.validar_oraculo(contrato, codigo, BANCO) is None
    reparado = codigo.replace(asercion, debilitada)
    assert adaptador.validar_oraculo(contrato, reparado, BANCO) is not None
    assert adaptador.comparar_aserciones(codigo, reparado).es_laundering
    ejecutor = Mock(
        side_effect=AssertionError("Un JUnit debilitado no debe ejecutarse.")
    )
    cliente_reviewer = Mock()
    cliente_reviewer.generar.side_effect = AssertionError(
        "El guardrail no consulta IA."
    )
    reviewer = ReviewerAgent(
        tracker, BANCO, "sin-uso", cliente=cliente_reviewer, ejecutor=ejecutor
    )
    revision = reviewer.revisar(
        contrato,
        contracts.generated_test_para(contrato, 2, reparado, test["archivo"]),
        test,
    )
    assert revision["laundering_detectado"] is True
    assert revision["decision"] == "retry"
    assert "ejecucion" not in revision
    ejecutor.assert_not_called()
    cliente_reviewer.generar.assert_not_called()
    assert tracker.total_tokens == 0
    print(
        f"{objetivo}: generated_test.v2; archivo={test['archivo']}; oraculo=valido; debilitamiento=rechazado; ejecutor=0",
        flush=True,
    )
