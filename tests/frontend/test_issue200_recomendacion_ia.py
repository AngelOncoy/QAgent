"""#200: Explorar indica cuándo la recomendación la generó la IA."""

from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
VISTA = RAIZ / "src" / "qagent" / "frontend" / "componentes" / "vista-previa"


def _js() -> str:
    return (VISTA / "vista-previa.js").read_text(encoding="utf-8")


def _funcion_js(nombre: str) -> str:
    js = _js()
    inicio = js.index(f"function {nombre}(")
    return js[inicio : js.index("\n}\n", inicio)]


def test_la_tarjeta_tiene_el_rotulo_de_ia_oculto_por_defecto() -> None:
    js = _js()

    assert 'id="expRecoIA"' in js
    assert "Recomendación generada por IA" in js
    assert 'class="np-chip exp-reco-ia hide"' in js
    assert 'id="expRecoNota"' in js


def test_el_rotulo_depende_del_origen_que_manda_el_backend() -> None:
    cuerpo = _funcion_js("renderRecomendacion")

    assert "origen === 'ia'" in cuerpo
    assert "$('expRecoIA').classList.toggle('hide', !porIA)" in cuerpo


def test_la_ia_no_cambia_lo_que_hace_aplicar() -> None:
    cuerpo = _funcion_js("aplicarRecomendacion")

    assert "origen" not in cuerpo
    for prohibido in ("start_run", "iniciarCorrida", "go('monitor')"):
        assert prohibido not in cuerpo


def test_el_rotulo_usa_solo_tokens() -> None:
    css = (VISTA / "vista-previa.css").read_text(encoding="utf-8")
    regla = next(
        linea for linea in css.splitlines() if linea.startswith(".exp-reco-ia")
    )

    assert "#" not in regla.split("{", 1)[1]
    assert "var(--accion-suave)" in regla
    assert "var(--enlace)" in regla
