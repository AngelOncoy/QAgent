"""Pruebas del cliente LLM real sin realizar conexiones a internet."""

from __future__ import annotations

from typing import Any

import pytest

from qagent.llm.cliente import ClienteLLMReal, ErrorLLM, LimiteProveedor

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


# --- Reintento ante el límite de uso de las capas gratuitas (HTTP 429/503) -------


class TransporteConLimite:
    """Responde 429 las primeras `veces` y luego una respuesta correcta."""

    def __init__(self, veces: int, espera_s: float | None = None) -> None:
        self.veces = veces
        self.espera_s = espera_s
        self.llamadas = 0

    def enviar(self, **_: Any) -> dict[str, Any]:
        self.llamadas += 1
        if self.llamadas <= self.veces:
            raise LimiteProveedor("HTTP 429", espera_s=self.espera_s)
        return respuesta_correcta()


def cliente_con_limite(
    transporte: TransporteConLimite, esperas: list[float], reintentos: int = 3
) -> ClienteLLMReal:
    return ClienteLLMReal(
        modelo="modelo-configurado",
        clave=CLAVE_PRUEBA,
        endpoint=ENDPOINT_PRUEBA,
        transporte=transporte,
        reintentos_limite=reintentos,
        espera_maxima_s=20.0,
        esperar=esperas.append,
    )


def test_ante_429_espera_y_reintenta_hasta_responder() -> None:
    esperas: list[float] = []
    transporte = TransporteConLimite(veces=2)

    respuesta = cliente_con_limite(transporte, esperas).generar("hola")

    assert respuesta.contenido == '{"resultado": "correcto"}'
    assert transporte.llamadas == 3
    assert esperas == [2.0, 4.0]  # espera creciente si el proveedor no dice cuánto


def test_respeta_retry_after_con_un_tope() -> None:
    esperas: list[float] = []

    cliente_con_limite(TransporteConLimite(veces=1, espera_s=7), esperas).generar("x")
    cliente_con_limite(TransporteConLimite(veces=1, espera_s=300), esperas).generar("x")

    assert esperas == [7.0, 20.0]


def test_si_el_limite_sigue_tras_los_reintentos_falla_sin_mostrar_la_clave() -> None:
    esperas: list[float] = []
    transporte = TransporteConLimite(veces=10)

    with pytest.raises(ErrorLLM) as error:
        cliente_con_limite(transporte, esperas, reintentos=2).generar("hola")

    assert transporte.llamadas == 3
    assert len(esperas) == 2
    assert CLAVE_PRUEBA not in str(error.value)


def test_otros_errores_no_se_reintentan() -> None:
    esperas: list[float] = []
    transporte = TransporteGrabado(error=ErrorLLM("HTTP 401"))
    cliente = ClienteLLMReal(
        modelo="m",
        clave=CLAVE_PRUEBA,
        endpoint=ENDPOINT_PRUEBA,
        transporte=transporte,
        esperar=esperas.append,
    )

    with pytest.raises(ErrorLLM):
        cliente.generar("hola")

    assert len(transporte.solicitudes) == 1
    assert esperas == []


def test_transporte_http_convierte_429_en_limite_con_retry_after(monkeypatch) -> None:
    import io
    from email.message import Message
    from urllib.error import HTTPError

    from qagent.llm import cliente as modulo

    cabeceras = Message()
    cabeceras["Retry-After"] = "12"

    def falla(*_: Any, **__: Any) -> None:
        raise HTTPError(
            ENDPOINT_PRUEBA,
            429,
            "Too Many Requests",
            cabeceras,
            io.BytesIO(b'{"error": "rate limit reached"}'),
        )

    monkeypatch.setattr(modulo, "urlopen", falla)

    with pytest.raises(LimiteProveedor) as error:
        modulo.TransporteHTTP().enviar(
            url=ENDPOINT_PRUEBA, cabeceras={}, datos={}, timeout_s=1
        )

    assert error.value.espera_s == 12.0
    assert "rate limit reached" in str(error.value)


def test_envia_un_user_agent_propio_para_no_ser_bloqueado() -> None:
    transporte = TransporteGrabado(respuesta=respuesta_correcta())

    crear_cliente(transporte).generar("hola")

    [solicitud] = transporte.solicitudes
    assert solicitud["cabeceras"]["User-Agent"] == "QAgent/1.0"
