"""Indicador del sandbox de la barra lateral: avisa si la IA es simulada (Docker opcional)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from pyagent.app.desktop import DesktopAPI
from pyagent.sandbox import estado as modulo_estado

APAGADO = {"estado": "no_iniciado", "mensaje": "Docker no está abierto"}
LISTO = {"estado": "ok", "mensaje": ""}


@pytest.mark.parametrize("estado", [APAGADO, LISTO])
def test_conserva_el_estado_real_de_docker(estado, monkeypatch):
    monkeypatch.setenv("PYAGENT_FAKE_LLM", "0")
    with patch.object(modulo_estado, "estado_docker", return_value=estado):
        r = DesktopAPI().estado_sandbox()
    assert r["estado"] == estado["estado"] and r["mensaje"] == estado["mensaje"]


def test_con_ia_real_no_se_marca_como_simulado(monkeypatch):
    monkeypatch.setenv("PYAGENT_FAKE_LLM", "0")
    with patch.object(modulo_estado, "estado_docker", return_value=APAGADO):
        assert DesktopAPI().estado_sandbox()["simulado"] is False


def test_con_ia_simulada_avisa_que_es_simulado(monkeypatch):
    monkeypatch.setenv("PYAGENT_FAKE_LLM", "1")
    with patch.object(modulo_estado, "estado_docker", return_value=APAGADO):
        r = DesktopAPI().estado_sandbox()
    assert r["simulado"] is True
    assert (
        r["estado"] == "no_iniciado"
    )  # el estado real no se oculta: lo decide la interfaz


def test_la_ia_simulada_tambien_puede_venir_del_env(monkeypatch):
    monkeypatch.delenv("PYAGENT_FAKE_LLM", raising=False)
    monkeypatch.setattr(
        "pyagent.config.carga.leer_env", lambda *a, **k: {"PYAGENT_FAKE_LLM": "1"}
    )
    with patch.object(modulo_estado, "estado_docker", return_value=APAGADO):
        assert DesktopAPI().estado_sandbox()["simulado"] is True
