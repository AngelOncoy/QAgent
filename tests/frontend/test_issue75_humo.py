"""#75: la ejecución y el informe muestran que la corrida fue Humo."""

from __future__ import annotations

from pathlib import Path

COMPONENTES = (
    Path(__file__).resolve().parents[2] / "src" / "qagent" / "frontend" / "componentes"
)
EJECUCION = (COMPONENTES / "ejecucion" / "ejecucion.js").read_text(encoding="utf-8")
INFORME = (COMPONENTES / "informe" / "informe.js").read_text(encoding="utf-8")


def test_la_ejecucion_destaca_el_pass_rate_y_no_exige_ramas_en_humo() -> None:
    assert "PASS RATE${v.es_humo ? ' · MÉTRICA PRINCIPAL (HUMO)' : ''}" in EJECUCION
    assert "cv.exige_ramas === false ? ' · no se exigen en Humo' : ''" in EJECUCION


def test_el_informe_explica_que_la_corrida_fue_humo() -> None:
    assert "v.es_humo ?" in INFORME
    assert "El Pass Rate es la métrica principal" in INFORME
    assert "cv.exige_ramas === false ? ' · ramas no exigidas en Humo' : ''" in INFORME
