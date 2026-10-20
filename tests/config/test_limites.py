"""Límites de verificación editables desde Configuración (intentos por función)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from qagent.config.limites import (
    MAX_INTENTOS,
    MIN_INTENTOS,
    guardar_max_intentos,
    leer_limites,
    reemplazar_seccion_reintentos,
)

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.10
    import tomli as tomllib

EQUIPO = """
[reintentos]
max_intentos = 3

[sandbox]
cpus = 4
memoria = "3g"
timeout_s = 120
"""


@pytest.fixture
def rutas(tmp_path: Path) -> tuple[Path, Path]:
    equipo = tmp_path / "config.toml"
    equipo.write_text(EQUIPO, encoding="utf-8")
    return equipo, tmp_path / "usuario" / "config.local.toml"


def test_sin_archivo_local_se_leen_los_valores_del_equipo(
    rutas: tuple[Path, Path],
) -> None:
    equipo, local = rutas
    limites = leer_limites(equipo, local)
    assert limites["ok"] is True
    assert limites["max_intentos"] == 3
    assert limites["max_intentos_equipo"] == 3
    assert (limites["intentos_min"], limites["intentos_max"]) == (
        MIN_INTENTOS,
        MAX_INTENTOS,
    )
    assert limites["timeout_s"] == 120
    assert limites["timeout_editable"] is False


def test_guardar_crea_el_archivo_local_y_se_superpone_al_equipo(
    rutas: tuple[Path, Path],
) -> None:
    equipo, local = rutas
    resultado = guardar_max_intentos(2, local)
    assert resultado["ok"] is True
    datos = tomllib.loads(local.read_text(encoding="utf-8"))
    assert datos["reintentos"]["max_intentos"] == 2
    limites = leer_limites(equipo, local)
    assert limites["max_intentos"] == 2
    assert limites["max_intentos_equipo"] == 3
    # El config.toml del equipo no se toca.
    assert equipo.read_text(encoding="utf-8") == EQUIPO


def test_guardar_reemplaza_la_seccion_y_conserva_el_resto(
    rutas: tuple[Path, Path],
) -> None:
    _, local = rutas
    local.parent.mkdir(parents=True)
    local.write_text(
        '[agentes.planner]\nproveedor = "gemini"\nmodelo = "x"\n\n[reintentos]\nmax_intentos = 3\n',
        encoding="utf-8",
    )
    assert guardar_max_intentos(1, local)["ok"] is True
    datos = tomllib.loads(local.read_text(encoding="utf-8"))
    assert datos["reintentos"]["max_intentos"] == 1
    assert datos["agentes"]["planner"]["proveedor"] == "gemini"
    assert local.read_text(encoding="utf-8").count("[reintentos]") == 1


@pytest.mark.parametrize("valor", [0, 4, -1, "2", 2.0, True, None])
def test_un_valor_invalido_no_escribe_nada(
    rutas: tuple[Path, Path], valor: object
) -> None:
    _, local = rutas
    resultado = guardar_max_intentos(valor, local)
    assert resultado["ok"] is False
    assert not local.exists()


def test_el_tiempo_maximo_es_del_equipo_aunque_el_local_lo_intente(
    rutas: tuple[Path, Path],
) -> None:
    equipo, local = rutas
    local.parent.mkdir(parents=True)
    local.write_text("[sandbox]\ntimeout_s = 5\n", encoding="utf-8")
    assert leer_limites(equipo, local)["timeout_s"] == 120


def test_un_local_con_error_de_formato_no_se_sobrescribe(
    rutas: tuple[Path, Path],
) -> None:
    equipo, local = rutas
    local.parent.mkdir(parents=True)
    roto = "[agentes.planner\nproveedor = \n"
    local.write_text(roto, encoding="utf-8")
    assert leer_limites(equipo, local)["ok"] is False
    assert guardar_max_intentos(2, local)["ok"] is False
    assert local.read_text(encoding="utf-8") == roto


def test_reemplazar_agrega_la_seccion_al_final_si_falta() -> None:
    texto = '# encabezado\n[agentes.planner]\nmodelo = "x"\n'
    nuevo = reemplazar_seccion_reintentos(texto, 2)
    assert nuevo.startswith("# encabezado\n[agentes.planner]")
    assert tomllib.loads(nuevo)["reintentos"]["max_intentos"] == 2


def test_guardar_max_tokens_crea_seccion_presupuesto(
    rutas: tuple[Path, Path],
) -> None:
    from qagent.config.limites import guardar_max_tokens

    equipo, local = rutas
    resultado = guardar_max_tokens(50000, local)
    assert resultado["ok"] is True
    datos = tomllib.loads(local.read_text(encoding="utf-8"))
    assert datos["presupuesto"]["max_tokens_por_corrida"] == 50000
    limites = leer_limites(equipo, local)
    assert limites["max_tokens_por_corrida"] == 50000


def test_guardar_max_tokens_cero_o_none_elimina_limite(
    rutas: tuple[Path, Path],
) -> None:
    from qagent.config.limites import guardar_max_tokens

    equipo, local = rutas
    guardar_max_tokens(10000, local)
    assert leer_limites(equipo, local)["max_tokens_por_corrida"] == 10000

    resultado = guardar_max_tokens(0, local)
    assert resultado["ok"] is True
    assert leer_limites(equipo, local)["max_tokens_por_corrida"] is None


@pytest.mark.parametrize("valor", [-10, "5000", 12.5, True])
def test_guardar_max_tokens_invalido(rutas: tuple[Path, Path], valor: object) -> None:
    from qagent.config.limites import guardar_max_tokens

    _, local = rutas
    res = guardar_max_tokens(valor, local)
    assert res["ok"] is False


def test_guardar_limites_guarda_intentos_y_tokens(
    rutas: tuple[Path, Path],
) -> None:
    from qagent.config.limites import guardar_limites

    equipo, local = rutas
    res = guardar_limites(max_intentos=2, max_tokens=75000, ruta_local=local)
    assert res["ok"] is True
    limites = leer_limites(equipo, local)
    assert limites["max_intentos"] == 2
    assert limites["max_tokens_por_corrida"] == 75000
