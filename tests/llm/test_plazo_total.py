"""Plazo total de una llamada a la IA y registro de tokens de hilos vencidos (A1, A3).

Sin red: la respuesta HTTP y el proveedor se simulan.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from qagent.llm import cliente as modulo
from qagent.llm.cliente import ClienteLLMReal, ErrorLLM, ProveedorSaturado, SinConexion
from qagent.llm.tracker import TokenTracker
from tests.llm.test_cliente_real import (
    CLAVE_PRUEBA,
    ENDPOINT_PRUEBA,
    respuesta_correcta,
)


class RespuestaGoteo:
    """Respuesta HTTP que manda un espacio cada `pausa_s` y nunca termina.

    Así se comportan algunos proveedores para mantener viva la conexión: el timeout
    del socket nunca se cumple porque siempre llega algo.
    """

    def __init__(self, pausa_s: float = 0.02) -> None:
        self.pausa_s = pausa_s

    def read1(self, _tamano: int) -> bytes:
        time.sleep(self.pausa_s)
        return b" "

    def __enter__(self) -> Any:
        return self

    def __exit__(self, *_: object) -> None:
        return None


def test_una_respuesta_que_gotea_se_corta_en_el_plazo_total(monkeypatch) -> None:
    monkeypatch.setattr(modulo, "urlopen", lambda *_a, **_k: RespuestaGoteo())

    inicio = time.monotonic()
    with pytest.raises(SinConexion, match="no respondió en 0.3 segundos"):
        modulo.TransporteHTTP().enviar(
            url=ENDPOINT_PRUEBA, cabeceras={}, datos={}, timeout_s=0.3
        )

    assert time.monotonic() - inicio < 1.5


def test_lectura_por_bloques_devuelve_la_respuesta_completa() -> None:
    class Bloques:
        def __init__(self) -> None:
            self.partes = [b'{"a": ', b"1}", b""]

        def read1(self, _tamano: int) -> bytes:
            return self.partes.pop(0)

    assert modulo._leer_con_plazo(Bloques(), time.monotonic() + 5) == b'{"a": 1}'


class TransporteSaturado:
    """Siempre responde HTTP 503 pidiendo esperar `espera_s`; anota cada timeout."""

    def __init__(self, espera_s: float | None = None, responde_en: int = 99) -> None:
        self.espera_s = espera_s
        self.responde_en = responde_en
        self.timeouts: list[float] = []

    def enviar(self, *, timeout_s: float, **_: Any) -> dict[str, Any]:
        self.timeouts.append(timeout_s)
        if len(self.timeouts) >= self.responde_en:
            return respuesta_correcta()
        raise ProveedorSaturado("HTTP 503", espera_s=self.espera_s)


def cliente(transporte: Any, esperas: list[float], **opciones: Any) -> ClienteLLMReal:
    return ClienteLLMReal(
        modelo="modelo-configurado",
        clave=CLAVE_PRUEBA,
        endpoint=ENDPOINT_PRUEBA,
        transporte=transporte,
        esperar=esperas.append,
        **opciones,
    )


def test_no_reintenta_si_la_espera_no_cabe_en_el_plazo_total() -> None:
    esperas: list[float] = []
    transporte = TransporteSaturado(espera_s=20.0)

    with pytest.raises(ErrorLLM):
        cliente(transporte, esperas, timeout_s=90.0, plazo_total_s=10.0).generar("x")

    assert len(transporte.timeouts) == 1
    assert esperas == []


def test_cada_solicitud_recibe_solo_lo_que_queda_del_plazo() -> None:
    esperas: list[float] = []
    transporte = TransporteSaturado(espera_s=1.0, responde_en=2)

    cliente(transporte, esperas, timeout_s=90.0, plazo_total_s=30.0).generar("x")

    assert esperas == [1.0]
    assert all(t <= 30.0 for t in transporte.timeouts)


def test_por_defecto_el_plazo_total_es_el_timeout() -> None:
    assert cliente(TransporteSaturado(), [], timeout_s=90.0).plazo_total_s == 90.0


def test_plazo_total_invalido() -> None:
    with pytest.raises(ValueError):
        cliente(TransporteSaturado(), [], plazo_total_s=0)


# --- A3: un hilo que termina tarde registra en su propia función ------------------


def test_el_hilo_conserva_el_contexto_aunque_el_general_cambie() -> None:
    tracker = TokenTracker()
    tracker.fijar_contexto("primera", 1)
    contexto = tracker.contexto_actual()
    listo = threading.Event()

    def agente_lento() -> None:
        tracker.fijar_contexto_hilo(*contexto)
        listo.wait(2)
        tracker.registrar("generator", "m", 10, 5)

    hilo = threading.Thread(target=agente_lento)
    hilo.start()
    tracker.fijar_contexto("segunda", 1)  # el orquestador ya pasó a otra función
    listo.set()
    hilo.join()

    [registro] = tracker.llamadas
    assert (registro.funcion, registro.intento) == ("primera", 1)
    assert tracker.contexto_actual() == ("segunda", 1)
