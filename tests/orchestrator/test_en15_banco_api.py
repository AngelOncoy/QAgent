"""EN-15: generación TestClient y banco FastAPI con IA simulada.

La prueba rápida valida contratos y código generado sin ejecutar el banco. La prueba
marcada ``docker`` ejecuta los seis tests generados dentro del sandbox sin red.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from qagent import contracts
from qagent.agents import GeneratorAgent, PlannerAgent, ReviewerAgent
from qagent.analysis import analizar_proyecto
from qagent.llm import FakeLLMClient, TokenTracker
from qagent.orchestrator import Estado, Orquestador
from qagent.sandbox import (
    DockerNoDisponible,
    ImagenNoEncontrada,
    construir_imagen_base,
    ejecutar_pruebas,
    obtener_cliente,
    preparar_imagen,
)

RAIZ = Path(__file__).resolve().parents[2]
BANCO = RAIZ / "bench_api"
CORRECTOS = {"GET /salud", "POST /items", "GET /items"}
CON_BUG = {
    "GET /items/{item_id}",
    "DELETE /items/{item_id}",
    "GET /descuento",
}


def contratos_del_banco() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Obtiene los contratos reales de HU-27 con las grabaciones de endpoints."""
    [modulo] = analizar_proyecto(BANCO)["modulos"]
    fuente = (BANCO / "api_mvp.py").read_text(encoding="utf-8")
    planner = PlannerAgent(FakeLLMClient(), TokenTracker(), es_simulado=True)
    resultado = planner.planificar_endpoints(modulo, fuente)
    for contrato in resultado:
        contracts.validar(contracts.PLANNER, contrato)
    return modulo, resultado


def test_genera_un_testclient_valido_por_cada_endpoint_con_cero_tokens() -> None:
    _, plan = contratos_del_banco()
    tracker = TokenTracker()
    generator = GeneratorAgent(FakeLLMClient(), tracker, es_simulado=True)

    generados = [generator.generar(contrato, 1, None) for contrato in plan]

    assert len(generados) == 6
    assert {test["objetivo"] for test in generados} == CORRECTOS | CON_BUG
    for test in generados:
        ast.parse(test["codigo"])
        assert "TestClient" in test["codigo"]
        assert "client.request" in test["codigo"]
        assert "assert response.status_code" in test["codigo"]
    assert tracker.total_tokens == 0
    assert tracker.total_costo_usd == 0.0


@pytest.mark.docker
@pytest.mark.red
def test_banco_api_generado_detecta_exactamente_los_tres_bugs() -> None:
    """Seis tests generados; ejecución dentro de Docker con ``network_mode=none``."""
    try:
        cliente_docker = obtener_cliente()
    except DockerNoDisponible as error:
        pytest.skip(str(error))

    try:
        imagen = preparar_imagen(BANCO, cliente_docker)
    except ImagenNoEncontrada:
        construir_imagen_base(cliente_docker)
        imagen = preparar_imagen(BANCO, cliente_docker)
    modulo, plan = contratos_del_banco()
    tracker = TokenTracker()
    cliente = FakeLLMClient()
    orquestador = Orquestador(
        planner=None,  # no se usa: el plan estático se entrega como spec reutilizada
        generator=GeneratorAgent(cliente, tracker, es_simulado=True),
        reviewer=ReviewerAgent(
            tracker,
            BANCO,
            imagen,
            cliente=cliente,
            es_simulado=True,
        ),
        tracker=tracker,
    )

    resultado = orquestador.ejecutar(modulo, plan_reutilizado=plan)
    decisiones = {
        objetivo.objetivo: objetivo.decision for objetivo in resultado.objetivos
    }
    diagnostico = {
        objetivo.objetivo: [revision["feedback"] for revision in objetivo.revisiones]
        for objetivo in resultado.objetivos
    }

    assert resultado.estado_final == Estado.FIN, resultado.motivo_fallo
    assert {k for k, v in decisiones.items() if v == "accept"} == CORRECTOS, (
        decisiones,
        diagnostico,
    )
    assert {k for k, v in decisiones.items() if v == "bug_detectado"} == CON_BUG, (
        decisiones,
        diagnostico,
    )
    assert tracker.total_tokens == 0
    assert tracker.total_costo_usd == 0.0


@pytest.mark.docker
@pytest.mark.red
@pytest.mark.parametrize(
    ("objetivo", "exit_code_esperado", "resumen_esperado"),
    [
        ("POST /items", 0, "4 passed"),
        ("GET /items/{item_id}", 1, "1 failed, 3 passed"),
    ],
)
def test_dependency_overrides_se_restauran_despues_del_test_en_sandbox(
    tmp_path: Path,
    objetivo: str,
    exit_code_esperado: int,
    resumen_esperado: str,
) -> None:
    """Comprueba el ``finally`` tras un caso aprobado y otro que detecta un bug."""
    try:
        cliente_docker = obtener_cliente()
    except DockerNoDisponible as error:
        pytest.skip(str(error))

    try:
        imagen = preparar_imagen(BANCO, cliente_docker)
    except ImagenNoEncontrada:
        construir_imagen_base(cliente_docker)
        imagen = preparar_imagen(BANCO, cliente_docker)

    _, plan = contratos_del_banco()
    contrato = next(item for item in plan if item["objetivo"] == objetivo)
    generator = GeneratorAgent(FakeLLMClient(), TokenTracker(), es_simulado=True)
    generado = generator.generar(contrato, 1, None)
    carpeta_tests = tmp_path / "tests"
    carpeta_tests.mkdir()
    (carpeta_tests / "test_01_generado.py").write_text(
        generado["codigo"], encoding="utf-8"
    )
    (carpeta_tests / "test_02_limpieza.py").write_text(
        "from api_mvp import app\n\n"
        "def test_dependency_overrides_quedo_vacio():\n"
        "    assert app.dependency_overrides == {}\n",
        encoding="utf-8",
    )

    resultado = ejecutar_pruebas(
        imagen,
        BANCO,
        carpeta_tests,
        "api_mvp",
        cliente=cliente_docker,
    )

    assert resultado.exit_code == exit_code_esperado, resultado.stdout
    assert resumen_esperado in resultado.stdout
