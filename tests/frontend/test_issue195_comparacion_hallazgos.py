"""Issue #195: la UI muestra comparaciones persistidas y navegables."""

from pathlib import Path

RAIZ = Path(__file__).parents[2] / "src" / "qagent" / "frontend" / "componentes"


def _leer(ruta: str) -> str:
    return (RAIZ / ruta).read_text(encoding="utf-8")


def test_resultados_muestra_resumen_estados_y_corrida_original() -> None:
    js = _leer("ejecucion/ejecucion.js")
    assert "Comparación con la corrida original" in js
    assert "Resultados originales" in js
    assert "Errores anteriores" in js
    assert "Errores actuales" in js
    assert "Siguen fallando" in js
    assert "Regresiones" in js
    assert "No comparables" in js
    assert "cargarEjecucionReal('${escHtml(comparacion.run_origen_id)}')" in js


def test_historial_usa_comparacion_persistida_para_verify_fix() -> None:
    js = _leer("historial/historial.js")
    assert "actual.perfil === 'verify_fix'" in js
    assert "renderComparacionVerificacionHistorial" in js
    assert "Abrir corrida original" in js
    assert "corrida.comparacion" in js


def test_estilos_son_responsivos_y_no_introducen_colores_literales() -> None:
    for ruta in ("ejecucion/ejecucion.css", "historial/historial.css"):
        css = _leer(ruta)
        bloque = css[css.find("#195") :] if "#195" in css else css
        assert "var(--" in bloque
        assert "@media" in css
        assert "#fff" not in bloque.lower()
