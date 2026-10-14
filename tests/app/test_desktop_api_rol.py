"""Puente pywebview de «Agregar API» (HU-30): rutas temporales y proveedor simulado."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("webview")

from qagent.app.desktop import DesktopAPI
from qagent.config import carga as config_carga
from qagent.llm import proveedores
from tests.config.config_equipo import CONFIG_EQUIPO

# Valor de prueba armado en tiempo de ejecución: no es una clave real.
CLAVE = "clave-de-prueba-" + "Q" * 16


class TransporteOk:
    def __init__(self) -> None:
        self.envios: list[dict[str, Any]] = []

    def enviar(self, **kwargs: Any) -> dict[str, Any]:
        self.envios.append(kwargs)
        return {"choices": [{"message": {"content": "OK"}}]}


@pytest.fixture
def api(tmp_path: Path, monkeypatch) -> DesktopAPI:
    config = tmp_path / "config.toml"
    config.write_text(CONFIG_EQUIPO, encoding="utf-8")
    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")
    monkeypatch.setattr(config_carga, "RUTA_CONFIG", config)
    monkeypatch.setattr(config_carga, "RUTA_ENV", env)
    monkeypatch.setattr(config_carga, "RUTA_CONFIG_LOCAL", tmp_path / "no-existe.toml")
    # Ninguna llamada sale a la red: el transporte por defecto es el simulado.
    monkeypatch.setattr(proveedores, "TransporteHTTP", TransporteOk)
    return DesktopAPI()


def test_listar_proveedores_para_el_formulario(api):
    ids = [p["id"] for p in api.listar_proveedores()]
    assert ids[0] == "anthropic" and "openrouter" in ids and "groq" not in ids


def test_guardar_devuelve_conectado_y_los_roles_sin_la_key(api):
    r = api.guardar_api_rol("planner", "gemini", "gemini-2.5-flash", CLAVE)

    assert r["ok"] and r["mensaje"] == "Conectado ✓"
    assert CLAVE not in repr(r)
    planner = next(x for x in r["roles"] if x["agente"] == "planner")
    assert planner["proveedor"] == "gemini"
    assert planner["clave_enmascarada"] == CLAVE[:4] + "…" + CLAVE[-4:]


def test_eliminar_deja_sin_configurar_y_bloquea_la_corrida(api, monkeypatch):
    r = api.eliminar_api_rol("reviewer")
    assert r["ok"]
    assert not next(x for x in r["roles"] if x["agente"] == "reviewer")["configurado"]

    monkeypatch.setenv("QAGENT_FAKE_LLM", "0")  # con la IA real, el rol hace falta
    monkeypatch.setattr(
        "qagent.sandbox.estado.estado_docker",
        lambda: {"estado": "ok", "mensaje": "ok"},
    )
    entorno = api.verificar_entorno()
    assert not entorno["listo"]
    assert any("Falta configurar el Reviewer" in p for p in entorno["problemas"])
