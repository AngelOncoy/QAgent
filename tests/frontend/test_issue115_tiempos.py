"""#115: la interfaz muestra los tiempos medidos por el backend."""

from __future__ import annotations

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "src" / "qagent" / "frontend"


def _texto(componente: str) -> str:
    return (FRONTEND / "componentes" / componente).read_text(encoding="utf-8")


def test_monitor_reancla_el_reloj_con_el_tiempo_del_backend() -> None:
    monitor = _texto("monitor/monitor.js")

    assert "transcurrido_s" in monitor
    assert "PRG.inicio = Date.now() - Math.max(0, transcurrido_s) * 1000" in monitor
    assert "duracion_objetivo_s" in monitor
    assert "duracionTexto" in monitor


def test_ejecucion_usa_el_total_medido_y_el_desglose() -> None:
    ejecucion = _texto("ejecucion/ejecucion.js")

    assert "v.duracion_total_s" in ejecucion
    assert "duracion_generacion_s" in ejecucion
    assert "duracion_sandbox_s" in ejecucion
    assert "duracion_pytest_s" in ejecucion
    assert "Duración total medida" in ejecucion


def test_historial_tiene_columna_de_duracion() -> None:
    historial = _texto("historial/historial.js")

    assert "<th>Duración</th>" in historial
    assert "duracionCorta(h.duracion_s)" in historial
    assert "Corrida anterior a la medición de duración" in historial
