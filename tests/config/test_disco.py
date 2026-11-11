"""Límites de espacio en disco de `[disco]` en config.toml (#267)."""

from __future__ import annotations

from pathlib import Path

import pytest

from qagent.config import carga
from qagent.config.disco import BYTES_POR_GB, CLAVES, LimitesDisco, leer_limites_disco


def _config(tmp_path: Path, texto: str) -> Path:
    ruta = tmp_path / "config.toml"
    ruta.write_text(texto, encoding="utf-8")
    return ruta


def test_el_config_del_equipo_define_todos_los_limites_de_disco():
    avisos: list[str] = []

    limites = leer_limites_disco(avisos=avisos)

    assert avisos == []
    for clave in CLAVES:
        assert getattr(limites, clave) is not None
        assert getattr(limites, clave) > 0


def test_los_gigabytes_se_convierten_a_bytes():
    limites = LimitesDisco(tope_imagenes_derivadas_gb=10)

    assert limites.tope_imagenes_derivadas_bytes == 10 * BYTES_POR_GB
    assert LimitesDisco().tope_imagenes_derivadas_bytes is None


def test_lee_los_valores_de_la_seccion_disco(tmp_path):
    ruta = _config(
        tmp_path,
        "[disco]\ntope_imagenes_derivadas_gb = 2.5\ncache_antiguedad_dias = 3\n",
    )

    limites = leer_limites_disco(ruta)

    assert limites.tope_imagenes_derivadas_gb == 2.5
    assert limites.cache_antiguedad_dias == 3


@pytest.mark.parametrize("valor", ["0", "-1", '"mucho"', "true", "[1]"])
def test_un_valor_invalido_desactiva_solo_ese_limite(tmp_path, valor):
    ruta = _config(
        tmp_path,
        f"[disco]\ntope_imagenes_derivadas_gb = {valor}\ncache_antiguedad_dias = 7\n",
    )
    avisos: list[str] = []

    limites = leer_limites_disco(ruta, avisos)

    assert limites.tope_imagenes_derivadas_gb is None
    assert limites.cache_antiguedad_dias == 7
    assert any("tope_imagenes_derivadas_gb" in a for a in avisos)


def test_sin_la_seccion_no_se_aplica_ningun_limite(tmp_path):
    avisos: list[str] = []

    assert (
        leer_limites_disco(_config(tmp_path, "[x]\na = 1\n"), avisos) == LimitesDisco()
    )
    assert any("[disco]" in a for a in avisos)


@pytest.mark.parametrize("contenido", [None, "esto no es [toml"])
def test_un_config_ilegible_no_lanza_y_no_aplica_limites(tmp_path, contenido):
    ruta = tmp_path / "config.toml"
    if contenido is not None:
        ruta.write_text(contenido, encoding="utf-8")

    assert leer_limites_disco(ruta) == LimitesDisco()


def test_el_usuario_no_puede_cambiar_los_limites_desde_su_config_local():
    base = {"disco": {"tope_imagenes_derivadas_gb": 10}}
    local = {"disco": {"tope_imagenes_derivadas_gb": 9999}}

    assert "disco" in carga.SECCIONES_SOLO_EQUIPO
    assert carga.superponer_config(base, local)["disco"] == base["disco"]
