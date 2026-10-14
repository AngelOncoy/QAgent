"""API de cada agente elegida desde la interfaz (HU-30): config.toml + .env de EN-06.

Regla: el proveedor se puede repetir entre agentes, la API key no (una por agente).

Las llamadas a los proveedores se simulan con un transporte falso: ninguna prueba sale a
la red ni usa claves reales.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from pyagent.config import cargar_configuracion, leer_env, verificar_entorno
from pyagent.config.roles import (
    configurar_rol,
    eliminar_rol,
    enmascarar,
    leer_roles,
    listar_proveedores,
    quitar_variable_env,
    reemplazar_seccion_agente,
    reemplazar_variable_env,
)
from pyagent.llm.cliente import ErrorLLM, SinConexion
from tests.config.config_equipo import CONFIG_EQUIPO

if sys.version_info >= (3, 11):
    import tomllib
else:  # Python 3.10
    import tomli as tomllib

# Valores de prueba armados en tiempo de ejecución: no son claves reales.
CLAVE_GEMINI = "clave-gemini-" + "G" * 20
CLAVE_XIAOMI = "clave-xiaomi-" + "X" * 20
CLAVE_OPENAI = "clave-openai-" + "O" * 20
CLAVE_GEMINI_2 = "clave-gemini-" + "H" * 20


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
    """config.toml del equipo y un .env casi vacío, en una carpeta temporal."""
    config = tmp_path / "config.toml"
    config.write_text(CONFIG_EQUIPO, encoding="utf-8")
    env = tmp_path / ".env"
    env.write_text("# claves\nPYAGENT_FAKE_LLM=0\n", encoding="utf-8")
    return config, env


def _guardar(rutas, agente, proveedor, modelo, clave=None, transporte=None):
    config, env = rutas
    return configurar_rol(
        agente,
        proveedor,
        modelo,
        clave,
        ruta_config=config,
        ruta_env=env,
        transporte=transporte or Transporte(),
    )


def _eliminar(rutas, agente):
    config, env = rutas
    return eliminar_rol(agente, ruta_config=config, ruta_env=env)


def _roles(rutas) -> dict[str, dict]:
    config, env = rutas
    return {r["agente"]: r for r in leer_roles(config, env)}


# --- Enmascarado -----------------------------------------------------------------------


def test_enmascarar_muestra_cuatro_al_inicio_y_cuatro_al_final():
    assert enmascarar("abcd" + "x" * 10 + "wxyz") == "abcd…wxyz"


@pytest.mark.parametrize("corta", ["", None, "abc", "12345678901"])
def test_enmascarar_oculta_entera_una_clave_corta(corta):
    resultado = enmascarar(corta)
    assert resultado in {"", "••••"}
    if corta:
        assert corta not in resultado


# --- Guardar y leer por rol ------------------------------------------------------------


def test_guardar_y_leer_la_configuracion_de_un_rol(rutas):
    r = _guardar(rutas, "planner", "gemini", "gemini-2.5-flash", CLAVE_GEMINI)

    assert r == {"ok": True, "mensaje": "Conectado ✓"}
    planner = _roles(rutas)["planner"]
    assert planner["configurado"]
    assert planner["proveedor"] == "gemini"
    assert planner["modelo"] == "gemini-2.5-flash"
    assert planner["clave_enmascarada"] == enmascarar(CLAVE_GEMINI)
    assert planner["variable"] == "GEMINI_API_KEY_PLANNER"


def test_cada_rol_usa_su_proveedor_sin_afectar_a_los_otros(rutas):
    _guardar(rutas, "planner", "gemini", "gemini-2.5-flash", CLAVE_GEMINI)
    _guardar(rutas, "generator", "xiaomi", "mimo-v2.6-pro", CLAVE_XIAOMI)
    _guardar(rutas, "reviewer", "openai", "gpt-5-mini", CLAVE_OPENAI)
    _guardar(rutas, "generator", "xiaomi", "mimo-v2.6-flash")  # cambiar solo uno

    roles = _roles(rutas)
    assert {a: (r["proveedor"], r["modelo"]) for a, r in roles.items()} == {
        "planner": ("gemini", "gemini-2.5-flash"),
        "generator": ("xiaomi", "mimo-v2.6-flash"),
        "reviewer": ("openai", "gpt-5-mini"),
    }
    carga = cargar_configuracion(*rutas, simulado=False)
    assert carga.ok, carga.avisos
    assert carga.config.agentes["generator"].modelo == "mimo-v2.6-flash"


def test_la_configuracion_persiste_en_disco(rutas):
    _guardar(rutas, "reviewer", "openrouter", "openai/gpt-oss-120b", CLAVE_OPENAI)
    # Una lectura nueva (como al volver a abrir la app) encuentra lo guardado.
    with open(rutas[0], "rb") as archivo:
        datos = tomllib.load(archivo)
    assert datos["agentes"]["reviewer"]["proveedor"] == "openrouter"
    assert leer_env(rutas[1])["OPENROUTER_API_KEY_REVIEWER"] == CLAVE_OPENAI


def test_el_resto_de_config_toml_no_cambia(rutas):
    config, _ = rutas
    antes = config.read_text(encoding="utf-8")
    _guardar(rutas, "generator", "gemini", "gemini-2.5-flash", CLAVE_GEMINI)
    despues = config.read_text(encoding="utf-8")

    seccion_planner = antes.split("[agentes.planner]")[1].split("[agentes.generator]")[
        0
    ]
    assert seccion_planner in despues
    assert antes.split("[agentes.planner]")[0] == despues.split("[agentes.planner]")[0]


# --- Las claves solo en .env -------------------------------------------------------------


def test_la_key_no_se_escribe_en_config_toml(rutas):
    config, env = rutas
    _guardar(rutas, "planner", "gemini", "gemini-2.5-flash", CLAVE_GEMINI)

    texto = config.read_text(encoding="utf-8")
    assert CLAVE_GEMINI not in texto
    assert enmascarar(CLAVE_GEMINI) not in texto
    with open(config, "rb") as archivo:
        planner = tomllib.load(archivo)["agentes"]["planner"]
    assert set(planner) == {
        "proveedor",
        "modelo",
        "precio_entrada_usd_m",
        "precio_salida_usd_m",
    }
    assert leer_env(env)["GEMINI_API_KEY_PLANNER"] == CLAVE_GEMINI


def test_guardar_solo_toca_config_toml_y_env(rutas, tmp_path):
    _guardar(rutas, "planner", "gemini", "gemini-2.5-flash", CLAVE_GEMINI)
    assert sorted(p.name for p in tmp_path.iterdir()) == [".env", "config.toml"]


def test_ninguna_respuesta_lleva_la_key_completa(rutas):
    config, env = rutas
    r = _guardar(rutas, "planner", "gemini", "gemini-2.5-flash", CLAVE_GEMINI)
    respuestas = [r, leer_roles(config, env), listar_proveedores()]
    assert all(CLAVE_GEMINI not in repr(x) for x in respuestas)


def test_la_env_conserva_las_demas_lineas(rutas):
    _, env = rutas
    _guardar(rutas, "planner", "gemini", "gemini-2.5-flash", CLAVE_GEMINI)
    _guardar(rutas, "planner", "gemini", "gemini-2.5-flash", CLAVE_GEMINI + "2")

    texto = env.read_text(encoding="utf-8")
    assert "# claves" in texto and "PYAGENT_FAKE_LLM=0" in texto
    assert texto.count("GEMINI_API_KEY_PLANNER=") == 1
    assert leer_env(env)["GEMINI_API_KEY_PLANNER"] == CLAVE_GEMINI + "2"


def test_reemplazar_variable_env_quita_duplicados_y_agrega_si_falta():
    texto = "A=1\nexport B=2\nB=3\n"
    assert reemplazar_variable_env(texto, "B", "nuevo") == "A=1\nB=nuevo\n"
    assert reemplazar_variable_env("A=1\n\n", "C", "x") == "A=1\nC=x\n"


# --- Mismo proveedor en varios roles, cada uno con su propia key ----------------------


def test_el_mismo_proveedor_en_dos_roles_con_keys_distintas(rutas):
    config, env = rutas
    assert _guardar(rutas, "planner", "gemini", "gemini-2.5-flash", CLAVE_GEMINI)["ok"]
    r = _guardar(rutas, "generator", "gemini", "gemini-2.5-flash-lite", CLAVE_GEMINI_2)

    assert r["ok"]
    valores = leer_env(env)
    assert valores["GEMINI_API_KEY_PLANNER"] == CLAVE_GEMINI
    assert valores["GEMINI_API_KEY_GENERATOR"] == CLAVE_GEMINI_2
    roles = _roles(rutas)
    assert roles["planner"]["clave_enmascarada"] == enmascarar(CLAVE_GEMINI)
    assert roles["generator"]["clave_enmascarada"] == enmascarar(CLAVE_GEMINI_2)
    carga = cargar_configuracion(config, env, simulado=False)
    assert carga.claves.obtener("GEMINI_API_KEY_GENERATOR") == CLAVE_GEMINI_2


def test_cambiar_la_key_de_un_rol_no_afecta_al_otro(rutas):
    _guardar(rutas, "planner", "gemini", "gemini-2.5-flash", CLAVE_GEMINI)
    _guardar(rutas, "generator", "gemini", "gemini-2.5-flash", CLAVE_GEMINI_2)
    _guardar(rutas, "generator", "gemini", "gemini-2.5-flash", CLAVE_GEMINI_2 + "b")

    valores = leer_env(rutas[1])
    assert valores["GEMINI_API_KEY_PLANNER"] == CLAVE_GEMINI
    assert valores["GEMINI_API_KEY_GENERATOR"] == CLAVE_GEMINI_2 + "b"


@pytest.mark.parametrize("proveedor", ["gemini", "openrouter"])
def test_la_key_de_otro_rol_se_rechaza_sin_llamar_al_proveedor(rutas, proveedor):
    config, env = rutas
    _guardar(rutas, "planner", "gemini", "gemini-2.5-flash", CLAVE_GEMINI)
    antes = (config.read_text(encoding="utf-8"), env.read_text(encoding="utf-8"))
    modelo = "gemini-2.5-flash" if proveedor == "gemini" else "openai/gpt-oss-120b"
    transporte = Transporte()

    r = _guardar(rutas, "reviewer", proveedor, modelo, CLAVE_GEMINI, transporte)

    assert not r["ok"]
    assert "ya la usa el Planner" in r["mensaje"]
    assert transporte.envios == []
    assert (
        config.read_text(encoding="utf-8"),
        env.read_text(encoding="utf-8"),
    ) == antes


def test_sin_key_en_otro_rol_del_mismo_proveedor_se_pide_una(rutas):
    _guardar(rutas, "planner", "gemini", "gemini-2.5-flash", CLAVE_GEMINI)
    transporte = Transporte()

    r = _guardar(rutas, "reviewer", "gemini", "gemini-2.5-flash", None, transporte)

    assert not r["ok"] and "Escribe la API key" in r["mensaje"]
    assert transporte.envios == []


def test_editar_sin_key_mantiene_la_propia(rutas):
    _guardar(rutas, "planner", "gemini", "gemini-2.5-flash", CLAVE_GEMINI)
    transporte = Transporte()

    r = _guardar(rutas, "planner", "gemini", "gemini-2.5-flash-lite", None, transporte)

    assert r["ok"]
    cabeceras = transporte.envios[0]["cabeceras"]
    assert cabeceras["Authorization"] == f"Bearer {CLAVE_GEMINI}"
    assert _roles(rutas)["planner"]["modelo"] == "gemini-2.5-flash-lite"


def test_cambiar_de_proveedor_pide_key_y_quita_la_anterior(rutas):
    _guardar(rutas, "planner", "gemini", "gemini-2.5-flash", CLAVE_GEMINI)
    assert not _guardar(rutas, "planner", "openai", "gpt-5-mini")["ok"]

    assert _guardar(rutas, "planner", "openai", "gpt-5-mini", CLAVE_OPENAI)["ok"]
    valores = leer_env(rutas[1])
    assert "GEMINI_API_KEY_PLANNER" not in valores
    assert valores["OPENAI_API_KEY_PLANNER"] == CLAVE_OPENAI


def test_una_key_compartida_de_antes_se_marca_como_repetida(rutas):
    """config.toml del equipo: Planner y Generator en Xiaomi con XIAOMI_API_KEY."""
    _, env = rutas
    env.write_text(f"XIAOMI_API_KEY={CLAVE_XIAOMI}\n", encoding="utf-8")

    roles = _roles(rutas)
    assert roles["planner"]["variable"] == "XIAOMI_API_KEY"
    assert roles["planner"]["clave_repetida_con"] == ["Generator"]
    assert roles["generator"]["clave_repetida_con"] == ["Planner"]
    # Mantenerla al editar no se permite: se pide una key propia.
    assert not _guardar(rutas, "planner", "xiaomi", "mimo-v2.6-pro")["ok"]
    assert _guardar(rutas, "planner", "xiaomi", "mimo-v2.6-pro", CLAVE_GEMINI_2)["ok"]
    assert _roles(rutas)["generator"]["clave_repetida_con"] == []


def test_listar_proveedores_no_ofrece_keys_de_otros_roles(rutas):
    _guardar(rutas, "planner", "gemini", "gemini-2.5-flash", CLAVE_GEMINI)
    gemini = next(p for p in listar_proveedores() if p["id"] == "gemini")
    assert "tiene_clave" not in gemini and "clave_enmascarada" not in gemini
    assert gemini["variables"]["reviewer"] == "GEMINI_API_KEY_REVIEWER"


def test_quitar_variable_env():
    assert quitar_variable_env("A=1\nB=2\nexport B=3\n", "B") == "A=1\n"
    assert quitar_variable_env("A=1\n", "B") == "A=1\n"


def test_sin_key_nueva_ni_guardada_no_llama_al_proveedor(rutas):
    transporte = Transporte()
    r = _guardar(rutas, "planner", "anthropic", "claude-opus-5-5", "", transporte)
    assert not r["ok"] and "API key" in r["mensaje"]
    assert transporte.envios == []


# --- Fallo de la prueba: no se guarda nada ----------------------------------------------


@pytest.mark.parametrize(
    ("error", "motivo"),
    [
        (ErrorLLM("HTTP 401", codigo=401), "Key inválida"),
        (SinConexion("sin red"), "Sin conexión"),
        (ErrorLLM("HTTP 404", codigo=404), "Modelo no disponible"),
    ],
)
def test_si_la_prueba_falla_no_se_guarda_nada(rutas, error, motivo):
    config, env = rutas
    antes = (config.read_text(encoding="utf-8"), env.read_text(encoding="utf-8"))

    r = _guardar(
        rutas, "planner", "gemini", "gemini-2.5-flash", CLAVE_GEMINI, Transporte(error)
    )

    assert not r["ok"] and r["mensaje"] == motivo
    assert (
        config.read_text(encoding="utf-8"),
        env.read_text(encoding="utf-8"),
    ) == antes


@pytest.mark.parametrize(
    ("agente", "proveedor", "modelo"),
    [
        ("otro", "gemini", "gemini-2.5-flash"),
        ("planner", "inventado", "x"),
        ("planner", "groq", "openai/gpt-oss-120b"),  # oculto en la interfaz
        ("planner", "gemini", "modelo-escrito-a-mano"),
    ],
)
def test_solo_se_aceptan_agentes_proveedores_y_modelos_del_catalogo(
    rutas, agente, proveedor, modelo
):
    transporte = Transporte()
    r = _guardar(rutas, agente, proveedor, modelo, CLAVE_GEMINI, transporte)
    assert not r["ok"]
    assert transporte.envios == []


def test_una_key_con_espacios_se_rechaza(rutas):
    r = _guardar(rutas, "planner", "gemini", "gemini-2.5-flash", "abc def ghi jkl mno")
    assert not r["ok"]


# --- Eliminar y bloqueo cuando falta un rol ----------------------------------------------


def test_eliminar_deja_el_rol_sin_configurar(rutas):
    config, env = rutas
    _guardar(rutas, "planner", "gemini", "gemini-2.5-flash", CLAVE_GEMINI)

    assert _eliminar(rutas, "planner")["ok"]

    roles = _roles(rutas)
    assert not roles["planner"]["configurado"]
    assert roles["generator"]["configurado"] and roles["reviewer"]["configurado"]
    assert "GEMINI_API_KEY_PLANNER" not in leer_env(env)  # la key era solo suya
    assert CLAVE_GEMINI not in config.read_text(encoding="utf-8")


def test_falta_un_rol_bloquea_e_indica_cual(rutas):
    config, env = rutas
    for clave in ("XIAOMI_API_KEY", "OPENAI_API_KEY"):
        env.write_text(
            env.read_text(encoding="utf-8") + f"{clave}=valor-de-prueba-123\n",
            encoding="utf-8",
        )
    _eliminar(rutas, "generator")

    carga = cargar_configuracion(config, env, simulado=False)
    assert not carga.ok
    assert carga.config is not None  # los demás roles siguen leyéndose
    assert carga.sin_configurar == ["generator"]
    assert any("Falta configurar el Generator" in a for a in carga.avisos)

    entorno = verificar_entorno(
        config,
        env,
        simulado=False,
        docker=lambda: {"estado": "ok", "mensaje": "ok"},
        git=lambda: {"estado": "ok", "mensaje": "ok"},
    )
    assert not entorno["listo"]
    assert "Generator" in entorno["mensaje"]


def test_con_ia_simulada_un_rol_sin_configurar_no_bloquea(rutas):
    config, env = rutas
    _eliminar(rutas, "reviewer")

    carga = cargar_configuracion(config, env, simulado=True)
    assert carga.ok
    assert carga.config.agentes["reviewer"].modelo == "ia-simulada"


def test_eliminar_un_rol_ya_eliminado_no_falla(rutas):
    config, _ = rutas
    _eliminar(rutas, "planner")
    antes = config.read_text(encoding="utf-8")
    assert _eliminar(rutas, "planner")["ok"]
    assert config.read_text(encoding="utf-8") == antes


def test_un_rol_eliminado_se_vuelve_a_agregar_en_su_lugar(rutas):
    config, _ = rutas
    _eliminar(rutas, "generator")
    _guardar(rutas, "generator", "gemini", "gemini-2.5-flash", CLAVE_GEMINI)

    texto = config.read_text(encoding="utf-8")
    assert texto.index("[agentes.planner]") < texto.index("[agentes.generator]")
    assert texto.index("[agentes.generator]") < texto.index("[agentes.reviewer]")


def test_reemplazar_seccion_respeta_lo_demas():
    texto = '# cabecera\n[a]\nx = 1\n\n[agentes.planner]\nproveedor = "x"\n# nota\n\n[b]\ny = 2\n'
    nuevo = reemplazar_seccion_agente(texto, "planner", ['proveedor = "gemini"'])
    assert (
        nuevo
        == '# cabecera\n[a]\nx = 1\n\n[agentes.planner]\nproveedor = "gemini"\n\n[b]\ny = 2\n'
    )
    assert (
        reemplazar_seccion_agente(texto, "planner", None)
        == "# cabecera\n[a]\nx = 1\n\n[b]\ny = 2\n"
    )


def test_un_rol_de_config_local_se_marca(rutas, tmp_path):
    config, env = rutas
    local = tmp_path / "config.local.toml"
    local.write_text(
        '[agentes.planner]\nproveedor = "gemini"\nmodelo = "gemini-2.5-flash"\n'
        "precio_entrada_usd_m = 0\nprecio_salida_usd_m = 0\n",
        encoding="utf-8",
    )
    roles = {r["agente"]: r for r in leer_roles(config, env, local)}
    assert roles["planner"]["desde_local"] and roles["planner"]["proveedor"] == "gemini"
    assert not roles["generator"]["desde_local"]
