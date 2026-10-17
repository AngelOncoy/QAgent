"""EN-09: el informe real muestra el Mutation Score y los mutantes sobrevivientes."""

from __future__ import annotations

from pathlib import Path

INFORME_JS = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "qagent"
    / "frontend"
    / "componentes"
    / "informe"
    / "informe.js"
).read_text(encoding="utf-8")


def real_js() -> str:
    return INFORME_JS[INFORME_JS.index("let reporteReal") :]


def test_el_checklist_lista_los_sobrevivientes() -> None:
    js = real_js()
    assert "function sobrevivientesHtml(f)" in js
    assert "+ sobrevivientesHtml(f);" in js
    assert "escHtml(s.cambio || s.mutante)" in js
    assert "Number(s.linea)" in js


def test_el_color_del_score_sale_del_control_del_backend() -> None:
    js = real_js()
    assert "function colorMutacion(f)" in js
    assert "c.clave === 'mutation'" in js
    assert "META." not in js[js.index("function colorMutacion") :]
