"""HU-06: la marca Profundizar de la vista previa viaja con la selección."""

from __future__ import annotations

from pathlib import Path

VISTA_JS = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "qagent"
    / "frontend"
    / "componentes"
    / "vista-previa"
    / "vista-previa.js"
).read_text(encoding="utf-8")


def seleccion_js() -> str:
    inicio = VISTA_JS.index("function obtenerSeleccionObjetivos")
    return VISTA_JS[inicio : VISTA_JS.index("\n}\n", inicio)]


def test_la_seleccion_envia_las_funciones_marcadas() -> None:
    assert "criticas: (m.fns || []).filter(f => f.inc && f.crit).map(f => f.n)" in (
        seleccion_js()
    )


def test_solo_se_envian_marcas_de_funciones_incluidas() -> None:
    """El backend rechaza marcas de funciones que no están en la selección."""
    assert "f.inc && f.crit" in seleccion_js()


def test_la_marca_explica_que_depende_de_la_configuracion() -> None:
    assert "Se aplica si activas Profundizar en la configuración de pruebas." in (
        VISTA_JS
    )
