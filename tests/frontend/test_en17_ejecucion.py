"""EN-17: los casos ejecutados en el sandbox se muestran en Resultados, sin navegador.

Antes vivían en la pestaña «Ejecución y casos» del informe; ahora están en la evidencia
de auditoría del detalle de cada función o endpoint.
"""

from __future__ import annotations

from pathlib import Path

RESULTADOS = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "qagent"
    / "frontend"
    / "componentes"
    / "ejecucion"
    / "ejecucion.js"
).read_text(encoding="utf-8")


def test_resultados_muestran_los_casos_ejecutados() -> None:
    assert "function ejecucionDeIntentos" in RESULTADOS
    assert "function casoEjecutadoHtml" in RESULTADOS
    assert "Casos ejecutados" in RESULTADOS
    assert "lineas_sin_cubrir" in RESULTADOS


def test_el_caso_que_falla_muestra_donde_y_que() -> None:
    for pieza in (
        "Esperado",
        "Obtenido",
        "Pila de llamadas",
        "Traza completa de pytest",
    ):
        assert pieza in RESULTADOS


def test_el_texto_del_usuario_siempre_se_escapa() -> None:
    """Los casos vienen de la salida de pytest: nunca se insertan sin escapar."""
    bloque = RESULTADOS[
        RESULTADOS.index("function casoEjecutadoHtml") : RESULTADOS.index(
            "function evidenciaAuditoria"
        )
    ]

    assert "escHtml(String(c.mensaje)" in bloque
    assert "escHtml(c.traza)" in bloque and "escHtml(c.codigo)" in bloque
    assert "${c.traza}" not in bloque and "${c.codigo}" not in bloque
