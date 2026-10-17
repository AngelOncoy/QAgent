"""#70: el informe y la ejecución marcan la prueba repetida y explican el motivo."""

from __future__ import annotations

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "src" / "qagent" / "frontend"


def leer(ruta: str) -> str:
    return (FRONTEND / ruta).read_text(encoding="utf-8")


def test_el_informe_marca_la_prueba_repetida_y_el_motivo() -> None:
    js = leer("componentes/informe/informe.js")

    assert (
        '${f.reutilizada?\'<span class="rkind" title="La prueba aprobada guardada '
        "se volvió a ejecutar en el sandbox, sin IA\">♻ Prueba repetida</span>':''}"
        in js
    )
    assert (
        "f.estado==='requiere_corrida_nueva' && f.texto_motivo_regresion "
        "? `${e.txt} · ${f.texto_motivo_regresion}`" in js
    )


def test_la_ejecucion_marca_la_prueba_repetida_y_el_motivo() -> None:
    js = leer("componentes/ejecucion/ejecucion.js")

    assert (
        '${p.reutilizada?\'<span class="bdg b-grey" title="La prueba aprobada '
        'guardada se volvió a ejecutar en el sandbox, sin IA">♻ Prueba repetida'
        "</span>':''}" in js
    )
    assert (
        "p.estado==='requiere_corrida_nueva' && p.texto_motivo_regresion "
        "? `${e.txt} · ${p.texto_motivo_regresion}`" in js
    )


def test_el_motivo_se_escapa_antes_de_mostrarse() -> None:
    """La etiqueta con el motivo pasa por escHtml en las dos pantallas."""
    assert "${escHtml(etiqueta)}</span>" in leer("componentes/informe/informe.js")
    assert "${escHtml(etiqueta)}</span>" in leer("componentes/ejecucion/ejecucion.js")
