"""#244: la pantalla Configuración tiene una fila para el Recomendador y la Vista previa
lleva a ella."""

from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
COMPONENTES = RAIZ / "src" / "qagent" / "frontend" / "componentes"


def _leer(ruta: str) -> str:
    return (COMPONENTES / ruta).read_text(encoding="utf-8")


def _funcion_js(texto: str, nombre: str) -> str:
    inicio = texto.index(f"function {nombre}(")
    return texto[inicio : texto.index("\n}\n", inicio)]


def test_configuracion_tiene_la_fila_del_recomendador() -> None:
    js = _leer("configuracion/configuracion.js")

    assert "recomendador: {t:'Recomendando'" in js
    assert "opcional" in _funcion_js(js, "filaRol")
    assert "Reglas (sin IA)" in js


def test_sin_clave_el_recomendador_no_es_un_problema() -> None:
    cuerpo = _funcion_js(_leer("configuracion/configuracion.js"), "filaRol")

    # Una etapa opcional sin clave muestra «Reglas (sin IA)», no «Falta la clave».
    assert cuerpo.index("r.opcional") < cuerpo.index("Falta la clave")


def test_la_demostracion_incluye_al_recomendador() -> None:
    js = _leer("configuracion/configuracion.js")

    assert "['planner','generator','reviewer','recomendador']" in js


def test_el_modal_usa_el_nombre_de_la_etapa() -> None:
    modal = _leer("configuracion/modal-api.js")

    assert "ETAPA[agente]" in modal  # el título sale de la tabla de etapas


def test_la_vista_previa_lleva_a_configuracion() -> None:
    js = _leer("vista-previa/vista-previa.js")

    assert 'id="expRecoConfigurar"' in js
    assert "Configurar IA" in js
    assert "onclick=\"go('config')\"" in js


def test_el_boton_no_aplica_ni_inicia_nada() -> None:
    js = _leer("vista-previa/vista-previa.js")
    inicio = js.index('id="expRecoConfigurar"')
    boton = js[inicio : js.index("</button>", inicio)]

    for prohibido in ("start_run", "iniciarCorrida", "aplicarRecomendacion"):
        assert prohibido not in boton


def test_los_estilos_nuevos_usan_solo_tokens() -> None:
    css = _leer("vista-previa/vista-previa.css")
    regla = next(
        linea for linea in css.splitlines() if linea.startswith(".exp-reco-acciones")
    )

    assert "#" not in regla.split("{", 1)[1]
    assert "var(--esp-2)" in regla
