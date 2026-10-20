"""Pruebas de la persistencia del tema de apariencia en config.local.toml."""

from __future__ import annotations

import sys
from pathlib import Path

from qagent.app.desktop import DesktopAPI
from qagent.config.apariencia import (
    TEMA_POR_DEFECTO,
    guardar_tema,
    leer_tema,
    reemplazar_seccion_apariencia,
)

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib


def test_sin_archivo_local_devuelve_tema_por_defecto(tmp_path: Path) -> None:
    local = tmp_path / "config.local.toml"
    assert leer_tema(local) == TEMA_POR_DEFECTO


def test_guardar_tema_crea_el_archivo_y_se_lee(tmp_path: Path) -> None:
    local = tmp_path / "usuario" / "config.local.toml"
    res = guardar_tema("claro", local)
    assert res["ok"] is True
    assert res["tema"] == "claro"

    datos = tomllib.loads(local.read_text(encoding="utf-8"))
    assert datos["apariencia"]["tema"] == "claro"
    assert leer_tema(local) == "claro"


def test_guardar_tema_actualiza_seccion_existente(tmp_path: Path) -> None:
    local = tmp_path / "config.local.toml"
    guardar_tema("claro", local)
    res = guardar_tema("oscuro", local)
    assert res["ok"] is True
    assert leer_tema(local) == "oscuro"


def test_rechaza_temas_no_validos(tmp_path: Path) -> None:
    local = tmp_path / "config.local.toml"
    res = guardar_tema("neon", local)
    assert res["ok"] is False
    assert not local.exists()


def test_reemplazar_seccion_apariencia_conserva_otras_secciones() -> None:
    previo = """[reintentos]
max_intentos = 2

[apariencia]
tema = "oscuro"

[agentes.planner]
proveedor = "openai"
"""
    nuevo = reemplazar_seccion_apariencia(previo, "claro")
    datos = tomllib.loads(nuevo)
    assert datos["reintentos"]["max_intentos"] == 2
    assert datos["apariencia"]["tema"] == "claro"
    assert datos["agentes"]["planner"]["proveedor"] == "openai"


def test_desktop_api_obtener_y_guardar_tema(monkeypatch, tmp_path: Path) -> None:
    local = tmp_path / "config.local.toml"
    monkeypatch.setattr("qagent.config.carga.RUTA_CONFIG_LOCAL", local)

    api = DesktopAPI()
    assert api.obtener_tema()["tema"] == "oscuro"

    res = api.guardar_tema("claro")
    assert res["ok"] is True
    assert api.obtener_tema()["tema"] == "claro"
