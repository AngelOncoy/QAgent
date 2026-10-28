"""#70: la casilla Profundizar también aparece al repetir pruebas guardadas."""

from __future__ import annotations

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "src" / "qagent" / "frontend"


def leer(ruta: str) -> str:
    return (FRONTEND / ruta).read_text(encoding="utf-8")


def cuerpo_de(js: str, inicio: str, fin: str) -> str:
    return js[js.index(inicio) : js.index(fin, js.index(inicio))]


def config() -> str:
    return leer("componentes/config-pruebas/config-pruebas.js")


def test_repetir_se_describe_sin_ia_y_fondo_como_mas_largo() -> None:
    js = config()
    assert "Volver a correr las guardadas" in js
    assert "Solo se vuelven a correr pruebas guardadas: no se usa IA" in js
    assert "Análisis a fondo de críticas" in js
    assert (
        "if (modo === 'repetir') return profundizarRepetir && repetibles > 0 ? 'reg_deep' : 'reg';"
        in js
    )
    assert "if (modo === 'fondo') return prioritarias > 0 ? 'deep' : 'std';" in js


def test_el_historial_trata_reg_deep_como_sin_ia() -> None:
    historial = leer("componentes/historial/historial.js")

    assert "h.perfil === 'reg' || h.perfil === 'reg_deep'" in historial
