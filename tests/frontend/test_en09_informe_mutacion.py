"""EN-09: Resultados muestra la fortaleza de las pruebas y los mutantes sobrevivientes.

El informe dejó de ser una pantalla; su evidencia de auditoría vive en el detalle de Resultados.
"""

from __future__ import annotations

from pathlib import Path

RESULTADOS_JS = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "qagent"
    / "frontend"
    / "componentes"
    / "ejecucion"
    / "ejecucion.js"
).read_text(encoding="utf-8")


def evidencia_js() -> str:
    return RESULTADOS_JS[RESULTADOS_JS.index("function evidenciaAuditoria") :]


def test_la_evidencia_lista_los_sobrevivientes() -> None:
    assert "(f.mutacion && f.mutacion.sobrevivientes) || []" in RESULTADOS_JS
    js = evidencia_js()
    assert "escHtml(s.cambio || s.mutante || '')" in js
    assert "Number(s.linea)" in js


def test_la_fortaleza_sale_del_backend_sin_metas_locales() -> None:
    assert "Number(f.mutation_score)" in RESULTADOS_JS
    assert "META." not in evidencia_js()
