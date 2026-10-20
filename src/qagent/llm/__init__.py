"""Módulo de comunicación LLM y contabilidad de tokens."""

from qagent.llm.cliente import (
    ClienteLLMReal,
    ErrorLLM,
    TransporteHTTP,
    es_modo_simulado,
    obtener_cliente_llm,
)
from qagent.llm.fabrica import (
    ENDPOINT_POR_PROVEEDOR,
    ConfiguracionLLMIncompleta,
    crear_cliente,
)
from qagent.llm.fake import FakeLLMClient
from qagent.llm.modelos import ClienteLLM, RespuestaLLM
from qagent.llm.precios import ConfiguracionInvalida, PrecioAgente, cargar_precios
from qagent.llm.tracker import TokenTracker

__all__ = [
    "ENDPOINT_POR_PROVEEDOR",
    "ClienteLLM",
    "ClienteLLMReal",
    "ConfiguracionInvalida",
    "ConfiguracionLLMIncompleta",
    "ErrorLLM",
    "FakeLLMClient",
    "PrecioAgente",
    "RespuestaLLM",
    "TokenTracker",
    "TransporteHTTP",
    "cargar_precios",
    "crear_cliente",
    "es_modo_simulado",
    "obtener_cliente_llm",
]
