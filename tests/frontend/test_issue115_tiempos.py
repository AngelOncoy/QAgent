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


def test_monitor_combina_tokens_alertas_y_tiempos_en_el_mismo_evento() -> None:
    monitor = _texto("monitor/monitor.js")
    bloque = monitor.split("function monitorEventoReal", 1)[1].split(
        "function monitorFinReal", 1
    )[0]

    assert "d.tokens_acumulados" in bloque
    assert "d.limite_tokens" in bloque
    assert "d.alerta_presupuesto" in bloque
    assert "transcurrido_s" in bloque
    assert "duracion_objetivo_s" in bloque
    assert "Number.isFinite" in bloque

    fin = monitor.split("function monitorFinReal", 1)[1]
    assert "runDone = true" in fin
    assert "clearInterval(agoTimer)" in fin
    assert "r.duracion_s" in fin


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
