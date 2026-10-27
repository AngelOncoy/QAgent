"""#148: el Monitor muestra el entorno aislado aparte de la etapa del análisis."""

from __future__ import annotations

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "src" / "qagent" / "frontend"


def _texto(componente: str) -> str:
    return (FRONTEND / "componentes" / componente).read_text(encoding="utf-8")


def test_el_monitor_recibe_el_estado_del_entorno() -> None:
    monitor = _texto("monitor/monitor.js")
    bloque = monitor.split("function monitorEventoReal", 1)[1].split(
        "function monitorFinReal", 1
    )[0]

    assert "entorno: d.entorno" in bloque


def test_el_aviso_del_entorno_no_se_oculta_con_el_analisis() -> None:
    monitor = _texto("monitor/monitor.js")
    paso = monitor.split("function registrarPaso", 1)[1].split("function ", 1)[0]

    # Con el estado informado, solo `listo`, `fallo` o `cancelado` ocultan el aviso;
    # la regla anterior (ocultarlo con la primera etapa) queda solo sin ese dato.
    assert "PRG.entornoInformado = true" in paso
    assert "entorno === 'preparando' || entorno === 'avance'" in paso
    assert "else if (!PRG.entornoInformado)" in paso


def test_el_aviso_explica_que_el_analisis_sigue_mientras_tanto() -> None:
    monitor = _texto("monitor/monitor.js")
    estilos = _texto("monitor/monitor.css")

    assert 'id="prgEntornoParalelo"' in monitor
    assert "$('prgEntornoParalelo').classList.toggle('hide', !PRG.etapa)" in monitor
    assert ".prg-entorno-paralelo{" in estilos
