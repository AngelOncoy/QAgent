"""Cliente de IA simulada (Fake LLM) con respuestas pregrabadas.

Permite desarrollar y ejecutar pruebas unitarias con consumo estricto de 0 tokens.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, ClassVar


@dataclass
class RespuestaLLM:
    """Estructura de respuesta uniforme devuelta por el cliente LLM."""

    contenido: str
    tokens_entrada: int
    tokens_salida: int
    costo_usd: float
    modelo: str
    datos_json: dict[str, Any] | None = None


class FakeLLMClient:
    """Simulador de LLM que devuelve respuestas grabadas y reporta 0 tokens."""

    # Respuestas que cumplen los contratos de contracts/ (EN-01): el Planner devuelve una
    # lista de planner_contract.v2 por módulo y el Reviewer un review_result.
    RESPUESTAS_GRABADAS: ClassVar[dict[str, str]] = {
        "planner": json.dumps(
            [
                {
                    "version": "2",
                    "modulo": "modulo_simulado.py",
                    "huella": "0" * 64,
                    "tipo": "funcion",
                    "objetivo": "duplicar",
                    "firma": "(x: int) -> int",
                    "critical": False,
                    "llama_a": [],
                    "casos": [
                        {
                            "id": "caso_1",
                            "entrada": {"x": 10},
                            "valor_esperado": 20,
                            "origen": "docstring",
                        }
                    ],
                }
            ]
        ),
        "generator": (
            "from modulo_simulado import duplicar\n\n\n"
            "def test_caso_1():\n"
            "    assert duplicar(10) == 20\n"
        ),
        "reviewer": json.dumps(
            {
                "version": "1",
                "objetivo": "duplicar",
                "intento": 1,
                "estado_sandbox": "ok",
                "cobertura": {"lineas": 100.0, "ramas": 100.0},
                "laundering_detectado": False,
                "tipo_fallo": None,
                "hash_error": None,
                "decision": "accept",
                "feedback": "Test aprobado en sandbox.",
            }
        ),
    }

    def __init__(self, modelo: str = "fake-model-v1") -> None:
        self.modelo = modelo

    def generar(self, prompt: str, rol: str = "generator") -> RespuestaLLM:
        """Devuelve una respuesta grabada según el rol del agente con 0 tokens de consumo.

        Args:
            prompt: Texto o instrucción enviada (no se envía a internet).
            rol: Rol del agente que solicita la respuesta ('planner', 'generator', 'reviewer').

        Returns:
            RespuestaLLM: Objeto con contenido grabado y 0 tokens consumidos.
        """
        contenido = self.RESPUESTAS_GRABADAS.get(
            rol.lower(), f"Respuesta simulada para prompt: {prompt[:30]}..."
        )

        return RespuestaLLM(
            contenido=contenido,
            tokens_entrada=0,
            tokens_salida=0,
            costo_usd=0.0,
            modelo=self.modelo,
        )
