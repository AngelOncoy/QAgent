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


def test_repetir_ofrece_profundizar_con_caja_blanca_y_sin_ia() -> None:
    repetir = cuerpo_de(config(), "if (modo === 'repetir') {", "return;\n  }")

    assert 'onchange="elegirPruebas({profundizarRepetir:this.checked})"' in repetir
    assert "caja-${deep.tipo_caja}" in repetir
    assert "Tarda más, pero no usa IA" in repetir
    assert (
        'title="Ninguna función marcada tiene una prueba guardada vigente"' in repetir
    )


def test_solo_cuentan_las_prioritarias_con_prueba_repetible() -> None:
    js = config()
    cuerpo = cuerpo_de(js, "function prioritariasRepetibles", "\n}\n")

    assert "f.inc && f.crit" in cuerpo
    assert "PRUEBAS_REPETIBLES===null || PRUEBAS_REPETIBLES.has(clave)" in cuerpo
    assert "const apagadaRep = repetibles === 0;" in js


def test_la_vista_previa_pide_las_pruebas_repetibles() -> None:
    vista = leer("componentes/vista-previa/vista-previa.js")
    estado = leer("js/estado.js")

    assert "PRUEBAS_REPETIBLES = await pruebasRepetibles(ruta);" in vista
    assert "window.pywebview.api.pruebas_repetibles(ruta)" in vista
    assert "let PRUEBAS_REPETIBLES = null;" in estado


def test_reg_deep_se_estima_como_regresion_y_se_nombra() -> None:
    js = config()

    assert "estFor(profile==='reg_deep' ? 'reg' : profile)" in js
    assert "reg_deep:'Repetir pruebas guardadas + profundizar'" in js
    assert "profile==='reg_deep' ? `mutmut se aplicará" in js


def test_el_historial_trata_reg_deep_como_sin_ia() -> None:
    historial = leer("componentes/historial/historial.js")

    assert "h.perfil === 'reg' || h.perfil === 'reg_deep'" in historial
