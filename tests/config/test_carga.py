"""Pruebas de la carga de config.toml y .env (EN-06)."""

from __future__ import annotations

import io
import json
import logging
import pickle
from pathlib import Path

import pytest

from pyagent.config import (
    CLAVE_POR_PROVEEDOR,
    Claves,
    FiltroSecretos,
    cargar_configuracion,
    leer_env,
    verificar_entorno,
)
from pyagent.config import carga as carga_mod
from pyagent.config.carga import RUTA_CONFIG

# Valores de prueba armados en tiempo de ejecución: no son claves reales.
SECRETO_A = "valor-de-prueba-" + "A" * 12
SECRETO_O = "valor-de-prueba-" + "O" * 12
SECRETO_X = "valor-de-prueba-" + "X" * 12


def _escribir_env(ruta: Path, **valores: str) -> Path:
    ruta.write_text("".join(f"{k}={v}\n" for k, v in valores.items()), encoding="utf-8")
    return ruta


@pytest.fixture
def env_completo(tmp_path: Path) -> Path:
    return _escribir_env(
        tmp_path / ".env",
        ANTHROPIC_API_KEY=SECRETO_A,
        OPENAI_API_KEY=SECRETO_O,
        XIAOMI_API_KEY=SECRETO_X,
    )


def _config_con(tmp_path: Path, reemplazos: dict[str, str]) -> Path:
    """Copia config.toml cambiando fragmentos de texto."""
    texto = RUTA_CONFIG.read_text(encoding="utf-8")
    for viejo, nuevo in reemplazos.items():
        assert viejo in texto, f"el fragmento '{viejo}' ya no está en config.toml"
        texto = texto.replace(viejo, nuevo, 1)
    destino = tmp_path / "config.toml"
    destino.write_text(texto, encoding="utf-8")
    return destino


# ---------- config.toml ----------


def test_config_del_equipo_es_valida_con_todas_las_claves(env_completo):
    carga = cargar_configuracion(RUTA_CONFIG, env_completo, simulado=False)
    assert carga.ok, carga.avisos
    config = carga.config
    assert config.presupuesto.tope_por_corrida_usd > 0
    assert (
        config.presupuesto.tope_semestre_usd >= config.presupuesto.tope_por_corrida_usd
    )
    assert config.max_intentos == 3
    assert set(config.agentes) == {"planner", "generator", "reviewer"}
    assert config.agentes["reviewer"].modelo
    assert config.umbrales.cobertura_lineas_min > 0


def test_cada_proveedor_de_config_tiene_variable_de_clave():
    carga = cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True)
    for proveedor in carga.config.proveedores():
        assert proveedor in CLAVE_POR_PROVEEDOR


def test_falta_un_precio_avisa_y_no_hay_config(tmp_path, env_completo):
    ruta = _config_con(tmp_path, {"precio_salida_usd_m = 0.50": ""})
    carga = cargar_configuracion(ruta, env_completo, simulado=False)
    assert not carga.ok
    assert carga.config is None
    assert any(
        "precio_salida_usd_m" in a and "agentes.reviewer" in a for a in carga.avisos
    )


def test_falta_el_tope_de_gasto(tmp_path, env_completo):
    ruta = _config_con(tmp_path, {"tope_por_corrida_usd = 1.00": ""})
    carga = cargar_configuracion(ruta, env_completo, simulado=False)
    assert any("tope_por_corrida_usd" in a for a in carga.avisos_config)


@pytest.mark.parametrize("malo", ["0", "-2", '"mucho"', "true"])
def test_tope_invalido(tmp_path, env_completo, malo):
    ruta = _config_con(
        tmp_path, {"tope_por_corrida_usd = 1.00": f"tope_por_corrida_usd = {malo}"}
    )
    carga = cargar_configuracion(ruta, env_completo, simulado=False)
    assert any("mayor que 0" in a for a in carga.avisos_config)


def test_reintentos_deben_ser_enteros(tmp_path, env_completo):
    ruta = _config_con(tmp_path, {"max_intentos = 3": "max_intentos = 2.5"})
    carga = cargar_configuracion(ruta, env_completo, simulado=False)
    assert any("entero" in a for a in carga.avisos_config)


def test_falta_la_seccion_de_umbrales(tmp_path, env_completo):
    ruta = _config_con(tmp_path, {"pass_rate_min = 70": ""})
    carga = cargar_configuracion(ruta, env_completo, simulado=False)
    assert any("pass_rate_min" in a for a in carga.avisos_config)


def test_proveedor_desconocido(tmp_path, env_completo):
    ruta = _config_con(tmp_path, {'proveedor = "openai"': 'proveedor = "inventado"'})
    carga = cargar_configuracion(ruta, env_completo, simulado=False)
    assert any("inventado" in a for a in carga.avisos_config)


def test_falta_un_agente(tmp_path, env_completo):
    ruta = _config_con(tmp_path, {"[agentes.generator]": "[agentes.otro]"})
    carga = cargar_configuracion(ruta, env_completo, simulado=False)
    assert any("agentes.generator" in a for a in carga.avisos_config)


def test_toml_con_sintaxis_invalida(tmp_path, env_completo):
    ruta = tmp_path / "config.toml"
    ruta.write_text("[presupuesto\nmal", encoding="utf-8")
    carga = cargar_configuracion(ruta, env_completo, simulado=False)
    assert carga.config is None
    assert any("sintaxis" in a for a in carga.avisos_config)


def test_falta_config_toml(tmp_path, env_completo):
    carga = cargar_configuracion(tmp_path / "nada.toml", env_completo, simulado=False)
    assert carga.config is None
    assert any("config.toml" in a for a in carga.avisos_config)


def test_reune_todos_los_problemas_en_vez_de_el_primero(tmp_path, env_completo):
    ruta = _config_con(
        tmp_path,
        {"precio_salida_usd_m = 0.50": "", "max_intentos = 3": "max_intentos = 0"},
    )
    carga = cargar_configuracion(ruta, env_completo, simulado=False)
    assert len(carga.avisos_config) >= 2


# ---------- .env ----------


def test_falta_una_clave_avisa_cual_y_quien_la_usa(tmp_path):
    env = _escribir_env(
        tmp_path / ".env", ANTHROPIC_API_KEY=SECRETO_A, XIAOMI_API_KEY=SECRETO_X
    )
    carga = cargar_configuracion(RUTA_CONFIG, env, simulado=False)
    assert not carga.ok
    assert len(carga.avisos_claves) == 1
    assert "OPENAI_API_KEY" in carga.avisos_claves[0]
    assert "reviewer" in carga.avisos_claves[0]


def test_clave_vacia_cuenta_como_faltante(tmp_path):
    env = _escribir_env(
        tmp_path / ".env",
        ANTHROPIC_API_KEY=SECRETO_A,
        OPENAI_API_KEY=SECRETO_O,
        XIAOMI_API_KEY="",
    )
    carga = cargar_configuracion(RUTA_CONFIG, env, simulado=False)
    assert any("XIAOMI_API_KEY" in a for a in carga.avisos_claves)


def test_solo_se_exigen_las_claves_de_los_proveedores_en_uso(tmp_path):
    # En config.toml el Planner usa Xiaomi (Anthropic está comentado): no hace falta su clave.
    env = _escribir_env(
        tmp_path / ".env", OPENAI_API_KEY=SECRETO_O, XIAOMI_API_KEY=SECRETO_X
    )
    assert cargar_configuracion(RUTA_CONFIG, env, simulado=False).ok


def test_si_falta_env_lo_crea_con_las_claves_vacias(tmp_path):
    env = tmp_path / ".env"
    carga = cargar_configuracion(RUTA_CONFIG, env, simulado=False)
    assert env.exists()
    assert leer_env(env) == {"XIAOMI_API_KEY": "", "OPENAI_API_KEY": ""}
    assert not carga.ok  # creado pero vacío: sigue bloqueado
    assert "Se creó el archivo .env" in carga.avisos_claves[0]
    assert any("OPENAI_API_KEY" in a for a in carga.avisos_claves[1:])


def test_no_sobrescribe_un_env_existente(tmp_path, env_completo):
    antes = env_completo.read_text(encoding="utf-8")
    cargar_configuracion(RUTA_CONFIG, env_completo, simulado=False)
    assert env_completo.read_text(encoding="utf-8") == antes


def test_crea_env_con_todas_las_claves_si_config_es_invalida(tmp_path):
    env = tmp_path / ".env"
    cargar_configuracion(tmp_path / "nada.toml", env, simulado=False)
    assert set(leer_env(env)) == set(CLAVE_POR_PROVEEDOR.values())


def test_avisa_si_no_puede_crear_env(tmp_path, monkeypatch):
    monkeypatch.setattr(carga_mod, "crear_env", lambda *_: False)
    carga = cargar_configuracion(RUTA_CONFIG, tmp_path / ".env", simulado=False)
    assert any("no se pudo crear" in a for a in carga.avisos_claves)


def test_con_ia_simulada_no_crea_env(tmp_path):
    cargar_configuracion(RUTA_CONFIG, tmp_path / ".env", simulado=True)
    assert not (tmp_path / ".env").exists()


def test_con_ia_simulada_no_se_exigen_claves(tmp_path):
    carga = cargar_configuracion(RUTA_CONFIG, tmp_path / ".env", simulado=True)
    assert carga.ok
    assert carga.avisos_claves == []


def test_simulado_se_toma_de_la_variable_de_entorno(tmp_path, monkeypatch):
    monkeypatch.setenv("PYAGENT_FAKE_LLM", "1")
    assert cargar_configuracion(RUTA_CONFIG, tmp_path / ".env").ok
    monkeypatch.setenv("PYAGENT_FAKE_LLM", "0")
    assert not cargar_configuracion(RUTA_CONFIG, tmp_path / ".env").ok


def test_leer_env_formatos(tmp_path):
    ruta = tmp_path / ".env"
    ruta.write_bytes(
        b"\xef\xbb\xbf# comentario\n"
        b"A=uno\n"
        b'B="con espacios y # hash"\n'
        b"C='comillas simples'\n"
        b"export D=exportada\n"
        b"E=valor # comentario al final\n"
        b"F=\n"
        b"linea sin igual\n"
        b"1MAL=x\n"
    )
    assert leer_env(ruta) == {
        "A": "uno",
        "B": "con espacios y # hash",
        "C": "comillas simples",
        "D": "exportada",
        "E": "valor",
        "F": "",
    }


# ---------- las claves nunca se exponen (RN-07) ----------


def test_claves_no_se_muestran_en_repr_ni_str(env_completo):
    claves = cargar_configuracion(RUTA_CONFIG, env_completo, simulado=False).claves
    for texto in (repr(claves), str(claves), f"{claves}", f"{claves!r}"):
        assert SECRETO_A not in texto
    assert claves.obtener("ANTHROPIC_API_KEY") == SECRETO_A  # solo con acceso explícito


def test_claves_no_se_serializan():
    with pytest.raises(TypeError):
        pickle.dumps(Claves({"X": SECRETO_A}))


def test_redactar_oculta_cualquier_clave():
    claves = Claves({"A": SECRETO_A, "O": SECRETO_O})
    texto = claves.redactar(f"fallo con {SECRETO_A} y también {SECRETO_O}")
    assert SECRETO_A not in texto and SECRETO_O not in texto
    assert texto.count("***") == 2


def test_filtro_de_logging_oculta_la_clave(env_completo):
    claves = cargar_configuracion(RUTA_CONFIG, env_completo, simulado=False).claves
    salida = io.StringIO()
    handler = logging.StreamHandler(salida)
    handler.addFilter(FiltroSecretos(claves))
    logger = logging.getLogger("prueba.en06")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        logger.info("Authorization: Bearer %s", SECRETO_A)
        logger.error(f"clave openai {SECRETO_O}")
    finally:
        logger.removeHandler(handler)
    registrado = salida.getvalue()
    assert "Bearer ***" in registrado
    assert SECRETO_A not in registrado and SECRETO_O not in registrado


def test_ningun_resultado_serializable_contiene_claves(tmp_path, env_completo):
    carga = cargar_configuracion(RUTA_CONFIG, env_completo, simulado=False)
    entorno = verificar_entorno(
        RUTA_CONFIG,
        env_completo,
        simulado=False,
        docker=lambda: {"estado": "ok", "mensaje": "ok"},
        git=lambda: {"estado": "ok", "mensaje": "ok"},
    )
    volcado = json.dumps(entorno) + repr(carga) + repr(carga.claves) + str(carga.avisos)
    for secreto in (SECRETO_A, SECRETO_O, SECRETO_X):
        assert secreto not in volcado


def test_avisos_con_clave_faltante_no_incluyen_las_que_si_estan(tmp_path):
    env = _escribir_env(tmp_path / ".env", ANTHROPIC_API_KEY=SECRETO_A)
    carga = cargar_configuracion(RUTA_CONFIG, env, simulado=False)
    assert SECRETO_A not in " ".join(carga.avisos)


# ---------- IA simulada también desde el .env ----------


@pytest.fixture
def sin_variable_del_sistema(monkeypatch):
    """Quita PYAGENT_FAKE_LLM del entorno del sistema para que decida el .env."""
    monkeypatch.delenv("PYAGENT_FAKE_LLM", raising=False)


def test_el_env_con_ia_simulada_no_exige_claves(tmp_path, sin_variable_del_sistema):
    ruta = _escribir_env(tmp_path / ".env", PYAGENT_FAKE_LLM="1")
    carga = cargar_configuracion(RUTA_CONFIG, ruta)
    assert carga.simulado
    assert carga.avisos_claves == []
    assert carga.ok


def test_sin_la_bandera_el_env_si_exige_claves(tmp_path, sin_variable_del_sistema):
    ruta = _escribir_env(tmp_path / ".env", ANTHROPIC_API_KEY=SECRETO_A)
    carga = cargar_configuracion(RUTA_CONFIG, ruta)
    assert not carga.simulado
    assert carga.avisos_claves  # faltan las de los otros proveedores


@pytest.mark.parametrize("valor", ["0", "", "si", "true"])
def test_solo_el_valor_1_activa_la_ia_simulada_en_el_env(
    tmp_path, sin_variable_del_sistema, valor
):
    ruta = _escribir_env(tmp_path / ".env", PYAGENT_FAKE_LLM=valor)
    assert not carga_mod.simulado_desde_env(ruta)


def test_lo_definido_en_el_sistema_manda_sobre_el_env(tmp_path, monkeypatch):
    ruta = _escribir_env(tmp_path / ".env", PYAGENT_FAKE_LLM="1")
    monkeypatch.setenv("PYAGENT_FAKE_LLM", "0")
    assert not carga_mod.modo_simulado(ruta)
    monkeypatch.setenv("PYAGENT_FAKE_LLM", "1")
    assert carga_mod.modo_simulado(_escribir_env(tmp_path / "otro.env", OTRA="x"))


def test_sin_archivo_env_la_ia_simulada_no_se_activa(
    tmp_path, sin_variable_del_sistema
):
    assert not carga_mod.simulado_desde_env(tmp_path / "no-existe.env")
    assert not carga_mod.modo_simulado(tmp_path / "no-existe.env")


def test_aplicar_simulacion_copia_solo_la_bandera_y_no_las_claves(
    tmp_path, monkeypatch, sin_variable_del_sistema
):
    ruta = _escribir_env(
        tmp_path / ".env", PYAGENT_FAKE_LLM="1", ANTHROPIC_API_KEY=SECRETO_A
    )
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert carga_mod.aplicar_simulacion_desde_env(ruta) is True
    import os

    assert os.environ["PYAGENT_FAKE_LLM"] == "1"
    assert "ANTHROPIC_API_KEY" not in os.environ  # las claves nunca pasan al entorno
    monkeypatch.delenv("PYAGENT_FAKE_LLM")  # limpieza de lo que puso la prueba


def test_aplicar_simulacion_no_pisa_lo_definido_en_el_sistema(tmp_path, monkeypatch):
    ruta = _escribir_env(tmp_path / ".env", PYAGENT_FAKE_LLM="1")
    monkeypatch.setenv("PYAGENT_FAKE_LLM", "0")
    assert carga_mod.aplicar_simulacion_desde_env(ruta) is False
    import os

    assert os.environ["PYAGENT_FAKE_LLM"] == "0"


def test_el_entorno_con_ia_simulada_en_el_env_solo_pide_docker_y_git(
    tmp_path, sin_variable_del_sistema
):
    ruta = _escribir_env(tmp_path / ".env", PYAGENT_FAKE_LLM="1")
    listo = {"estado": "ok", "mensaje": "ok"}
    resultado = verificar_entorno(
        RUTA_CONFIG, ruta, docker=lambda: listo, git=lambda: listo
    )
    assert resultado["simulado"] is True
    assert resultado["listo"] is True
