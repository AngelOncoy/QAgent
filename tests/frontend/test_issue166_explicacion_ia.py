"""#166: Resultados avisa «Explicación generada por IA» cuando `origen` es `ia`."""

from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
EJECUCION = RAIZ / "src" / "qagent" / "frontend" / "componentes" / "ejecucion"


def _funcion_js(nombre: str) -> str:
    js = (EJECUCION / "ejecucion.js").read_text(encoding="utf-8")
    inicio = js.index(f"function {nombre}(")
    return js[inicio : js.index("\n}\n", inicio)]


def test_la_explicacion_avisa_si_la_genero_la_ia() -> None:
    cuerpo = _funcion_js("explicacionSimple")

    assert "s.origen === 'ia'" in cuerpo
    assert "Explicación generada por IA" in cuerpo
    # El modelo viene del archivo de la corrida: se escapa como el resto del texto.
    assert "escHtml(s.modelo)" in cuerpo


def test_la_etiqueta_usa_solo_tokens() -> None:
    css = (EJECUCION / "ejecucion.css").read_text(encoding="utf-8")
    regla = css[css.index(".bnj-origen-ia{") :].split("}", 1)[0]

    assert "color:var(--" in regla
    assert "#" not in regla
