"""EP-10 (#172): la API del Explicador es obligatoria y la corrida explica con ella.

Usa la IA simulada y el ejecutor simulado de `test_corrida`: no ejecuta código ni
llama a una API real. La API se guarda como lo hace la pantalla Configuración.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from qagent import contracts
from qagent.almacenamiento import AlmacenProyecto
from qagent.config import cargar_configuracion, roles, verificar_entorno
from qagent.config.carga import RUTA_CONFIG
from qagent.llm import proveedores
from qagent.storage.registro import ARCHIVO_EXPLICACIONES
from tests.orchestrator.test_corrida import BANCO, CON_BUG
from tests.orchestrator.test_hu32_explicador_corrida import _leer, correr

# Valor de prueba armado en tiempo de ejecución: no es una clave real.
CLAVE_GEMINI = "clave-gemini-" + "E" * 20
LISTO = {"estado": "ok", "mensaje": "ok"}


class TransporteOk:
    """El proveedor responde bien a la prueba de conexión (sin red)."""

    def enviar(self, **_):
        return {"choices": [{"message": {"content": "OK"}}]}


@pytest.fixture
def proyecto(tmp_path: Path) -> AlmacenProyecto:
    carpeta = tmp_path / "banco"
    shutil.copytree(
        BANCO, carpeta, ignore=shutil.ignore_patterns("*.md", "*.json", ".qagent")
    )
    almacen = AlmacenProyecto(carpeta)
    almacen.inicializar()
    return almacen


@pytest.fixture
def usuario(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    """`.env` y `config.local.toml` de la carpeta del usuario, vacíos."""
    monkeypatch.setattr(proveedores, "TransporteHTTP", TransporteOk)
    carpeta = tmp_path / "home" / ".qagent"
    return carpeta / ".env", carpeta / "config.local.toml"


def test_con_la_config_del_equipo_la_corrida_explica_con_ia(proyecto):
    config = cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config
    resumen, carpeta = correr(proyecto, config)

    assert resumen.estado == "fin", resumen.motivo
    results = _leer(carpeta, "results.json")
    datos = _leer(carpeta, ARCHIVO_EXPLICACIONES)
    contracts.validar_explicaciones(datos, results_confiables=results)
    assert sorted(e["objetivo"] for e in datos["explicaciones"]) == sorted(CON_BUG)
    assert all(e["origen"] == "ia" for e in datos["explicaciones"])
    modelo = config.agentes["explicador"].modelo
    assert all(e["modelo"] == modelo for e in datos["explicaciones"])
    # Su modelo queda registrado con los de los demás agentes.
    assert results["modelos"]["explicador"]["modelo"] == modelo
    log = _leer(carpeta, "log.json")
    contracts.validar(contracts.RUN_LOG, log)
    assert log["totales_por_agente"]["explicador"]["llamadas"] == len(CON_BUG)


def test_la_api_guardada_desde_configuracion_redacta_las_explicaciones(
    proyecto, usuario
):
    env, local = usuario
    r = roles.configurar_rol(
        "explicador",
        "gemini",
        "gemini-2.5-flash",
        CLAVE_GEMINI,
        ruta_config=RUTA_CONFIG,
        ruta_env=env,
        ruta_local=local,
    )
    assert r["ok"], r

    config = cargar_configuracion(
        RUTA_CONFIG, env, simulado=True, ruta_local=local
    ).config
    _, carpeta = correr(proyecto, config)

    datos = _leer(carpeta, ARCHIVO_EXPLICACIONES)
    assert all(e["origen"] == "ia" for e in datos["explicaciones"])
    assert all(e["modelo"] == "gemini-2.5-flash" for e in datos["explicaciones"])
    assert CLAVE_GEMINI not in (carpeta / "log.json").read_text(encoding="utf-8")


def test_sin_la_api_del_explicador_no_se_puede_iniciar_con_la_ia_real(usuario):
    env, local = usuario
    assert roles.eliminar_rol(
        "explicador", ruta_config=RUTA_CONFIG, ruta_env=env, ruta_local=local
    )["ok"]

    entorno = verificar_entorno(
        RUTA_CONFIG,
        env,
        simulado=False,
        docker=lambda: LISTO,
        git=lambda: LISTO,
        ruta_local=local,
    )

    assert entorno["listo"] is False
    assert any("Falta configurar el Explicador" in p for p in entorno["problemas"])


def test_con_la_ia_simulada_un_explicador_sin_api_no_bloquea(proyecto, usuario):
    env, local = usuario
    roles.eliminar_rol(
        "explicador", ruta_config=RUTA_CONFIG, ruta_env=env, ruta_local=local
    )
    carga = cargar_configuracion(RUTA_CONFIG, env, simulado=True, ruta_local=local)
    assert carga.ok, carga.avisos

    resumen, carpeta = correr(proyecto, carga.config)

    assert resumen.estado == "fin", resumen.motivo
    datos = _leer(carpeta, ARCHIVO_EXPLICACIONES)
    assert all(e["origen"] == "ia" for e in datos["explicaciones"])
