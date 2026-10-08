"""HU-13: la corrida no inicia si Docker no está disponible."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pyagent.app.desktop import DesktopAPI
from pyagent.sandbox import estado as modulo_estado

MENSAJE = "Docker no está abierto: inícialo y vuelve a intentar"


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> DesktopAPI:
    """Puente con una ventana simulada para capturar los eventos hacia la interfaz.

    Se fija la IA real (PYAGENT_FAKE_LLM=0): con la IA simulada Docker es opcional.
    """
    monkeypatch.setenv("PYAGENT_FAKE_LLM", "0")
    puente = DesktopAPI()
    puente.set_window(MagicMock())
    # EN-06 también verifica config.toml, .env y Git: aquí se da por listo para
    # probar solo la parte de Docker (HU-13).
    puente.verificar_entorno = lambda: {
        "listo": True,
        "mensaje": "Entorno listo",
        "problemas": [],
        "comprobaciones": [],
    }  # type: ignore[method-assign]
    return puente


@pytest.mark.parametrize("estado", ["no_iniciado", "no_instalado"])
def test_sin_docker_no_inicia_la_corrida_y_devuelve_el_mensaje_exacto(api, estado):
    with patch.object(
        modulo_estado,
        "estado_docker",
        return_value={"estado": estado, "mensaje": "otro texto"},
    ):
        resultado = api.start_run("C:/Mis proyectos/demo", "deep")

    assert resultado == {"status": "docker_no_disponible", "mensaje": MENSAJE}
    api._window.evaluate_js.assert_not_called()


def test_con_docker_la_corrida_inicia(api):
    with patch.object(
        modulo_estado, "estado_docker", return_value={"estado": "ok", "mensaje": ""}
    ):
        resultado = api.start_run("C:/Mis proyectos/demo", "deep")

    assert resultado["status"] == "started"
    api._window.evaluate_js.assert_called_once()


# ---------- con la IA simulada Docker es opcional ----------


def test_con_ia_simulada_la_corrida_inicia_aunque_docker_no_este(api, monkeypatch):
    monkeypatch.setenv("PYAGENT_FAKE_LLM", "1")
    with patch.object(
        modulo_estado,
        "estado_docker",
        return_value={"estado": "no_instalado", "mensaje": "sin docker"},
    ):
        resultado = api.start_run("C:/Mis proyectos/demo", "deep")

    assert resultado["status"] == "started"
    api._window.evaluate_js.assert_called_once()


def test_con_ia_simulada_ni_siquiera_se_consulta_docker(api, monkeypatch):
    monkeypatch.setenv("PYAGENT_FAKE_LLM", "1")
    with patch(
        "pyagent.sandbox.verificar_docker",
        side_effect=AssertionError("no debe llamarse"),
    ):
        assert api.start_run("C:/Mis proyectos/demo", "deep")["status"] == "started"


def test_con_ia_simulada_en_el_env_tampoco_se_exige_docker(api, monkeypatch):
    """La bandera puede venir del .env: sin variable en el sistema decide el archivo."""
    monkeypatch.delenv("PYAGENT_FAKE_LLM")
    monkeypatch.setattr(
        "pyagent.config.carga.leer_env", lambda *a, **k: {"PYAGENT_FAKE_LLM": "1"}
    )
    with patch(
        "pyagent.sandbox.verificar_docker",
        side_effect=AssertionError("no debe llamarse"),
    ):
        assert api.start_run("C:/Mis proyectos/demo", "deep")["status"] == "started"
