"""Corrida real del banco React con Vitest, Testing Library y jsdom (#171, CA3, CA7).

Pasa por el orquestador, el Generator, el guardrail y el Reviewer con el sandbox
``qagent-sandbox:node`` sin red. Necesita Docker y, la primera vez, internet para
instalar React en la imagen derivada del proyecto (``npm install``).
"""

from __future__ import annotations

import shutil

import pytest

from qagent.agents.generator import GeneratorAgent
from qagent.agents.planner import PlannerAgent
from qagent.agents.reviewer import ReviewerAgent
from qagent.lenguajes import TypeScriptAdapter
from qagent.llm import TokenTracker
from qagent.llm.fake import FakeLLMClient
from qagent.orchestrator import Orquestador
from qagent.sandbox import LimitesSandbox
from qagent.sandbox.imagen import _imagen_existe, asegurar_imagen
from qagent.sandbox.modelos import IMAGEN_NODE
from tests.lenguajes.test_banco_react import BANCO, GRABACIONES

pytestmark = [pytest.mark.docker, pytest.mark.red]


def _tiene_testing_library(cliente) -> bool:
    """Si la imagen base ya se construyó con el ``Dockerfile.node`` de #171."""
    historial = cliente.images.get(IMAGEN_NODE).history()
    return any(
        "@testing-library/react" in (c.get("CreatedBy") or "") for c in historial
    )


def test_corrida_react_aprueba_boton_detecta_bug_y_omite_sin_oraculo(
    cliente_docker, tmp_path
) -> None:
    if not _imagen_existe(cliente_docker, IMAGEN_NODE):
        pytest.skip("Falta qagent-sandbox:node.")
    if not _tiene_testing_library(cliente_docker):
        pytest.skip("qagent-sandbox:node es anterior a #171: reconstrúyela.")

    proyecto = tmp_path / "react"
    shutil.copytree(BANCO, proyecto)
    imagen = asegurar_imagen(proyecto, IMAGEN_NODE, cliente_docker)

    adaptador = TypeScriptAdapter()
    estructura = adaptador.analizar(proyecto)
    modulos = {m["ruta"]: m for m in estructura["modulos"]}
    tracker = TokenTracker()
    orquestador = Orquestador(
        PlannerAgent(
            FakeLLMClient(grabaciones=GRABACIONES),
            tracker,
            es_simulado=True,
            adaptador=adaptador,
        ),
        GeneratorAgent(
            FakeLLMClient(grabaciones={}),
            tracker,
            es_simulado=True,
            ruta_proyecto=proyecto,
        ),
        ReviewerAgent(
            tracker,
            proyecto,
            imagen,
            limites=LimitesSandbox(cpus=2.0, memoria="2g", timeout_s=120),
        ),
        tracker=tracker,
        timeout_paso_s=240,
    )

    resultados = {
        ruta: orquestador.ejecutar(modulos[ruta])
        for ruta in ("src/Boton.tsx", "src/Insignia.tsx", "src/Libre.tsx")
    }
    decisiones = {
        o.objetivo: o.decision for r in resultados.values() for o in r.objetivos
    }
    assert decisiones == {"Boton": "accept", "Insignia": "bug_detectado"}

    boton = resultados["src/Boton.tsx"].objetivos[0]
    assert boton.intentos == 1
    ejecucion = boton.revisiones[0]["ejecucion"]
    assert ejecucion["totales"]["total"] == 3
    assert ejecucion["totales"]["pasaron"] == 3
    assert boton.cobertura is not None
    insignia = resultados["src/Insignia.tsx"].objetivos[0]
    assert insignia.revisiones[0]["ejecucion"]["totales"]["fallaron"] == 1
    assert insignia.cobertura is not None

    [omitido] = resultados["src/Libre.tsx"].omitidos
    assert omitido["tipo"] == "componente"
    assert "sin resultado esperado verificable" in omitido["motivo"].lower()
