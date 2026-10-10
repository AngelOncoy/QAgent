"""Pruebas de PlannerAgent sin usar una API real."""

from __future__ import annotations

import json

import pytest

from pyagent import contracts
from pyagent.agents.planner import ErrorRespuestaPlanner, PlannerAgent
from pyagent.llm import RespuestaLLM, TokenTracker

MODULO = {
    "ruta": "calculadora.py",
    "huella": "a" * 64,
    "funciones": [
        {
            "nombre": "duplicar",
            "firma": "(x: int) -> int",
            "docstring": "Devuelve x multiplicado por dos.",
            "llama_a": [],
        }
    ],
}

PLAN = [
    {
        "version": "2",
        "modulo": "calculadora.py",
        "huella": "a" * 64,
        "tipo": "funcion",
        "objetivo": "duplicar",
        "firma": "(x: int) -> int",
        "critical": False,
        "llama_a": [],
        "casos": [
            {
                "id": "duplica_positivo",
                "entrada": {"x": 2},
                "valor_esperado": 4,
                "origen": "docstring",
            }
        ],
    }
]


class ClienteGrabado:
    """Cliente que devuelve una respuesta controlada."""

    def __init__(self, contenido: str) -> None:
        self.contenido = contenido
        self.llamadas: list[tuple[str, str]] = []

    def generar(self, prompt: str, rol: str = "generator") -> RespuestaLLM:
        self.llamadas.append((prompt, rol))
        return RespuestaLLM(
            contenido=self.contenido,
            tokens_entrada=100,
            tokens_salida=40,
            costo_usd=0.01,
            modelo="modelo-prueba",
        )


def test_planner_devuelve_contratos_validos() -> None:
    cliente = ClienteGrabado(json.dumps(PLAN))
    planner = PlannerAgent(cliente, TokenTracker())

    resultado = planner.planificar(MODULO)

    assert resultado == PLAN
    assert contracts.es_valido(contracts.PLANNER, resultado[0])


def test_planner_envia_estructura_y_registra_tokens() -> None:
    cliente = ClienteGrabado(json.dumps(PLAN))
    tracker = TokenTracker()
    planner = PlannerAgent(cliente, tracker)

    planner.planificar(MODULO)

    prompt, rol = cliente.llamadas[0]
    assert rol == "planner"
    assert "calculadora.py" in prompt
    assert "duplicar" in prompt
    assert "No ejecutes" in prompt

    [llamada] = tracker.llamadas
    assert llamada.agente == "planner"
    assert llamada.tokens_entrada == 100
    assert llamada.tokens_salida == 40


def test_planner_acepta_json_dentro_de_cerca_markdown() -> None:
    cliente = ClienteGrabado(f"```json\n{json.dumps(PLAN)}\n```")
    planner = PlannerAgent(cliente, TokenTracker())

    assert planner.planificar(MODULO) == PLAN


def test_planner_rechaza_json_invalido() -> None:
    cliente = ClienteGrabado("esto no es JSON")
    planner = PlannerAgent(cliente, TokenTracker())

    with pytest.raises(ErrorRespuestaPlanner, match="JSON válido"):
        planner.planificar(MODULO)


def test_planner_rechaza_un_objeto_en_lugar_de_lista() -> None:
    cliente = ClienteGrabado(json.dumps(PLAN[0]))
    planner = PlannerAgent(cliente, TokenTracker())

    with pytest.raises(ErrorRespuestaPlanner, match="lista"):
        planner.planificar(MODULO)
