"""Pruebas de contabilización, estimación y diferenciación de consumo de tokens."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from qagent.llm import FakeLLMClient, TokenTracker, estimar_tokens
from qagent.llm.cliente import ClienteLLMReal


class TransporteFijo:
    """Transporte simulado que retorna una respuesta predefinida sin red."""

    def __init__(self, respuesta: dict[str, Any]) -> None:
        self.respuesta = respuesta

    def enviar(
        self,
        *,
        url: str,
        cabeceras: dict[str, str],
        datos: dict[str, Any],
        timeout_s: float,
    ) -> dict[str, Any]:
        return self.respuesta


def test_estimar_tokens_texto_vacio_y_contenido() -> None:
    """Verifica que la estimación heurística funcione para textos vacíos y no vacíos."""
    assert estimar_tokens("") == 0
    assert estimar_tokens("   \n\t") == 0

    corta = "def suma(a, b): return a + b"
    tokens_corta = estimar_tokens(corta)
    assert tokens_corta > 0
    assert tokens_corta == len(corta.strip()) // 4 or 1

    larga = "x" * 1000
    assert estimar_tokens(larga) == 250


def test_cliente_real_con_tokens_reportados_marca_no_estimado() -> None:
    """Cuando el proveedor reporta usage, los tokens son reales y es_estimado es False."""
    datos_respuesta = {
        "id": "chatcmpl-123",
        "model": "gpt-4o",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "def test_ok(): assert True",
                }
            }
        ],
        "usage": {
            "prompt_tokens": 150,
            "completion_tokens": 40,
        },
    }
    cliente = ClienteLLMReal(
        modelo="gpt-4o",
        clave="sk-test",
        endpoint="https://api.openai.com/v1/chat/completions",
        transporte=TransporteFijo(datos_respuesta),
    )

    respuesta = cliente.generar("Escribe un test", rol="generator")
    assert respuesta.tokens_entrada == 150
    assert respuesta.tokens_salida == 40
    assert respuesta.es_estimado is False


def test_cliente_real_sin_usage_estima_tokens_y_marca_es_estimado() -> None:
    """Cuando el proveedor no reporta usage, se estiman y es_estimado es True."""
    prompt = "Genera contratos de prueba para el módulo bancario."
    contenido = "def test_banco(): pass"
    datos_respuesta = {
        "id": "chatcmpl-456",
        "model": "modelo-sin-usage",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": contenido,
                }
            }
        ],
        # usage omitido intencionalmente
    }
    cliente = ClienteLLMReal(
        modelo="modelo-sin-usage",
        clave="sk-test",
        endpoint="https://api.openai.com/v1/chat/completions",
        transporte=TransporteFijo(datos_respuesta),
    )

    respuesta = cliente.generar(prompt, rol="planner")
    assert respuesta.tokens_entrada == estimar_tokens(prompt)
    assert respuesta.tokens_salida == estimar_tokens(contenido)
    assert respuesta.es_estimado is True


def test_cliente_real_con_usage_nulo_o_incompleto_estima() -> None:
    """Cuando usage es None o le faltan claves, se estiman los tokens."""
    datos_respuesta = {
        "id": "chatcmpl-789",
        "model": "modelo-incompleto",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "resultado",
                }
            }
        ],
        "usage": None,
    }
    cliente = ClienteLLMReal(
        modelo="modelo-incompleto",
        clave="sk-test",
        endpoint="https://api.openai.com/v1/chat/completions",
        transporte=TransporteFijo(datos_respuesta),
    )

    respuesta = cliente.generar("prompt de prueba", rol="reviewer")
    assert respuesta.es_estimado is True
    assert respuesta.tokens_entrada == estimar_tokens("prompt de prueba")
    assert respuesta.tokens_salida == estimar_tokens("resultado")


def test_tracker_diferencia_reales_y_estimados(tmp_path: Path) -> None:
    """TokenTracker mantiene totales acumulados separados para tokens reales y estimados."""
    tracker = TokenTracker()

    # Llamada 1: real (ej. proveedor reportó 100 de entrada y 50 de salida)
    reg1 = tracker.registrar(
        agente="planner",
        modelo="gpt-4o",
        tokens_entrada=100,
        tokens_salida=50,
        es_estimado=False,
    )
    assert reg1.es_estimado is False

    # Llamada 2: estimada (ej. proveedor local sin métricas de uso: 80 entrada, 20 salida)
    reg2 = tracker.registrar(
        agente="generator",
        modelo="ollama-local",
        tokens_entrada=80,
        tokens_salida=20,
        es_estimado=True,
    )
    assert reg2.es_estimado is True

    # Comprobación de totales acumulados
    assert tracker.total_tokens == 250
    assert tracker.total_tokens_reales == 150
    assert tracker.total_tokens_estimados == 100

    # Totales por agente
    totales = tracker.totales_por_agente()
    assert totales["planner"]["tokens_reales"] == 150
    assert totales["planner"]["tokens_estimados"] == 0
    assert (
        totales["planner"]["prompt_tokens"] + totales["planner"]["completion_tokens"]
        == 150
    )

    assert totales["generator"]["tokens_reales"] == 0
    assert totales["generator"]["tokens_estimados"] == 100
    assert (
        totales["generator"]["prompt_tokens"]
        + totales["generator"]["completion_tokens"]
        == 100
    )

    # Log estructurado
    log = tracker.guardar_log(tmp_path / "log.json")
    assert log["total_tokens"] == 250
    assert log["tokens_reales"] == 150
    assert log["tokens_estimados"] == 100
    assert log["llamadas"][0]["es_estimado"] is False
    assert log["llamadas"][1]["es_estimado"] is True


def test_ia_simulada_mantiene_cero_tokens_no_estimados() -> None:
    """La IA simulada (QAGENT_FAKE_LLM=1) siempre reporta 0 tokens reales."""
    cliente = FakeLLMClient()
    respuesta = cliente.generar("test", rol="planner")
    assert respuesta.tokens_entrada == 0
    assert respuesta.tokens_salida == 0
    assert respuesta.es_estimado is False

    tracker = TokenTracker()
    tracker.registrar(
        agente="planner",
        modelo=respuesta.modelo,
        tokens_entrada=respuesta.tokens_entrada,
        tokens_salida=respuesta.tokens_salida,
        es_estimado=respuesta.es_estimado,
        es_simulado=True,
    )
    assert tracker.total_tokens == 0
    assert tracker.total_tokens_reales == 0
    assert tracker.total_tokens_estimados == 0
