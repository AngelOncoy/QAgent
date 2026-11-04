"""#244: el Recomendador se configura desde la pantalla Configuración.

Sin llamadas reales: la prueba de conexión usa un transporte simulado. Todo se escribe
en una carpeta temporal; el `config.toml` del equipo nunca se modifica.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from qagent.agents.recomendador_ia import RecomendadorIA, crear_recomendador_ia
from qagent.config import cargar_configuracion
from qagent.config.carga import RUTA_CONFIG, Claves, leer_env
from qagent.config.roles import (
    AGENTES_OPCIONALES,
    configurar_rol,
    eliminar_rol,
    leer_roles,
    listar_proveedores,
)
from qagent.llm import TokenTracker
from qagent.llm.cliente import SinConexion

# Valores de prueba armados en tiempo de ejecución: no son claves reales.
CLAVE = "clave-deepseek-" + "D" * 20
CLAVE_OTRA = "clave-deepseek-" + "E" * 20


class Transporte:
    """Responde bien (o con `error`) y registra las llamadas."""

    def __init__(self, error: BaseException | None = None) -> None:
        self.error = error
        self.envios: list[dict[str, Any]] = []

    def enviar(self, **kwargs: Any) -> dict[str, Any]:
        self.envios.append(kwargs)
        if self.error is not None:
            raise self.error
        return {"choices": [{"message": {"content": "OK"}}]}


@pytest.fixture
def rutas(tmp_path: Path) -> tuple[Path, Path]:
    """`config.local.toml` y `.env` temporales; el `config.toml` es el real del equipo."""
    env = tmp_path / ".env"
    env.write_text("# claves\n", encoding="utf-8")
    return tmp_path / "config.local.toml", env


def _guardar(rutas, agente="recomendador", clave=CLAVE, transporte=None):
    local, env = rutas
    return configurar_rol(
        agente,
        "deepseek",
        "deepseek-flash",
        clave,
        ruta_config=RUTA_CONFIG,
        ruta_env=env,
        ruta_local=local,
        transporte=transporte or Transporte(),
    )


def _roles(rutas, opcionales=True) -> dict[str, dict]:
    local, env = rutas
    return {
        r["agente"]: r
        for r in leer_roles(RUTA_CONFIG, env, local, con_opcionales=opcionales)
    }


def test_sin_pedirlo_solo_salen_las_etapas(rutas):
    assert list(_roles(rutas, opcionales=False)) == [
        "planner",
        "generator",
        "reviewer",
        "explicador",
    ]


def test_el_recomendador_sale_opcional_y_sin_configurar(rutas):
    roles = _roles(rutas)

    assert list(roles) == [
        "planner",
        "generator",
        "reviewer",
        "explicador",
        "recomendador",
    ]
    assert roles["recomendador"]["opcional"] is True
    assert roles["recomendador"]["configurado"] is False
    assert not roles["planner"]["opcional"]
    assert AGENTES_OPCIONALES == ("recomendador",)


def test_guardar_escribe_la_clave_en_env_y_el_modo_en_config_local(rutas):
    local, env = rutas
    equipo = RUTA_CONFIG.read_text(encoding="utf-8")

    r = _guardar(rutas)

    assert r["ok"], r
    assert "DEEPSEEK_API_KEY_RECOMENDADOR=" + CLAVE in env.read_text(encoding="utf-8")
    texto = local.read_text(encoding="utf-8")
    assert "[agentes.recomendador]" in texto
    assert 'modo = "ia"' in texto
    assert 'proveedor = "deepseek"' in texto and 'modelo = "deepseek-flash"' in texto
    assert CLAVE not in texto  # la clave nunca va al config
    assert RUTA_CONFIG.read_text(encoding="utf-8") == equipo  # el del equipo no cambia


def test_el_estado_trae_la_clave_enmascarada_y_su_variable(rutas):
    _guardar(rutas)

    rol = _roles(rutas)["recomendador"]

    assert rol["configurado"] and rol["tiene_clave"] and rol["opcional"]
    assert rol["proveedor"] == "deepseek" and rol["modelo"] == "deepseek-flash"
    assert rol["variable"] == "DEEPSEEK_API_KEY_RECOMENDADOR"
    assert CLAVE not in repr(rol) and rol["clave_enmascarada"] != CLAVE


def test_lo_guardado_lo_usa_el_recomendador_de_la_aplicacion(rutas):
    """La variable que escribe la pantalla es la que busca `crear_recomendador_ia`."""
    local, env = rutas
    _guardar(rutas)

    carga = cargar_configuracion(RUTA_CONFIG, env, simulado=True, ruta_local=local)
    assert carga.config.recomendador.modo == "ia"
    assert carga.config.recomendador.precio.agente == "recomendador"
    # Sin clave en esta carga simulada: se lee `.env` como lo haría la aplicación.
    claves = Claves(leer_env(env))

    recomendador = crear_recomendador_ia(
        carga.config.recomendador, TokenTracker(), claves, simulado=False
    )

    assert isinstance(recomendador, RecomendadorIA)


def test_sin_guardar_la_aplicacion_sigue_con_reglas(rutas):
    local, env = rutas

    carga = cargar_configuracion(RUTA_CONFIG, env, simulado=True, ruta_local=local)

    assert carga.config.recomendador.modo == "reglas"
    assert "recomendador" not in carga.config.agentes
    assert carga.avisos_config == []


def test_no_se_guarda_nada_si_la_conexion_falla(rutas):
    local, env = rutas
    antes = env.read_text(encoding="utf-8")

    r = _guardar(rutas, transporte=Transporte(error=SinConexion("sin red")))

    assert not r["ok"]
    assert not local.exists()
    assert env.read_text(encoding="utf-8") == antes


def test_pide_la_clave_si_no_hay_ninguna(rutas):
    r = _guardar(rutas, clave="")

    assert not r["ok"]
    assert "Recomendador" in r["mensaje"]


def test_quitar_vuelve_a_las_reglas_y_borra_la_clave(rutas):
    local, env = rutas
    _guardar(rutas)

    r = eliminar_rol(
        "recomendador", ruta_config=RUTA_CONFIG, ruta_env=env, ruta_local=local
    )

    assert r["ok"]
    assert "DEEPSEEK_API_KEY_RECOMENDADOR" not in env.read_text(encoding="utf-8")
    assert 'modo = "reglas"' in local.read_text(encoding="utf-8")
    assert not _roles(rutas)["recomendador"]["configurado"]
    carga = cargar_configuracion(RUTA_CONFIG, env, simulado=True, ruta_local=local)
    assert carga.config.recomendador.modo == "reglas"


def test_un_modo_reglas_a_mano_no_cuenta_como_configurado(rutas):
    local, _ = rutas
    local.write_text(
        '[agentes.recomendador]\nmodo = "reglas"\nproveedor = "deepseek"\n'
        'modelo = "deepseek-flash"\n',
        encoding="utf-8",
    )

    assert not _roles(rutas)["recomendador"]["configurado"]


def test_guardar_al_recomendador_no_toca_las_etapas(rutas):
    antes = {
        a: r["configurado"] for a, r in _roles(rutas).items() if a != "recomendador"
    }

    _guardar(rutas)

    despues = {
        a: r["configurado"] for a, r in _roles(rutas).items() if a != "recomendador"
    }
    assert despues == antes


def test_avisa_si_comparte_la_clave_con_una_etapa(rutas):
    _guardar(rutas, agente="planner", clave=CLAVE)
    _guardar(rutas, agente="recomendador", clave=CLAVE)

    roles = _roles(rutas)

    assert roles["recomendador"]["clave_repetida_con"] == ["Planner"]
    assert roles["planner"]["clave_repetida_con"] == ["Recomendador"]


def test_una_clave_distinta_no_se_marca_como_repetida(rutas):
    _guardar(rutas, agente="planner", clave=CLAVE)
    _guardar(rutas, agente="recomendador", clave=CLAVE_OTRA)

    assert _roles(rutas)["recomendador"]["clave_repetida_con"] == []


def test_un_agente_desconocido_se_rechaza(rutas):
    assert not _guardar(rutas, agente="inventado")["ok"]
    local, env = rutas
    assert not eliminar_rol(
        "inventado", ruta_config=RUTA_CONFIG, ruta_env=env, ruta_local=local
    )["ok"]


def test_el_catalogo_trae_la_variable_del_recomendador():
    deepseek = next(p for p in listar_proveedores() if p["id"] == "deepseek")

    assert deepseek["variables"]["recomendador"] == "DEEPSEEK_API_KEY_RECOMENDADOR"
    assert deepseek["variables"]["planner"] == "DEEPSEEK_API_KEY_PLANNER"


def test_la_ventana_pide_tambien_al_recomendador():
    pytest.importorskip("webview")
    from qagent.app.desktop import DesktopAPI

    roles = {r["agente"]: r for r in DesktopAPI().obtener_roles()}

    assert "recomendador" in roles and roles["recomendador"]["opcional"]
