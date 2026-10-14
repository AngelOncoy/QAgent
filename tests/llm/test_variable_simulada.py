"""`QAGENT_FAKE_LLM` activa la IA simulada; `PYAGENT_FAKE_LLM` se sigue aceptando."""

from __future__ import annotations

from pathlib import Path

import pytest

from pyagent.config import carga
from pyagent.llm.cliente import es_modo_simulado


@pytest.fixture(autouse=True)
def _sin_banderas(monkeypatch: pytest.MonkeyPatch) -> None:
    # setenv antes de delenv: así monkeypatch restaura el entorno aunque no existieran.
    for nombre in ("QAGENT_FAKE_LLM", "PYAGENT_FAKE_LLM"):
        monkeypatch.setenv(nombre, "")
        monkeypatch.delenv(nombre)


def test_la_variable_nueva_activa_la_simulacion(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QAGENT_FAKE_LLM", "1")
    assert es_modo_simulado()


def test_la_variable_anterior_sigue_funcionando(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PYAGENT_FAKE_LLM", "1")
    assert es_modo_simulado()


def test_si_estan_las_dos_manda_la_nueva(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("QAGENT_FAKE_LLM", "0")
    monkeypatch.setenv("PYAGENT_FAKE_LLM", "1")
    assert not es_modo_simulado()


def test_sin_ninguna_no_hay_simulacion():
    assert not es_modo_simulado()


def test_env_con_la_variable_anterior_activa_la_simulacion(tmp_path: Path):
    env = tmp_path / ".env"
    env.write_text("PYAGENT_FAKE_LLM=1\n", encoding="utf-8")
    assert carga.simulado_desde_env(env)
    assert carga.modo_simulado(env)


def test_aplicar_desde_env_escribe_la_variable_nueva(tmp_path: Path):
    import os

    env = tmp_path / ".env"
    env.write_text("PYAGENT_FAKE_LLM=1\n", encoding="utf-8")
    assert carga.aplicar_simulacion_desde_env(env)
    assert os.environ["QAGENT_FAKE_LLM"] == "1"
    assert es_modo_simulado()
