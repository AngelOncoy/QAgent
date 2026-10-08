"""Punto de acceso para obtener el cliente LLM según la configuración del entorno."""

from __future__ import annotations

import os

from pyagent.llm.fake import FakeLLMClient


def es_modo_simulado() -> bool:
    """Verifica si la simulación de IA está activa mediante PYAGENT_FAKE_LLM=1."""
    return os.getenv("PYAGENT_FAKE_LLM", "0").strip() == "1"


def obtener_cliente_llm(modelo: str = "default-model") -> FakeLLMClient:
    """Retorna el cliente LLM correspondiente.

    Si PYAGENT_FAKE_LLM=1 está configurado, retorna FakeLLMClient.
    """
    if es_modo_simulado():
        return FakeLLMClient(modelo=modelo)

    # Cuando se implemente el cliente real en EN-05 se integrará aquí
    raise NotImplementedError(
        "El cliente real de LLM no está activo o falta configurar credenciales. "
        "Activa el modo simulado con: export PYAGENT_FAKE_LLM=1 (en Windows: set PYAGENT_FAKE_LLM=1)"
    )
