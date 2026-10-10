"""Creación del cliente LLM de cada agente desde config.toml y .env (HU-11)."""

from __future__ import annotations

from typing import Any

import pytest

from pyagent.config import Claves
from pyagent.llm import (
    ClienteLLMReal,
    ConfiguracionLLMIncompleta,
    FakeLLMClient,
    PrecioAgente,
    crear_cliente,
)


def precio(proveedor: str = "xiaomi", **extra: Any) -> PrecioAgente:
    return PrecioAgente(
        agente="planner",
        proveedor=proveedor,
        modelo="modelo-x",
        entrada_usd_m=1.0,
        salida_usd_m=2.0,
        **extra,
    )


class TransporteEspia:
    def __init__(self) -> None:
        self.envios: list[dict[str, Any]] = []

    def enviar(self, **kwargs: Any) -> dict[str, Any]:
        self.envios.append(kwargs)
        return {
            "choices": [{"message": {"content": "[]"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 1},
        }


def test_con_ia_simulada_no_pide_claves() -> None:
    cliente = crear_cliente(precio(), None, simulado=True)

    assert isinstance(cliente, FakeLLMClient)
    assert cliente.modelo == "modelo-x"


def test_xiaomi_usa_su_url_y_la_cabecera_api_key() -> None:
    transporte = TransporteEspia()
    claves = Claves({"XIAOMI_API_KEY": "sk-secreta-123"})

    cliente = crear_cliente(precio(), claves, simulado=False, transporte=transporte)
    cliente.generar("hola", rol="planner")

    assert isinstance(cliente, ClienteLLMReal)
    [envio] = transporte.envios
    assert envio["url"] == "https://api.xiaomimimo.com/v1/chat/completions"
    assert envio["cabeceras"]["api-key"] == "sk-secreta-123"
    assert "reasoning_effort" not in envio["datos"]


def test_endpoint_y_esfuerzo_de_config_toml() -> None:
    transporte = TransporteEspia()
    claves = Claves({"OPENAI_API_KEY": "sk-otra-clave-456"})
    configurado = precio(
        "openai", endpoint="https://proxy.local/v1/chat/completions", esfuerzo="high"
    )

    cliente = crear_cliente(configurado, claves, simulado=False, transporte=transporte)
    cliente.generar("hola", rol="reviewer")

    [envio] = transporte.envios
    assert envio["url"] == "https://proxy.local/v1/chat/completions"
    assert envio["datos"]["reasoning_effort"] == "high"
    assert "api-key" not in envio["cabeceras"]


def test_sin_clave_en_env_falla_con_mensaje_claro() -> None:
    with pytest.raises(ConfiguracionLLMIncompleta, match="XIAOMI_API_KEY"):
        crear_cliente(precio(), Claves({}), simulado=False)
