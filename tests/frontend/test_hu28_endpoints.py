"""Regresiones de HU-28 para endpoints en las cuatro pantallas."""

from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
FRONTEND = RAIZ / "frontend"


def leer(ruta: str) -> str:
    return (FRONTEND / ruta).read_text(encoding="utf-8")


def test_vista_previa_renderiza_metodo_ruta_y_manejador_escapados() -> None:
    js = leer("componentes/vista-previa/vista-previa.js")

    assert "m.endpoints" in js
    assert "escHtml(e.metodo)" in js
    assert "escHtml(e.ruta)" in js
    assert "escHtml(e.manejador)" in js
    assert "resumen.total_endpoints" in js


def test_monitor_usa_identidad_y_porcentaje_del_backend() -> None:
    js = leer("componentes/monitor/monitor.js")
    real = js[
        js.index("function monitorEventoReal") : js.index("function monitorFinReal")
    ]

    assert "d.identificador" in real
    assert "d.tipo_objetivo==='endpoint'" in real
    assert "Number(d.porcentaje)" in real
    assert "d.hechos / d.total" not in real
    assert "escHtml(lugar)" in real and "escHtml(d.t || '')" in real


def test_ejecucion_filtra_por_tipo_con_conteos_del_backend() -> None:
    js = leer("componentes/ejecucion/ejecucion.js")
    real = js[js.index("let ejecucionReal") :]

    assert "v.filtros_tipo.map" in real
    assert "p.tipo===filterType" in real
    assert "v.total_objetivos" in real
    assert "p.tipo==='endpoint'?escHtml(p.identificador)" in real


def test_reporte_filtra_y_presenta_contrato_http_y_cinco_controles() -> None:
    js = leer("componentes/informe/informe.js")
    real = js[js.index("let reporteReal") :]

    assert "v.filtros_tipo.map" in real
    assert "f.tipo===rTypeFilter" in real
    assert "f.contrato_http.casos.map" in real
    assert "jsonHL(c.peticion)" in real
    assert "jsonHL(c.respuesta_esperada)" in real
    assert "f.controles.map" in real
    assert "5 controles" in real


def test_textos_no_confiables_pasan_por_escape_en_el_flujo_real() -> None:
    ejecucion = leer("componentes/ejecucion/ejecucion.js")
    informe = leer("componentes/informe/informe.js")
    monitor = leer("componentes/monitor/monitor.js")

    assert "escHtml(p.identificador)" in ejecucion
    for expresion in (
        "escHtml(f.identificador)",
        "escHtml(f.manejador)",
        "escHtml(c.id",
        "escHtml(c.descripcion)",
        "escHtml(c.origen",
    ):
        assert expresion in informe
    assert "escHtml(lugar)" in monitor
    assert "escHtml(d.t || '')" in monitor


def test_estados_vacios_no_inventan_resultados() -> None:
    ejecucion = leer("componentes/ejecucion/ejecucion.js")
    informe = leer("componentes/informe/informe.js")

    mensaje = "No hay resultados para los filtros seleccionados."
    assert mensaje in ejecucion
    assert mensaje in informe
