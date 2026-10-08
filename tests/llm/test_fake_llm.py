"""Pruebas unitarias para la IA simulada y contabilidad de 0 tokens (EN-11)."""

import json
from pathlib import Path

import pytest

from pyagent.llm import (
    FakeLLMClient,
    TokenTracker,
    es_modo_simulado,
    obtener_cliente_llm,
)


def test_modo_simulado_activado(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica que PYAGENT_FAKE_LLM=1 activa el modo simulado y retorna FakeLLMClient."""
    monkeypatch.setenv("PYAGENT_FAKE_LLM", "1")
    assert es_modo_simulado() is True

    cliente = obtener_cliente_llm(modelo="test-model")
    assert isinstance(cliente, FakeLLMClient)
    assert cliente.modelo == "test-model"


def test_modo_simulado_desactivado(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica que sin PYAGENT_FAKE_LLM=1 no se active la simulación."""
    monkeypatch.setenv("PYAGENT_FAKE_LLM", "0")
    assert es_modo_simulado() is False

    with pytest.raises(NotImplementedError):
        obtener_cliente_llm()


def test_respuestas_grabadas_consumen_cero_tokens() -> None:
    """Verifica que las respuestas grabadas reporten estrictamente 0 tokens y costo 0."""
    cliente = FakeLLMClient(modelo="simulado-v1")

    for rol in ["planner", "generator", "reviewer"]:
        respuesta = cliente.generar(prompt="probar función", rol=rol)
        assert len(respuesta.contenido) > 0
        assert respuesta.tokens_entrada == 0
        assert respuesta.tokens_salida == 0
        assert respuesta.costo_usd == 0.0


def test_corrida_completa_registra_cero_tokens_en_log_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Evidencia de aceptación: una corrida completa registra 0 tokens y 0 costo en log.json."""
    monkeypatch.setenv("PYAGENT_FAKE_LLM", "1")
    cliente = obtener_cliente_llm(modelo="fake-pipeline")
    tracker = TokenTracker()

    # Simular ciclo de los 3 agentes (Planner -> Generator -> Reviewer)
    roles = ["planner", "generator", "reviewer"]
    for rol in roles:
        res = cliente.generar(prompt=f"tarea de {rol}", rol=rol)
        tracker.registrar(
            agente=rol,
            modelo=res.modelo,
            tokens_entrada=res.tokens_entrada,
            tokens_salida=res.tokens_salida,
            costo_usd=res.costo_usd,
            es_simulado=True,
        )

    # 1. Comprobación en memoria
    assert tracker.total_tokens == 0
    assert tracker.total_costo_usd == 0.0
    assert len(tracker.llamadas) == 3

    # 2. Comprobación en archivo log.json persistido
    ruta_log = tmp_path / "log.json"
    resumen = tracker.guardar_log(ruta_log)

    assert ruta_log.exists()
    assert resumen["total_tokens"] == 0
    assert resumen["total_costo_usd"] == 0.0
    assert resumen["es_simulado"] is True

    # Verificar lectura directa del archivo JSON
    with open(ruta_log, "r", encoding="utf-8") as f:
        datos_disco = json.load(f)

    assert datos_disco["total_tokens"] == 0
    assert datos_disco["total_costo_usd"] == 0.0
    assert datos_disco["total_llamadas"] == 3