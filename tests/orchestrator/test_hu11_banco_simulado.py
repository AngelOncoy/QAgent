"""Corrida de punta a punta sobre el banco con la IA simulada y Docker real (HU-11).

Ensayo de EV-01 sin gastar tokens: Planner y Generator simulados (casos grabados en
`bench/ia_simulada.json`), Reviewer real ejecutando en el sandbox. Las 3 funciones
con bug sembrado deben terminar en `bug_detectado` y las 3 correctas en `accept`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyagent.agents import GeneratorAgent, PlannerAgent, ReviewerAgent
from pyagent.analysis.analyzer import analizar_proyecto
from pyagent.llm import FakeLLMClient, TokenTracker
from pyagent.orchestrator import Estado, Orquestador

BANCO = Path(__file__).resolve().parents[2] / "bench"
CON_BUG = {"calcular_descuento", "clasificar_edad", "buscar_elemento_mayor"}
SIN_BUG = {"es_palindromo", "invertir_palabras", "formatear_moneda"}


@pytest.fixture(scope="module")
def imagen_base() -> str:
    from pyagent.sandbox import (
        DockerNoDisponible,
        construir_imagen_base,
        obtener_cliente,
    )
    from pyagent.sandbox.imagen import IMAGEN_BASE, _imagen_existe

    try:
        cliente = obtener_cliente()
    except DockerNoDisponible as exc:
        pytest.skip(str(exc))
    if not _imagen_existe(cliente, IMAGEN_BASE):
        construir_imagen_base(cliente)
    return IMAGEN_BASE


@pytest.mark.docker
def test_banco_con_ia_simulada_detecta_los_bugs_sembrados(imagen_base: str) -> None:
    [modulo] = analizar_proyecto(BANCO)["modulos"]
    tracker = TokenTracker()
    cliente = FakeLLMClient()
    orquestador = Orquestador(
        PlannerAgent(cliente, tracker, es_simulado=True),
        GeneratorAgent(cliente, tracker, es_simulado=True),
        ReviewerAgent(tracker, BANCO, imagen_base, es_simulado=True),
    )

    resultado = orquestador.ejecutar(modulo)

    assert resultado.estado_final == Estado.FIN, resultado.motivo_fallo
    decisiones = {o.objetivo: o.decision for o in resultado.objetivos}
    assert decisiones == {
        **{nombre: "bug_detectado" for nombre in CON_BUG},
        **{nombre: "accept" for nombre in SIN_BUG},
    }
    assert tracker.total_tokens == 0
