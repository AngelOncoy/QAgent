"""start_run no inicia si el entorno no está listo (EN-06)."""

from __future__ import annotations

import pytest

pytest.importorskip("webview")

from pyagent.app.desktop import DesktopAPI


def _entorno(listo: bool) -> dict:
    return {
        "listo": listo,
        "mensaje": "Entorno listo"
        if listo
        else "Falta la clave OPENAI_API_KEY en .env",
        "problemas": [] if listo else ["Falta la clave OPENAI_API_KEY en .env"],
        "comprobaciones": [],
    }


@pytest.fixture(autouse=True)
def _docker_disponible(monkeypatch):
    """La parte de Docker la cubre HU-13; aquí solo se prueba el bloqueo de EN-06."""
    monkeypatch.setattr("pyagent.sandbox.verificar_docker", lambda: None)


def test_start_run_bloqueado_si_falta_algo(monkeypatch):
    api = DesktopAPI()
    monkeypatch.setattr(api, "verificar_entorno", lambda: _entorno(False))
    r = api.start_run("C:/proyecto")
    assert r["status"] == "blocked"
    assert "OPENAI_API_KEY" in r["motivo"]


def test_start_run_inicia_con_entorno_listo(monkeypatch):
    api = DesktopAPI()
    monkeypatch.setattr(api, "verificar_entorno", lambda: _entorno(True))
    assert api.start_run("C:/proyecto", "deep")["status"] == "started"
