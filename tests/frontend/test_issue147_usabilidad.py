"""Regresiones de usabilidad corregidas en la issue 147."""

from pathlib import Path

BASE = Path(__file__).parents[2] / "src" / "qagent" / "frontend"


def _leer(ruta: str) -> str:
    return (BASE / ruta).read_text(encoding="utf-8")


def test_selector_declara_y_respeta_el_tipo_completo() -> None:
    js = _leer("componentes/vista-previa/vista-previa.js")
    assert "Seleccionar todas las funciones" in js
    assert "Seleccionar todos los endpoints" in js
    assert "filasFunciones().forEach" in js
    assert "filasEndpoints().filter(r => endpointElegible(r.e))" in js
    assert "filter(funcionVisible).forEach" not in js


def test_explorar_recupera_y_guarda_la_seleccion_por_proyecto() -> None:
    js = _leer("componentes/vista-previa/vista-previa.js")
    assert "await restaurarSeleccionExplorar()" in js
    assert "api.obtener_seleccion_objetivos(projectPath)" in js
    assert "api.guardar_seleccion_objetivos(projectPath" in js
    assert "incluido:!!f.inc" in js
    assert "incluido:!!e.inc" in js


def test_preparar_conserva_un_estado_visible_sin_colapsar_el_diseno() -> None:
    js = _leer("componentes/config-pruebas/config-pruebas.js")
    assert 'id="prepBloqueo" aria-live="polite"' in js
    assert "classList.toggle('hide', !bloqueado)" not in js
    assert "La selección de objetivos se conserva en este proyecto" in js


def test_monitor_usa_actividad_indeterminada_y_etapas_reales() -> None:
    js = _leer("componentes/monitor/monitor.js")
    css = _leer("componentes/monitor/monitor.css")
    assert "prg-indeterminada" in js and "prg-indeterminada" in css
    assert "aria-busy" in js
    assert "Guardando la imagen Docker" in js
    assert "Instalando dependencias" in js
    assert "indeterminado ? '' : pct + '%'" in js
    assert "!indeterminado && (PRG.total || PRG.fin)" in js


def test_detalle_pytest_es_multilinea_y_escapa_el_contenido() -> None:
    js = _leer("componentes/ejecucion/ejecucion.js")
    css = _leer("componentes/ejecucion/ejecucion.css")
    assert (
        '<pre class="np-log bnj-salida-pytest">${escHtml(e.traza || e.salida)}</pre>'
        in js
    )
    assert ".bnj-salida-pytest{white-space:pre-wrap;overflow-wrap:anywhere" in css


def test_historial_distingue_omitidos_vacio_y_datos_antiguos() -> None:
    js = _leer("componentes/historial/historial.js")
    assert "${sel} sin probar" in js
    assert "Sin objetivos seleccionados" in js
    assert "Información no disponible" in js
    assert "proc === 0 && omit === sel" in js


def test_aviso_inicial_no_agrega_prefijo_de_python() -> None:
    js = _leer("js/puente-python.js")
    assert "toast(escHtml(event.data.message));" in js
    assert "Python: ${escHtml" not in js
