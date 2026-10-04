"""Cliente de IA simulada (Fake LLM) con respuestas pregrabadas.

Permite desarrollar y ejecutar pruebas unitarias con consumo estricto de 0 tokens.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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

    RESPUESTAS_GRABADAS = {
        "planner": (
            '{"modulo": "modulo_simulado.py", "tipo": "funcion", '
            '"casos": [{"id": "caso_1", "entrada": [10], "valor_esperado": 20, '
            '"origen": "docstring"}]}'
        ),
        "generator": (
            "import pytest\n\n"
            "def test_generado():\n"
            "    assert True\n"
        ),
        "reviewer": (
            '{"decision": "accept", "laundering_detectado": false, '
            '"cobertura": 100, "feedback": "Test aprobado en sandbox."}'
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
            rol.lower(),
            f"Respuesta simulada para prompt: {prompt[:30]}..."
        )

        return RespuestaLLM(
            contenido=contenido,
            tokens_entrada=0,
            tokens_salida=0,
            costo_usd=0.0,
            modelo=self.modelo,
        )