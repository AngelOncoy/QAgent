"""Pruebas de precios por agente y del costo en el tracker (EN-05). 0 tokens reales."""

from __future__ import annotations

from pathlib import Path

import pytest

from pyagent.llm import (
    ConfiguracionInvalida,
    PrecioAgente,
    TokenTracker,
    cargar_precios,
)

CONFIG = """
[agentes.planner]
proveedor = "anthropic"
modelo = "planner-x"
precio_entrada_usd_m = 4.00
precio_salida_usd_m = 20.00

[agentes.generator]
proveedor = "xiaomi"
modelo = "gen-x"
precio_entrada_usd_m = 0.435
precio_salida_usd_m = 0.87

[agentes.reviewer]
proveedor = "openai"
modelo = "rev-x"
precio_entrada_usd_m = 0.10
precio_salida_usd_m = 0.50
"""


@pytest.fixture
def config(tmp_path: Path) -> Path:
    ruta = tmp_path / "config.toml"
    ruta.write_text(CONFIG, encoding="utf-8")
    return ruta


def test_lee_los_tres_agentes(config: Path) -> None:
    precios = cargar_precios(config)

    assert set(precios) == {"planner", "generator", "reviewer"}
    assert precios["planner"] == PrecioAgente(
        "planner", "anthropic", "planner-x", 4.0, 20.0
    )


def test_config_del_repositorio_es_valido() -> None:
    assert set(cargar_precios()) == {"planner", "generator", "reviewer"}


def test_costo_es_tokens_por_precio_sobre_un_millon(config: Path) -> None:
    planner = cargar_precios(config)["planner"]

    # 10 000 × 4 / 1M + 2 000 × 20 / 1M = 0.04 + 0.04
    assert planner.costo(10_000, 2_000) == pytest.approx(0.08)
    assert planner.costo(0, 0) == 0.0


def test_tokens_negativos(config: Path) -> None:
    with pytest.raises(ValueError):
        cargar_precios(config)["planner"].costo(-1, 0)


def test_falta_un_agente(tmp_path: Path) -> None:
    ruta = tmp_path / "config.toml"
    ruta.write_text(CONFIG.split("[agentes.reviewer]")[0], encoding="utf-8")

    with pytest.raises(ConfiguracionInvalida, match="reviewer"):
        cargar_precios(ruta)


def test_falta_un_precio(tmp_path: Path) -> None:
    ruta = tmp_path / "config.toml"
    ruta.write_text(CONFIG.replace("precio_salida_usd_m = 0.50", ""), encoding="utf-8")

    with pytest.raises(ConfiguracionInvalida, match="precio_salida_usd_m"):
        cargar_precios(ruta)


# --- Tracker ---------------------------------------------------------------------


def test_tracker_calcula_el_costo_con_el_precio_del_agente(config: Path) -> None:
    tracker = TokenTracker(cargar_precios(config))

    registro = tracker.registrar(
        "reviewer", "rev-x", 1_000_000, 1_000_000, costo_usd=99.0
    )

    assert registro.costo_usd == pytest.approx(0.60)  # se ignora el costo recibido


def test_tracker_sin_precios_usa_el_costo_recibido() -> None:
    tracker = TokenTracker()

    assert tracker.registrar("generator", "x", 10, 5, costo_usd=0.25).costo_usd == 0.25


def test_contexto_de_funcion_e_intento() -> None:
    tracker = TokenTracker()

    tracker.fijar_contexto("duplicar", 2)
    implicito = tracker.registrar("generator", "x", 1, 1)
    explicito = tracker.registrar("reviewer", "x", 1, 1, funcion="otra", intento=1)

    assert (implicito.funcion, implicito.intento) == ("duplicar", 2)
    assert (explicito.funcion, explicito.intento) == ("otra", 1)


def test_totales_y_tokens_por_funcion(config: Path) -> None:
    tracker = TokenTracker(cargar_precios(config))
    tracker.registrar("planner", "p", 100, 10)
    tracker.registrar("generator", "g", 50, 20, funcion="duplicar", intento=1)
    tracker.registrar("generator", "g", 50, 20, funcion="duplicar", intento=2)

    totales = tracker.totales_por_agente()

    assert totales["generator"]["llamadas"] == 2
    assert totales["generator"]["prompt_tokens"] == 100
    assert tracker.tokens_de_funcion("duplicar") == {
        "generator": {"prompt_tokens": 100, "completion_tokens": 40}
    }
