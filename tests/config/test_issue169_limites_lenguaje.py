"""#169: límites del sandbox por lenguaje en `[sandbox.<lenguaje>]` de config.toml."""

from __future__ import annotations

from pathlib import Path

import pytest

from qagent.config import cargar_configuracion
from qagent.config.carga import RUTA_CONFIG
from qagent.lenguajes import adaptador_para
from qagent.sandbox.modelos import LimitesSandbox

PYTHON = LimitesSandbox(cpus=4.0, memoria="3g", timeout_s=120)


def _cargar(tmp_path: Path, extra: str = "", reemplazos: dict | None = None):
    """Carga config.toml del equipo con texto agregado al final de `[sandbox]`."""
    texto = RUTA_CONFIG.read_text(encoding="utf-8")
    for viejo, nuevo in (reemplazos or {}).items():
        assert viejo in texto, viejo
        texto = texto.replace(viejo, nuevo, 1)
    if extra:
        marca = "# Cada agente usa"
        texto = texto.replace(marca, extra + "\n" + marca, 1)
    ruta = tmp_path / "config.toml"
    ruta.write_text(texto, encoding="utf-8")
    return cargar_configuracion(ruta, "no-existe.env", simulado=True)


def test_python_conserva_sus_limites():
    config = cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config

    assert config.sandbox == PYTHON
    assert config.limites_sandbox("python") == PYTHON
    assert config.limites_sandbox() == PYTHON


def test_el_equipo_fija_limites_medidos_para_node_y_java():
    config = cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config

    for lenguaje in ("javascript", "typescript"):
        assert config.limites_sandbox(lenguaje) == LimitesSandbox(4.0, "2g", 120)
    assert config.limites_sandbox("java") == LimitesSandbox(4.0, "4g", 300)


def test_cada_adaptador_obtiene_los_limites_de_su_lenguaje():
    config = cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config

    java = adaptador_para("java")
    assert config.limites_sandbox(java.lenguaje).memoria == "4g"
    assert config.limites_sandbox(adaptador_para("python").lenguaje) == config.sandbox


def test_lo_que_falta_se_toma_de_sandbox(tmp_path):
    carga = _cargar(
        tmp_path,
        reemplazos={'memoria = "4g"': "", "timeout_s = 300": "timeout_s = 600"},
    )

    assert carga.ok, carga.avisos
    assert carga.config.limites_sandbox("java") == LimitesSandbox(4.0, "3g", 600)


def test_los_cpu_son_siempre_los_de_sandbox(tmp_path):
    carga = _cargar(tmp_path, reemplazos={"cpus = 4": "cpus = 2"})

    assert carga.ok, carga.avisos
    assert carga.config.limites_sandbox("java").cpus == 2.0
    assert carga.config.limites_sandbox("javascript").cpus == 2.0


def test_sin_secciones_por_lenguaje_todos_usan_sandbox(tmp_path):
    texto = RUTA_CONFIG.read_text(encoding="utf-8")
    inicio = texto.index("# Límites por lenguaje")
    fin = texto.index("# Cada agente usa")
    ruta = tmp_path / "config.toml"
    ruta.write_text(texto[:inicio] + texto[fin:], encoding="utf-8")

    config = cargar_configuracion(ruta, "no-existe.env", simulado=True).config

    assert config.sandbox_lenguajes == {}
    assert config.limites_sandbox("java") == PYTHON


@pytest.mark.parametrize(
    "extra, aviso",
    [
        ('[sandbox.cobol]\nmemoria = "1g"\n', "[sandbox.cobol]"),
        ("[sandbox.python]\ncpus = 8\n", "solo admite memoria y timeout_s"),
    ],
)
def test_seccion_desconocida_avisa(tmp_path, extra, aviso):
    carga = _cargar(tmp_path, extra)

    assert carga.config is None
    assert any(aviso in a for a in carga.avisos_config), carga.avisos_config


@pytest.mark.parametrize(
    "viejo, nuevo, aviso",
    [
        ('memoria = "4g"', 'memoria = "4 GB"', "formato de Docker"),
        ("timeout_s = 300", "timeout_s = 0", "mayor que 0"),
        ("timeout_s = 300", "timeout_s = 2.5", "entero"),
    ],
)
def test_valor_invalido_de_un_lenguaje_avisa_con_su_seccion(
    tmp_path, viejo, nuevo, aviso
):
    carga = _cargar(tmp_path, reemplazos={viejo: nuevo})

    assert carga.config is None
    assert any("[sandbox.java]" in a and aviso in a for a in carga.avisos_config), (
        carga.avisos_config
    )


def test_config_local_no_cambia_los_limites_por_lenguaje(tmp_path):
    local = tmp_path / "config.local.toml"
    local.write_text('[sandbox.java]\nmemoria = "32g"\n', encoding="utf-8")

    carga = cargar_configuracion(
        RUTA_CONFIG, "no-existe.env", simulado=True, ruta_local=local
    )

    assert carga.ok, carga.avisos
    assert carga.config.limites_sandbox("java").memoria == "4g"
