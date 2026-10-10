"""Pruebas del cliente LLM real sin realizar conexiones a internet."""

from __future__ import annotations

from typing import Any

import pytest

from pyagent.llm.cliente import ClienteLLMReal, ErrorLLM

CLAVE_PRUEBA = "clave-super-secreta-de-prueba"
ENDPOINT_PRUEBA = "https://proveedor.example/v1/chat/completions"


class TransporteGrabado:
    """Transporte simulado que registra la solicitud y devuelve una respuesta fija."""

    def __init__(
        self,
        respuesta: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.respuesta = respuesta
        self.error = error
        self.solicitudes: list[dict[str, Any]] = []

    def enviar(
        self,
        *,
        url: str,
        cabeceras: dict[str, str],
        datos: dict[str, Any],
        timeout_s: float,
    ) -> dict[str, Any]:
        """Registra la solicitud sin enviarla a internet."""
        self.solicitudes.append(
            {
                "url": url,
                "cabeceras": cabeceras,
                "datos": datos,
                "timeout_s": timeout_s,
            }
        )

        if self.error is not None:
            raise self.error

        if self.respuesta is None:
            return {}

        return self.respuesta


def respuesta_correcta() -> dict[str, Any]:
    """Respuesta compatible con una API de chat tipo OpenAI."""
    return {
        "id": "respuesta-1",
        "model": "modelo-real-respuesta",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": '{"resultado": "correcto"}',
                }
            }
        ],
        "usage": {
            "prompt_tokens": 120,
            "completion_tokens": 35,
        },
    }


def crear_cliente(
    transporte: TransporteGrabado,
    timeout_s: float = 30.0,
) -> ClienteLLMReal:
    """Crea un cliente real conectado únicamente al transporte simulado."""
    return ClienteLLMReal(
        modelo="modelo-configurado",
        clave=CLAVE_PRUEBA,
        endpoint=ENDPOINT_PRUEBA,
        transporte=transporte,
        timeout_s=timeout_s,
    )


def test_cliente_real_devuelve_contenido_modelo_y_tokens() -> None:
    transporte = TransporteGrabado(respuesta=respuesta_correcta())
    cliente = crear_cliente(transporte)

    respuesta = cliente.generar(
        prompt="Genera el contrato de prueba.",
        rol="planner",
    )

    assert respuesta.contenido == '{"resultado": "correcto"}'
    assert respuesta.modelo == "modelo-real-respuesta"
    assert respuesta.tokens_entrada == 120
    assert respuesta.tokens_salida == 35
    assert respuesta.costo_usd == 0.0
    assert respuesta.datos_json == respuesta_correcta()


def test_cliente_real_envia_modelo_prompt_rol_y_timeout() -> None:
    transporte = TransporteGrabado(respuesta=respuesta_correcta())
    cliente = crear_cliente(transporte, timeout_s=15.0)

    cliente.generar(
        prompt="Escribe un test pytest.",
        rol="generator",
    )

    assert len(transporte.solicitudes) == 1
    solicitud = transporte.solicitudes[0]

    assert solicitud["url"] == ENDPOINT_PRUEBA
    assert solicitud["timeout_s"] == 15.0
    assert solicitud["cabeceras"]["Authorization"] == f"Bearer {CLAVE_PRUEBA}"
    assert solicitud["cabeceras"]["Content-Type"] == "application/json"

    datos = solicitud["datos"]
    assert datos["model"] == "modelo-configurado"
    assert datos["messages"][0]["role"] == "system"
    assert "generator" in datos["messages"][0]["content"].lower()
    assert datos["messages"][1] == {
        "role": "user",
        "content": "Escribe un test pytest.",
    }


def test_cliente_real_usa_modelo_configurado_si_la_respuesta_no_lo_incluye() -> None:
    datos = respuesta_correcta()
    datos.pop("model")
    transporte = TransporteGrabado(respuesta=datos)
    cliente = crear_cliente(transporte)

    respuesta = cliente.generar("Prueba", rol="reviewer")

    assert respuesta.modelo == "modelo-configurado"


def test_cliente_real_rechaza_respuesta_sin_contenido() -> None:
    transporte = TransporteGrabado(
        respuesta={
            "model": "modelo-real-respuesta",
            "choices": [],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 0,
            },
        }
    )
    cliente = crear_cliente(transporte)

    with pytest.raises(ErrorLLM, match="contenido"):
        cliente.generar("Prueba", rol="planner")


def test_cliente_real_oculta_la_clave_en_errores() -> None:
    transporte = TransporteGrabado(
        error=RuntimeError(f"Falló la solicitud con {CLAVE_PRUEBA}")
    )
    cliente = crear_cliente(transporte)

    with pytest.raises(ErrorLLM) as capturado:
        cliente.generar("Prueba", rol="generator")

    mensaje = str(capturado.value)
    assert CLAVE_PRUEBA not in mensaje
    assert "***" in mensaje


@pytest.mark.parametrize("rol", ["planner", "generator", "reviewer"])
def test_cliente_real_acepta_los_tres_roles(rol: str) -> None:
    transporte = TransporteGrabado(respuesta=respuesta_correcta())
    cliente = crear_cliente(transporte)

    respuesta = cliente.generar("Tarea", rol=rol)

    assert respuesta.contenido
    mensaje_sistema = transporte.solicitudes[0]["datos"]["messages"][0]["content"]
    assert rol in mensaje_sistema.lower()
