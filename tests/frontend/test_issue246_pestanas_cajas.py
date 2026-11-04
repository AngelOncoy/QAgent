"""#246: Preparar agrupa los tipos de prueba en pestañas por tipo de caja.

Es solo una vista: cambiar de pestaña oculta o muestra tarjetas y nunca toca lo elegido.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
PREP = RAIZ / "src" / "qagent" / "frontend" / "componentes" / "config-pruebas"


def _js() -> str:
    return (PREP / "config-pruebas.js").read_text(encoding="utf-8")


def _funcion_js(nombre: str) -> str:
    js = _js()
    inicio = js.index(f"function {nombre}(")
    return js[inicio : js.index("\n}\n", inicio)]


def _etiqueta_con(js: str, fragmento: str) -> str:
    """La etiqueta HTML de apertura que contiene `fragmento`."""
    centro = js.index(fragmento)
    inicio = js.rfind("<", 0, centro)
    return js[inicio : js.index(">", centro) + 1]


def test_hay_cuatro_pestanas_en_orden() -> None:
    js = _js()
    bloque = js[
        js.index("const CAJAS = [") : js.index("];", js.index("const CAJAS = ["))
    ]

    claves = re.findall(r"\{k:'(\w+)',\s*t:'([^']+)'", bloque)
    assert claves == [
        ("todas", "Todas"),
        ("negra", "Caja negra"),
        ("blanca", "Caja blanca"),
        ("gris", "Caja gris"),
    ]


def test_las_pestanas_siguen_el_patron_de_tablist() -> None:
    js = _js()

    assert 'role="tablist"' in js and 'aria-label="Tipo de caja de las pruebas"' in js
    assert 'role="tabpanel"' in js and 'id="prepContenidoCajas"' in js
    render = _funcion_js("renderCajas")
    for atributo in (
        'role="tab"',
        "aria-selected",
        "aria-controls",
        "tabindex",
        "aria-label",
    ):
        assert atributo in render
    assert "aria-labelledby" in render  # el panel se nombra con la pestaña activa
    # Mismas clases que las pestañas de Explorar (Funciones / Endpoints).
    assert 'class="obj-switch"' in js and "obj-tab" in render


def test_el_teclado_recorre_las_pestanas() -> None:
    cuerpo = _funcion_js("teclasCajas")

    for tecla in ("ArrowRight", "ArrowLeft", "Home", "End"):
        assert tecla in cuerpo
    assert 'onkeydown="teclasCajas(event)"' in _js()


def test_cada_tipo_declara_su_caja() -> None:
    js = _js()

    # Caja blanca: unitarias, mutación (críticas y su fortaleza) y reglas de arquitectura.
    assert "'funciones seleccionadas', 'blanca')" in js
    assert 'data-caja="blanca" aria-labelledby="prepCritTitulo"' in js
    assert 'id="prepFortaleza" data-caja="blanca"' in js
    assert 'data-caja="blanca" aria-labelledby="prepArquitecturaTitulo"' in js
    # Caja negra: endpoints y E2E de humo.
    assert "'endpoints seleccionados', 'negra')" in js
    assert 'data-caja="negra" aria-labelledby="prepE2ETitulo"' in js
    # La tarjeta de tipos se oculta si ninguna de sus filas se ve.
    assert "data-caja-grupo" in js


def test_el_modo_de_la_corrida_no_es_un_tipo() -> None:
    js = _js()
    tarjeta = _etiqueta_con(js, 'aria-labelledby="prepModoTitulo"')

    assert "data-caja" not in tarjeta
    assert "data-caja" not in _etiqueta_con(js, 'id="prepComprobaciones"')
    assert "data-caja" not in _etiqueta_con(js, 'id="prepLimites"')


def test_la_caja_gris_vacia_explica_que_esta_en_camino() -> None:
    js = _js()

    assert 'id="prepCajaVacia"' in js
    assert "integración entre funciones" in js
    assert "prepCajaVacia" in _funcion_js("aplicarCaja")


def test_cambiar_de_pestana_no_cambia_lo_elegido() -> None:
    for nombre in ("elegirCaja", "aplicarCaja", "renderCajas", "teclasCajas"):
        cuerpo = _funcion_js(nombre)
        assert "elegirPruebas" not in cuerpo
        assert "eleccionPruebas =" not in cuerpo
    aplicar = _funcion_js("aplicarCaja")
    assert "classList.toggle('hide'" in aplicar  # solo muestra u oculta


def test_los_contadores_cuentan_lo_elegido() -> None:
    cuerpo = _funcion_js("tiposElegidosPorCaja")

    assert "e.endpoints === true" in cuerpo  # negra
    assert "e.unitarias === true" in cuerpo  # blanca
    assert "e.modo === 'fondo'" in cuerpo  # la mutación también es blanca
    assert "gris: 0" in cuerpo


def test_calc_aplica_la_pestana_despues_de_dibujar_los_tipos() -> None:
    cuerpo = _funcion_js("calc")

    orden = [
        cuerpo.index("renderTiposPrueba()"),
        cuerpo.index("renderCriticas()"),
        cuerpo.index("aplicarCaja()"),
    ]
    assert orden == sorted(orden)


def test_los_estilos_nuevos_usan_solo_tokens() -> None:
    css = (PREP / "config-pruebas.css").read_text(encoding="utf-8")
    reglas = [
        linea
        for linea in css.splitlines()
        if linea.startswith((".prep-cajas-barra", ".prep-fila:has"))
    ]

    assert len(reglas) == 4
    for regla in reglas:
        assert "#" not in regla.split("{", 1)[1]
