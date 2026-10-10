"""Crea el cliente LLM de cada agente a partir de `config.toml` y `.env` (HU-11).

Todos los proveedores de ADR-001 exponen una API de chat compatible con OpenAI; solo
cambian la URL y, en Xiaomi MiMo, la cabecera de la clave. Un agente puede fijar su
propia URL con `endpoint = "..."` en `[agentes.<agente>]`.
"""

from __future__ import annotations

from typing import Protocol

from pyagent.llm.cliente import ClienteLLMReal, TransporteLLM
from pyagent.llm.fake import FakeLLMClient
from pyagent.llm.modelos import ClienteLLM
from pyagent.llm.precios import PrecioAgente

#: URL de chat completions por proveedor (se puede reemplazar con `endpoint`).
ENDPOINT_POR_PROVEEDOR = {
    "openai": "https://api.openai.com/v1/chat/completions",
    "xiaomi": "https://api.xiaomimimo.com/v1/chat/completions",
    "anthropic": "https://api.anthropic.com/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
}

#: Proveedores que leen la clave de una cabecera propia además de `Authorization`.
CABECERA_CLAVE_POR_PROVEEDOR = {
    "xiaomi": "api-key",
    "anthropic": "x-api-key",
}


class FuenteClaves(Protocol):
    """Lo único que la fábrica necesita de `pyagent.config.Claves`."""

    def obtener(self, nombre: str) -> str | None:
        """Valor de la variable de `.env`, o None si no está."""
        ...


class ConfiguracionLLMIncompleta(ValueError):
    """Falta la clave o la URL para crear el cliente real de un agente."""


def crear_cliente(
    precio: PrecioAgente,
    claves: FuenteClaves | None,
    *,
    simulado: bool,
    transporte: TransporteLLM | None = None,
    timeout_s: float = 90.0,  # menor que el timeout por paso del orquestador (120 s)
) -> ClienteLLM:
    """Devuelve el cliente LLM del agente descrito por `precio`.

    Args:
        precio: entrada de `[agentes.<agente>]` (proveedor, modelo, endpoint, esfuerzo).
        claves: claves de `.env` (`cargar_configuracion().claves`); no se usan si
            `simulado` es True.
        simulado: True con `PYAGENT_FAKE_LLM=1`: devuelve la IA simulada (0 tokens).
        transporte: transporte HTTP reemplazable en las pruebas.
        timeout_s: tiempo máximo por llamada.

    Raises:
        ConfiguracionLLMIncompleta: si falta la clave en `.env` o no hay URL para
            el proveedor.
    """
    if simulado:
        return FakeLLMClient(modelo=precio.modelo)

    # Import diferido: pyagent.config importa pyagent.llm al cargarse.
    from pyagent.config.carga import CLAVE_POR_PROVEEDOR

    variable = CLAVE_POR_PROVEEDOR.get(precio.proveedor)
    clave = claves.obtener(variable) if (claves is not None and variable) else None
    if not clave:
        raise ConfiguracionLLMIncompleta(
            f"Falta la clave {variable or '(proveedor desconocido)'} en .env "
            f"para el {precio.agente}."
        )
    endpoint = precio.endpoint or ENDPOINT_POR_PROVEEDOR.get(precio.proveedor)
    if not endpoint:
        raise ConfiguracionLLMIncompleta(
            f"No hay URL para el proveedor '{precio.proveedor}': agrega "
            f'endpoint = "..." en [agentes.{precio.agente}] de config.toml.'
        )
    return ClienteLLMReal(
        modelo=precio.modelo,
        clave=clave,
        endpoint=endpoint,
        transporte=transporte,
        timeout_s=timeout_s,
        esfuerzo=precio.esfuerzo,
        cabecera_clave=CABECERA_CLAVE_POR_PROVEEDOR.get(precio.proveedor),
    )
