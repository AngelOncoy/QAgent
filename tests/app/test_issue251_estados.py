"""Estados que la app abierta pone al día sin reiniciar (#251), sin Docker ni red.

Casos 6 (IA simulada del `.env`), 10 (claves que oculta la bitácora) y 11 (limpieza del
sandbox cuando Docker pasa a responder). El seguimiento solo actúa con la app abierta
(`SEGUIMIENTO.activo`, que enciende `main`), así que aquí se enciende a mano.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from qagent.app import desktop
from qagent.app.desktop import SEGUIMIENTO, DesktopAPI
from qagent.config import carga
from qagent.sandbox import estado as modulo_estado

LISTO = {"estado": "ok", "mensaje": ""}
APAGADO = {"estado": "no_iniciado", "mensaje": "Docker no está abierto"}


@pytest.fixture
def sin_bandera(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin QAGENT_FAKE_LLM en el proceso; al terminar vuelve el valor original."""
    for nombre in ("QAGENT_FAKE_LLM", "PYAGENT_FAKE_LLM"):
        monkeypatch.setenv(nombre, "x")  # registra el valor original para restaurarlo
        monkeypatch.delenv(nombre)
    monkeypatch.setattr(carga, "_SIMULACION_COPIADA", False)


def _env(tmp_path: Path, texto: str) -> Path:
    ruta = tmp_path / ".env"
    ruta.write_text(texto, encoding="utf-8")
    return ruta


# ---------- Caso 6: QAGENT_FAKE_LLM del .env ----------


def test_quitar_la_ia_simulada_del_env_se_refleja_sin_reiniciar(sin_bandera, tmp_path):
    import os

    ruta = _env(tmp_path, "QAGENT_FAKE_LLM=1\n")
    assert carga.aplicar_simulacion_desde_env(ruta) is True
    assert os.environ["QAGENT_FAKE_LLM"] == "1"

    _env(tmp_path, "QAGENT_FAKE_LLM=0\n")
    assert carga.refrescar_simulacion_desde_env(ruta) is False
    assert "QAGENT_FAKE_LLM" not in os.environ

    _env(tmp_path, "QAGENT_FAKE_LLM=1\n")
    assert carga.refrescar_simulacion_desde_env(ruta) is True
    assert os.environ["QAGENT_FAKE_LLM"] == "1"


def test_lo_definido_en_el_sistema_sigue_mandando(sin_bandera, monkeypatch, tmp_path):
    import os

    monkeypatch.setenv("QAGENT_FAKE_LLM", "0")
    ruta = _env(tmp_path, "QAGENT_FAKE_LLM=1\n")
    assert carga.refrescar_simulacion_desde_env(ruta) is False
    assert os.environ["QAGENT_FAKE_LLM"] == "0"

    monkeypatch.setenv("QAGENT_FAKE_LLM", "1")
    _env(tmp_path, "QAGENT_FAKE_LLM=0\n")
    assert carga.refrescar_simulacion_desde_env(ruta) is True
    assert os.environ["QAGENT_FAKE_LLM"] == "1"


# ---------- Caso 10: claves que oculta la bitácora ----------


def test_reinstalar_el_filtro_actualiza_las_claves_sin_duplicarlo(monkeypatch):
    """Actualiza la redacción sin sustituir el logger que necesita pytest."""
    handler = logging.Handler()
    registro = SimpleNamespace(
        handlers=[handler]
    )  # el logger raíz, con un solo handler
    original = logging.getLogger
    # Se sustituye la referencia de carga, no el módulo logging compartido con pytest.
    monkeypatch.setattr(carga, "logging", SimpleNamespace(getLogger=lambda: registro))
    monkeypatch.setattr(carga, "_FILTRO_RAIZ", None)

    primero = carga.instalar_filtro_logs(carga.Claves({"A": "clave-vieja-123456"}))
    segundo = carga.instalar_filtro_logs(carga.Claves({"A": "clave-nueva-654321"}))

    assert segundo is primero
    assert handler.filters.count(primero) == 1
    mensaje = logging.LogRecord(
        "x", logging.INFO, "", 0, "usa clave-nueva-654321", (), None
    )
    primero.filter(mensaje)
    assert "clave-nueva-654321" not in mensaje.msg
    assert logging.getLogger is original
    assert isinstance(logging.getLogger(), logging.Logger)


def test_un_env_editado_a_mano_vuelve_a_leerse_una_sola_vez(monkeypatch, tmp_path):
    ruta = _env(tmp_path, "OPENAI_API_KEY_PLANNER=sk-escrita-a-mano-123456\n")
    monkeypatch.setattr(carga, "RUTA_ENV", ruta)
    monkeypatch.setattr(SEGUIMIENTO, "firma_env", None)
    leidas: list = []
    monkeypatch.setattr(desktop.bitacora, "configurar_registro", leidas.append)

    assert desktop._refrescar_claves_si_cambio() is True
    assert desktop._refrescar_claves_si_cambio() is False  # sin cambios, no se relee
    assert len(leidas) == 1
    assert "sk-escrita-a-mano-123456" not in leidas[0].redactar(
        "clave sk-escrita-a-mano-123456"
    )

    ruta.write_text("OPENAI_API_KEY_PLANNER=sk-otra-clave-distinta-789\n", "utf-8")
    assert desktop._refrescar_claves_si_cambio() is True
    assert len(leidas) == 2


# ---------- Caso 11: limpieza del sandbox ----------


class HilosFalsos:
    """`threading.Thread` que anota a quién se lanzaría, sin lanzarlo."""

    def __init__(self) -> None:
        self.lanzados: list = []

    def __call__(self, target, **_opciones):
        return SimpleNamespace(start=lambda: self.lanzados.append(target))


@pytest.fixture
def seguimiento(monkeypatch: pytest.MonkeyPatch) -> HilosFalsos:
    """App abierta con la limpieza pendiente; sin tocar el entorno ni el `.env`."""
    monkeypatch.setattr(SEGUIMIENTO, "activo", True)
    monkeypatch.setattr(SEGUIMIENTO, "limpieza", "pendiente")
    monkeypatch.setattr(desktop, "_refrescar_claves_si_cambio", lambda: False)
    refrescos: list = []
    monkeypatch.setattr(
        "qagent.config.refrescar_simulacion_desde_env",
        lambda *_a: refrescos.append(True) or False,
    )
    hilos = HilosFalsos()
    hilos.refrescos = refrescos
    monkeypatch.setattr(desktop.threading, "Thread", hilos)
    return hilos


def _estado(api: DesktopAPI, estado: dict) -> dict:
    with patch.object(modulo_estado, "estado_docker", return_value=estado):
        return api.estado_sandbox()


def test_la_limpieza_pendiente_se_lanza_cuando_docker_responde(seguimiento):
    api = DesktopAPI()
    _estado(api, APAGADO)
    assert seguimiento.lanzados == []
    _estado(api, LISTO)
    assert seguimiento.lanzados == [desktop._limpiar_sandbox]
    assert SEGUIMIENTO.limpieza == "en_curso"
    _estado(api, LISTO)  # ya en curso: no se lanza otra
    assert len(seguimiento.lanzados) == 1


def test_durante_una_corrida_no_se_limpia_ni_cambia_la_ia(seguimiento):
    api = DesktopAPI()
    api._corrida = SimpleNamespace(is_alive=lambda: True)
    _estado(api, LISTO)
    assert seguimiento.lanzados == []
    assert seguimiento.refrescos == []
    assert SEGUIMIENTO.limpieza == "pendiente"


def test_sin_la_app_abierta_no_se_toca_nada(seguimiento, monkeypatch):
    monkeypatch.setattr(SEGUIMIENTO, "activo", False)
    _estado(DesktopAPI(), LISTO)
    assert seguimiento.lanzados == [] and seguimiento.refrescos == []


@pytest.mark.parametrize(
    ("resultado", "esperado"),
    [({}, "pendiente"), ({"contenedores": 0, "imagenes": []}, "hecha")],
)
def test_la_limpieza_queda_pendiente_si_docker_no_respondio(
    monkeypatch, resultado, esperado
):
    monkeypatch.setattr(SEGUIMIENTO, "limpieza", "en_curso")
    monkeypatch.setattr(
        "qagent.sandbox.limpieza.limpiar_al_iniciar", lambda *_a, **_k: resultado
    )
    desktop._limpiar_sandbox()
    assert SEGUIMIENTO.limpieza == esperado
