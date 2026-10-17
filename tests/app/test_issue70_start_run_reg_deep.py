"""#70: `start_run` trata `reg_deep` como regresión (sin IA)."""

from __future__ import annotations

from qagent.storage.registro import (
    PERFIL_REGRESION_PROFUNDA,
    PERFILES_CON_MUTACION,
    PERFILES_REGRESION,
)


def test_reg_deep_es_regresion_y_aplica_mutacion() -> None:
    assert PERFIL_REGRESION_PROFUNDA == "reg_deep"
    assert PERFILES_REGRESION == {"reg", "reg_deep"}
    assert PERFILES_CON_MUTACION == {"deep", "reg_deep"}


def test_start_run_usa_los_perfiles_de_regresion() -> None:
    from pathlib import Path

    fuente = (
        Path(__file__).resolve().parents[2] / "src" / "qagent" / "app" / "desktop.py"
    ).read_text(encoding="utf-8")
    assert "es_regresion = profile in PERFILES_REGRESION" in fuente
