"""#197: Explorar muestra las pruebas recomendadas y el usuario decide si las aplica."""

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


def test_explorar_tiene_la_tarjeta_de_recomendacion() -> None:
    js = _js()

    for id_ in ("expReco", "expRecoLista", "expRecoProx", "expRecoAplicar"):
        assert f'id="{id_}"' in js
    # Empieza oculta: solo aparece cuando el backend manda una recomendación.
    assert 'class="np-tarjeta exp-reco hide"' in js


def test_la_recomendacion_llega_del_analisis_y_no_se_aplica_sola() -> None:
    carga = _funcion_js("cargarDatosVistaPrevia")

    assert "res.recomendacion" in carga
    assert "renderRecomendacion()" in carga
    assert "aplicarRecomendacion" not in carga


def test_aplicar_solo_precarga_preparar_y_nunca_inicia_la_corrida() -> None:
    cuerpo = _funcion_js("aplicarRecomendacion")

    assert "eleccionPruebas" in cuerpo
    assert "unitarias: tipos.has('funcion')" in cuerpo
    assert "endpoints: tipos.has('endpoint')" in cuerpo
    assert "tipos.has('mutacion') ? 'fondo'" in cuerpo
    for prohibido in ("start_run", "iniciarCorrida", "go('monitor')"):
        assert prohibido not in cuerpo


def test_el_texto_del_proyecto_se_escapa() -> None:
    cuerpo = _funcion_js("renderRecomendacion")

    assert "escHtml(r.motivo)" in cuerpo
    assert "escHtml(p.motivo)" in cuerpo
    assert "próximamente" in cuerpo


def test_los_estilos_usan_solo_tokens() -> None:
    css = (VISTA / "vista-previa.css").read_text(encoding="utf-8")
    bloque = css[css.index("/* Pruebas recomendadas") : css.index("/* Rejilla")]

    assert "var(--" in bloque
    assert "#" not in bloque
    assert "rgb" not in bloque
