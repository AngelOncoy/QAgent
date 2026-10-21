"""Pruebas de la interfaz de Historial: explicación de denominadores y clasificación de pruebas guardadas."""

from pathlib import Path

HISTORIAL_JS = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "qagent"
    / "frontend"
    / "componentes"
    / "historial"
    / "historial.js"
).read_text(encoding="utf-8")

HISTORIAL_CSS = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "qagent"
    / "frontend"
    / "componentes"
    / "historial"
    / "historial.css"
).read_text(encoding="utf-8")


def test_columna_pasan_explica_su_denominador() -> None:
    """La columna Pasan explica su denominador en la celda y tabla."""
    assert "<th>Pasan</th>" in HISTORIAL_JS
    assert "hst-pasan" in HISTORIAL_JS
    assert "procesados" in HISTORIAL_JS
    assert "pend. de" in HISTORIAL_JS
    assert "no procesados por detención" in HISTORIAL_JS


def test_identificacion_de_corridas_parciales() -> None:
    """Las corridas parciales se distinguen con terminación y aviso explícito."""
    assert "hst-aviso-parcial" in HISTORIAL_JS
    assert "Corrida parcial" in HISTORIAL_JS
    assert "no procesados por detención" in HISTORIAL_JS
    assert "h.es_parcial" in HISTORIAL_JS
    assert "h.terminacion_nombre" in HISTORIAL_JS


def test_clasificacion_de_pruebas_guardadas() -> None:
    """El apartado de pruebas guardadas clasifica planes, archivos, aceptadas, regresión y defectos."""
    assert "hst-clasif-grid" in HISTORIAL_JS
    assert "Planes de prueba" in HISTORIAL_JS
    assert "Archivos de prueba" in HISTORIAL_JS
    assert "Pruebas aceptadas" in HISTORIAL_JS
    assert "Para regresión" in HISTORIAL_JS
    assert "defecto detectado" in HISTORIAL_JS or "defectos detectados" in HISTORIAL_JS
    assert "descargarSpecsReal" in HISTORIAL_JS
    assert "descargarPruebasReal" in HISTORIAL_JS


def test_estilos_historial_usan_tokens() -> None:
    """Los nuevos estilos de historial usan exclusivamente tokens de css/tokens.css."""
    assert ".hst-pasan" in HISTORIAL_CSS
    assert ".hst-clasif-grid" in HISTORIAL_CSS
    assert ".hst-aviso-parcial" in HISTORIAL_CSS
    # No contiene colores hexadecimales (#...) fuera de tokens
    lineas_con_hex = [
        linea
        for linea in HISTORIAL_CSS.splitlines()
        if "#" in linea
        and not linea.strip().startswith("/*")
        and not linea.strip().startswith("#s-history")
    ]
    assert len(lineas_con_hex) == 0, (
        f"Se encontraron selectores o colores no permitidos: {lineas_con_hex}"
    )
