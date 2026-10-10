"""Integración de los agentes reales con el orquestador de HU-11."""

from __future__ import annotations

import json
from pathlib import Path

from pyagent.agents import GeneratorAgent, PlannerAgent, ReviewerAgent
from pyagent.llm import RespuestaLLM, TokenTracker
from pyagent.orchestrator import Estado, Orquestador
from pyagent.sandbox import ResultadoSandbox

MODULO = {
    "ruta": "calculadora.py",
    "huella": "a" * 64,
    "funciones": [
        {
            "nombre": "duplicar",
            "firma": "(x: int) -> int",
            "docstring": "Devuelve el doble de x.",
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

TEST_ROTO = """\
from calculadora import duplicar


def test_duplicar()
    assert duplicar(2) == 4
"""

TEST_CORREGIDO = """\
from calculadora import duplicar


def test_duplicar():
    assert duplicar(2) == 4
"""


class ClienteSecuencial:
    """Devuelve respuestas controladas en el orden configurado."""

    def __init__(self, respuestas: list[str], modelo: str) -> None:
        self.respuestas = list(respuestas)
        self.modelo = modelo
        self.llamadas: list[tuple[str, str]] = []

    def generar(self, prompt: str, rol: str = "generator") -> RespuestaLLM:
        self.llamadas.append((prompt, rol))
        return RespuestaLLM(
            contenido=self.respuestas.pop(0),
            tokens_entrada=10,
            tokens_salida=5,
            costo_usd=0.0,
            modelo=self.modelo,
        )


class EjecutorExitoso:
    """Simula que el test corregido pasa dentro del sandbox."""

    def __init__(self) -> None:
        self.llamadas = 0

    def __call__(
        self,
        imagen: str,
        ruta_proyecto: Path,
        ruta_tests: Path,
        modulo_cov: str,
    ) -> ResultadoSandbox:
        self.llamadas += 1
        codigo = ruta_tests.joinpath("test_generado.py").read_text(encoding="utf-8")
        assert "def test_duplicar():" in codigo
        return ResultadoSandbox(
            exit_code=0,
            stdout="1 passed",
            stderr="",
            coverage={
                "totals": {
                    "percent_covered": 100.0,
                    "num_branches": 0,
                    "covered_branches": 0,
                }
            },
            duracion_s=0.1,
        )


def test_error_de_sintaxis_se_reintenta_y_la_corrida_termina(
    tmp_path: Path,
) -> None:
    tracker = TokenTracker()
    cliente_planner = ClienteSecuencial([json.dumps(PLAN)], "planner-prueba")
    cliente_generator = ClienteSecuencial(
        [TEST_ROTO, TEST_CORREGIDO],
        "generator-prueba",
    )
    ejecutor = EjecutorExitoso()

    planner = PlannerAgent(cliente_planner, tracker, es_simulado=True)
    generator = GeneratorAgent(cliente_generator, tracker, es_simulado=True)
    reviewer = ReviewerAgent(
        tracker,
        tmp_path,
        "imagen-prueba",
        ejecutor=ejecutor,
        es_simulado=True,
    )
    orquestador = Orquestador(
        planner,
        generator,
        reviewer,
        tracker=tracker,
    )

    resultado = orquestador.ejecutar(MODULO)

    assert resultado.estado_final is Estado.FIN
    assert resultado.motivo_fallo is None

    [objetivo] = resultado.objetivos
    assert objetivo.intentos == 2
    assert objetivo.revisiones[0]["tipo_fallo"] == "error_test"
    assert objetivo.revisiones[0]["decision"] == "retry"
    assert objetivo.revisiones[1]["decision"] == "accept"
    assert objetivo.decision == "accept"

    assert len(cliente_planner.llamadas) == 1
    assert len(cliente_generator.llamadas) == 2
    assert "SyntaxError" in cliente_generator.llamadas[1][0]
    assert ejecutor.llamadas == 1

    assert resultado.traza_estados == [
        Estado.PLANIFICAR,
        Estado.GENERAR,
        Estado.EJECUTAR_REVISAR,
        Estado.REINTENTAR,
        Estado.GENERAR,
        Estado.EJECUTAR_REVISAR,
        Estado.FIN,
    ]
