"""Regresiones de HU-28 para endpoints en las cuatro pantallas."""

from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
FRONTEND = RAIZ / "src" / "qagent" / "frontend"


def leer(ruta: str) -> str:
    return (FRONTEND / ruta).read_text(encoding="utf-8")


def test_vista_previa_renderiza_metodo_ruta_y_manejador_escapados() -> None:
    js = leer("componentes/vista-previa/vista-previa.js")

    assert "m.endpoints" in js
    assert "escHtml(e.metodo)" in js
    assert "escHtml(e.ruta)" in js
    assert "escHtml(e.manejador)" in js
    assert "resumen.total_endpoints" in js


def test_monitor_usa_identidad_y_avance_del_backend() -> None:
    js = leer("componentes/monitor/monitor.js")
    real = js[
        js.index("function monitorEventoReal") : js.index("function monitorFinReal")
    ]

    assert "d.identificador" in real
    assert "tipo_objetivo:d.tipo_objetivo" in real
    assert "Number(d.hechos)" in real and "Number(d.total)" in real
    assert "d.hechos / d.total" not in real
    # Lo que viene del proyecto o de la IA se escapa al pintar.
    pintado = js[js.index("function pintarProgreso") :]
    assert "escHtml(a.fn)" in pintado and "escHtml(textoPlano(p.t || ''))" in pintado


def test_resultados_filtra_por_tipo_y_usa_la_identidad_del_backend() -> None:
    js = leer("componentes/ejecucion/ejecucion.js")

    assert "tipo: p.tipo" in js and "nombre: p.identificador" in js
    assert "(filterType === 'todos' || e.tipo === filterType)" in js
    assert "escHtml(e.nombre)" in js


def test_resultados_presentan_contrato_http_y_controles() -> None:
    # El informe dejó de ser una pantalla: su evidencia está en el detalle de Resultados.
    js = leer("componentes/ejecucion/ejecucion.js")

    assert "(f.contrato_http && f.contrato_http.casos)" in js
    assert "JSON.stringify(c.peticion)" in js
    assert "JSON.stringify(c.respuesta_esperada)" in js
    assert "e.controles.map" in js
    assert "Controles de integridad" in js


def test_textos_no_confiables_pasan_por_escape_en_el_flujo_real() -> None:
    resultados = leer("componentes/ejecucion/ejecucion.js")

    for expresion in (
        "escHtml(e.nombre)",
        "escHtml(e.firma)",
        "escHtml(c.descripcion || c.id || 'Caso')",
        "escHtml(JSON.stringify(c.peticion))",
        "escHtml(c.nombre || '')",
    ):
        assert expresion in resultados


def test_estados_vacios_no_inventan_resultados() -> None:
    resultados = leer("componentes/ejecucion/ejecucion.js")

    assert "No hay resultados en esta bandeja." in resultados
    assert "Nada coincide con la búsqueda." in resultados
