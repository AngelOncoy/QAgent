"""#267: el sandbox se limpia también al terminar cada corrida, sin Docker ni red.

Al abrir la app ya se limpiaba (#251); aquí se comprueba el segundo momento: el fin de
cada corrida, aunque haya fallado, en un hilo aparte y solo con la app abierta de verdad.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from qagent.app import desktop
from qagent.app.desktop import SEGUIMIENTO, DesktopAPI


class HilosFalsos:
    """`threading.Thread` que anota a quién se lanzaría, sin lanzarlo."""

    def __init__(self) -> None:
        self.lanzados: list = []

    def __call__(self, target, **_opciones):
        return SimpleNamespace(start=lambda: self.lanzados.append(target))


@pytest.fixture
def app_abierta(monkeypatch: pytest.MonkeyPatch) -> HilosFalsos:
    monkeypatch.setattr(SEGUIMIENTO, "activo", True)
    monkeypatch.setattr(SEGUIMIENTO, "limpieza", "hecha")
    hilos = HilosFalsos()
    monkeypatch.setattr(desktop.threading, "Thread", hilos)
    return hilos


def test_al_terminar_una_corrida_se_lanza_la_limpieza_en_otro_hilo(app_abierta):
    assert desktop._limpiar_sandbox_tras_corrida() is True

    assert app_abierta.lanzados == [desktop._limpiar_sandbox]
    assert SEGUIMIENTO.limpieza == "en_curso"


def test_si_ya_hay_una_limpieza_en_curso_no_se_lanza_otra(app_abierta, monkeypatch):
    monkeypatch.setattr(SEGUIMIENTO, "limpieza", "en_curso")

    assert desktop._limpiar_sandbox_tras_corrida() is False
    assert app_abierta.lanzados == []


def test_la_limpieza_pendiente_por_docker_caido_tambien_se_reintenta_tras_la_corrida(
    app_abierta, monkeypatch
):
    monkeypatch.setattr(SEGUIMIENTO, "limpieza", "pendiente")

    assert desktop._limpiar_sandbox_tras_corrida() is True


def test_sin_la_app_abierta_no_se_limpia_nada(monkeypatch):
    """En las pruebas y fuera de `main` nunca se toca Docker."""
    monkeypatch.setattr(SEGUIMIENTO, "activo", False)
    hilos = HilosFalsos()
    monkeypatch.setattr(desktop.threading, "Thread", hilos)

    assert desktop._limpiar_sandbox_tras_corrida() is False
    assert hilos.lanzados == []


def _api_con_corrida(monkeypatch, cuerpo):
    api = DesktopAPI()
    monkeypatch.setattr(api, "_correr", cuerpo)
    return api


def test_la_corrida_que_termina_bien_limpia_al_final(monkeypatch):
    llamadas: list[str] = []
    monkeypatch.setattr(
        desktop, "_limpiar_sandbox_tras_corrida", lambda: llamadas.append("limpieza")
    )
    api = _api_con_corrida(monkeypatch, lambda *a: llamadas.append("corrida"))

    api._correr_y_liberar("ruta", "perfil", "run", True, None, None)

    assert llamadas == ["corrida", "limpieza"]


def test_la_corrida_que_falla_tambien_limpia_al_final(monkeypatch):
    """Una corrida cortada es justo la que deja contenedores y capas a medias."""
    llamadas: list[str] = []
    monkeypatch.setattr(
        desktop, "_limpiar_sandbox_tras_corrida", lambda: llamadas.append("limpieza")
    )

    def corrida_que_falla(*_a):
        raise RuntimeError("Docker se cayó")

    api = _api_con_corrida(monkeypatch, corrida_que_falla)

    with pytest.raises(RuntimeError):
        api._correr_y_liberar("ruta", "perfil", "run", True, None, None)

    assert llamadas == ["limpieza"]


def test_el_resultado_de_la_limpieza_queda_en_la_bitacora(monkeypatch, caplog):
    monkeypatch.setattr(SEGUIMIENTO, "limpieza", "en_curso")
    gb = 1024**3
    monkeypatch.setattr(
        "qagent.sandbox.limpieza.limpiar_al_iniciar",
        lambda *_a, **_k: {
            "contenedores": 1,
            "construcciones": 2,
            "capas": 3,
            "capas_bytes": 6 * gb,
            "imagenes": ["qagent-sandbox:req-aaaaaaaaaaaa"],
            "imagenes_tope": ["qagent-sandbox:req-aaaaaaaaaaaa"],
            "cache_bytes": 512 * 1024**2,
        },
    )
    with caplog.at_level(logging.INFO):
        desktop._limpiar_sandbox()

    texto = caplog.text
    assert "2 contenedores de construcciones interrumpidas" in texto
    assert "3 capas sin etiqueta (6,0 GB)" in texto
    assert "qagent-sandbox:req-aaaaaaaaaaaa" in texto
    assert "caché de compilación (512 MB)" in texto
    assert SEGUIMIENTO.limpieza == "hecha"
