"""#75: Resultados muestra que la corrida fue Humo y que en ella no se exigen ramas."""

from __future__ import annotations

from pathlib import Path

COMPONENTES = (
    Path(__file__).resolve().parents[2] / "src" / "qagent" / "frontend" / "componentes"
)
RESULTADOS = (COMPONENTES / "ejecucion" / "ejecucion.js").read_text(encoding="utf-8")


def test_resultados_explican_que_la_corrida_fue_humo() -> None:
    assert "v && v.es_humo" in RESULTADOS
    assert "Corrida Humo: lo principal es cuántas pruebas pasan" in RESULTADOS


def test_en_humo_no_se_exigen_ramas() -> None:
    assert (
        "k.cobertura.exige_ramas === false ? 'Ramas no exigidas en Humo'" in RESULTADOS
    )
