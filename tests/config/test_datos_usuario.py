"""TA-06: los datos del usuario viven en `~/.qagent/`, nunca en la carpeta del programa."""

from __future__ import annotations

from pathlib import Path

import pytest

from qagent.config import carga, roles
from qagent.config.carga import cargar_configuracion, migrar_desde_repositorio
from qagent.llm import proveedores
from qagent.usuario import carpeta_usuario

CONFIG_EQUIPO = """
[presupuesto]
tope_por_corrida_usd = 1.0
tope_semestre_usd = 25.0
[reintentos]
max_intentos = 3
[umbrales]
pass_rate_min = 70
cobertura_lineas_min = 60
iteraciones_promedio_max = 2.0
[agentes.planner]
proveedor = "xiaomi"
modelo = "mimo-v2.6-pro"
precio_entrada_usd_m = 0.435
precio_salida_usd_m = 0.87
[agentes.generator]
proveedor = "xiaomi"
modelo = "mimo-v2.6-pro"
precio_entrada_usd_m = 0.435
precio_salida_usd_m = 0.87
[agentes.reviewer]
proveedor = "openai"
modelo = "gpt-6-luna"
precio_entrada_usd_m = 0.10
precio_salida_usd_m = 0.50
"""


class TransporteOk:
    def enviar(self, **_):
        return {"choices": [{"message": {"content": "OK"}}]}


# --- Dónde quedan los archivos ---------------------------------------------------


def test_env_y_config_local_estan_en_la_carpeta_del_usuario():
    import importlib

    limpio = importlib.reload(carga)  # sin el parche de conftest
    try:
        assert limpio.RUTA_ENV == carpeta_usuario() / ".env"
        assert limpio.RUTA_CONFIG_LOCAL == carpeta_usuario() / "config.local.toml"
    finally:
        importlib.reload(carga)


# --- Migración desde la raíz del repositorio -------------------------------------


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    return repo


def test_mueve_env_y_config_local_del_repositorio(tmp_path: Path):
    repo, destino = _repo(tmp_path), tmp_path / "home" / ".qagent"
    (repo / ".env").write_text("GEMINI_API_KEY_PLANNER=x\n", encoding="utf-8")
    (repo / "config.local.toml").write_text("[agentes]\n", encoding="utf-8")

    assert migrar_desde_repositorio(repo, destino) == [".env", "config.local.toml"]
    assert (destino / ".env").read_text(
        encoding="utf-8"
    ) == "GEMINI_API_KEY_PLANNER=x\n"
    assert not (repo / ".env").exists() and not (repo / "config.local.toml").exists()


def test_nunca_sobrescribe_lo_que_ya_esta_en_el_destino(tmp_path: Path):
    repo, destino = _repo(tmp_path), tmp_path / ".qagent"
    destino.mkdir()
    (repo / ".env").write_text("VIEJO=1\n", encoding="utf-8")
    (destino / ".env").write_text("NUEVO=1\n", encoding="utf-8")

    assert migrar_desde_repositorio(repo, destino) == []
    assert (destino / ".env").read_text(encoding="utf-8") == "NUEVO=1\n"
    assert (repo / ".env").exists()


def test_instalado_sin_repositorio_no_hace_nada(tmp_path: Path):
    sin_repo = tmp_path / "site-packages"
    sin_repo.mkdir()
    (sin_repo / ".env").write_text("X=1\n", encoding="utf-8")

    assert migrar_desde_repositorio(sin_repo, tmp_path / ".qagent") == []
    assert not (tmp_path / ".qagent").exists()


# --- La pantalla Configuración no toca el config.toml del equipo -----------------


@pytest.fixture
def rutas(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(proveedores, "TransporteHTTP", TransporteOk)
    equipo = tmp_path / "programa" / "config.toml"
    equipo.parent.mkdir()
    equipo.write_text(CONFIG_EQUIPO, encoding="utf-8")
    usuario = tmp_path / "home" / ".qagent"
    return equipo, usuario / ".env", usuario / "config.local.toml"


def test_guardar_api_escribe_en_el_config_local_del_usuario(rutas):
    equipo, env, local = rutas
    original = equipo.read_text(encoding="utf-8")

    r = roles.configurar_rol(
        "planner",
        "gemini",
        "gemini-2.5-flash",
        "AIza-prueba-123",
        ruta_config=equipo,
        ruta_env=env,
        ruta_local=local,
    )

    assert r["ok"], r
    assert equipo.read_text(encoding="utf-8") == original
    assert 'proveedor = "gemini"' in local.read_text(encoding="utf-8")
    config = cargar_configuracion(equipo, env, simulado=False, ruta_local=local).config
    assert config.agentes["planner"].proveedor == "gemini"
    assert config.agentes["reviewer"].proveedor == "openai"  # el resto, del equipo


def test_eliminar_api_deja_sin_configurar_sin_tocar_el_equipo(rutas):
    equipo, env, local = rutas
    original = equipo.read_text(encoding="utf-8")

    r = roles.eliminar_rol(
        "reviewer", ruta_config=equipo, ruta_env=env, ruta_local=local
    )

    assert r["ok"], r
    assert equipo.read_text(encoding="utf-8") == original
    carga_ = cargar_configuracion(equipo, env, simulado=False, ruta_local=local)
    assert carga_.sin_configurar == ["reviewer"]
    assert not carga_.ok  # con la IA real, un agente sin configurar bloquea la corrida
    estado = {e["agente"]: e for e in roles.leer_roles(equipo, env, local)}
    assert estado["reviewer"]["configurado"] is False
    assert estado["planner"]["configurado"] is True


# --- Demostración -----------------------------------------------------------------


def test_la_corrida_de_demostracion_va_a_la_carpeta_del_usuario():
    from qagent.app.desktop import _resolver_ruta_proyecto
    from qagent.storage.corrida_demo import CORRIDA_DEMO_ID

    raiz = _resolver_ruta_proyecto("", CORRIDA_DEMO_ID)

    assert raiz == carpeta_usuario() / "demo"
