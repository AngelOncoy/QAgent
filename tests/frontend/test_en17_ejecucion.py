"""Estructura de la pestaña «Ejecución y casos» del Reporte (EN-17), sin navegador."""

from __future__ import annotations

from pathlib import Path

INFORME = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "qagent"
    / "frontend"
    / "componentes"
    / "informe"
)


def test_el_reporte_tiene_la_pestana_de_ejecucion_y_casos() -> None:
    js = (INFORME / "informe.js").read_text(encoding="utf-8")

    assert "'run','term','4. Ejecución y casos'" in js
    assert "function ejecucionRealHtml" in js
    assert 'id="rentorno"' in js


def test_el_panel_de_fallo_muestra_donde_y_que() -> None:
    js = (INFORME / "informe.js").read_text(encoding="utf-8")

    for pieza in (
        "Esperado",
        "Obtenido",
        "Pila de llamadas",
        "Traza completa de pytest",
    ):
        assert pieza in js


def test_el_texto_del_usuario_siempre_se_escapa() -> None:
    """Los casos vienen de la salida de pytest: nunca se insertan sin escapar."""
    js = (INFORME / "informe.js").read_text(encoding="utf-8")
    bloque = js[
        js.index("function filaFalloHtml") : js.index("function renderReportReal")
    ]

    assert "escHtml(c.mensaje" in bloque or "escHtml(String(c.mensaje" in bloque
    assert "${c.traza}" not in bloque and "${c.codigo}" not in bloque
