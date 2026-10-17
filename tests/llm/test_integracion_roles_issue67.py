"""Distribución solicitada por la issue #67, validada sin conexiones externas."""

from __future__ import annotations

from typing import Any

from qagent.config import Claves
from qagent.llm import FakeLLMClient, PrecioAgente, crear_cliente


class TransporteGrabado:
    """Transporte local que permite inspeccionar una solicitud sin enviarla."""

    def __init__(self) -> None:
        self.solicitudes: list[dict[str, Any]] = []

    def enviar(self, **solicitud: Any) -> dict[str, Any]:
        self.solicitudes.append(solicitud)
        return {
            "choices": [{"message": {"content": "OK"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 1},
        }


CONFIGURACION_SOLICITADA = (
    (
        "planner",
        "gemini",
        "gemini-3.8-flash",
        "GEMINI_API_KEY_PLANNER",
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
    ),
    (
        "generator",
        "openrouter",
        "google/gemma-4-31b-it:free",
        "OPENROUTER_API_KEY_GENERATOR",
        "https://openrouter.ai/api/v1/chat/completions",
    ),
    (
        "reviewer",
        "groq",
        "openai/gpt-oss-20b",
        "GROQ_API_KEY_REVIEWER",
        "https://api.groq.com/openai/v1/chat/completions",
    ),
)


def precio(agente: str, proveedor: str, modelo: str) -> PrecioAgente:
    return PrecioAgente(agente, proveedor, modelo, 0.0, 0.0)


def test_cada_rol_usa_su_proveedor_modelo_endpoint_y_variable_propios() -> None:
    for agente, proveedor, modelo, variable, endpoint in CONFIGURACION_SOLICITADA:
        transporte = TransporteGrabado()
        cliente = crear_cliente(
            precio(agente, proveedor, modelo),
            Claves({variable: "clave-sintetica-segura"}),
            simulado=False,
            transporte=transporte,
        )

        cliente.generar("prueba mínima", rol=agente)

        [solicitud] = transporte.solicitudes
        assert solicitud["url"] == endpoint
        assert solicitud["datos"]["model"] == modelo
        assert agente in solicitud["datos"]["messages"][0]["content"]


def test_fake_llm_cubre_los_tres_roles_sin_claves_ni_transporte() -> None:
    for agente, proveedor, modelo, _variable, _endpoint in CONFIGURACION_SOLICITADA:
        cliente = crear_cliente(
            precio(agente, proveedor, modelo),
            None,
            simulado=True,
        )

        assert isinstance(cliente, FakeLLMClient)
        assert cliente.modelo == modelo
