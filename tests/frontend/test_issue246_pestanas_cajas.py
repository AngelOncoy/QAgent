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


def test_cada_tipo_declara_su_caja_como_define_la_arquitectura() -> None:
    """docs/arquitectura.md §10.2: funciones, negra; endpoints, gris; mutación, blanca."""
    js = _js()

    # Caja negra: funciones (solo nombre, firma y docstring) y E2E de humo.
    assert "'funciones seleccionadas', 'negra')" in js
    assert 'data-caja="negra" aria-labelledby="prepE2ETitulo"' in js
    # Caja gris: endpoints (el código del manejador guía los casos).
    assert "'endpoints seleccionados', 'gris')" in js
    # Caja blanca: críticas y su fortaleza (mutación) y reglas de arquitectura.
    assert 'data-caja="blanca" aria-labelledby="prepCritTitulo"' in js
    assert 'id="prepFortaleza" data-caja="blanca"' in js
    assert 'data-caja="blanca" aria-labelledby="prepArquitecturaTitulo"' in js
    # La tarjeta de tipos se oculta si ninguna de sus filas se ve.
    assert "data-caja-grupo" in js


def _modos() -> dict[str, list[str]]:
    js = _js()
    bloque = js[
        js.index("const MODOS_PREPARAR = [") : js.index(
            "];", js.index("const MODOS_PREPARAR = [")
        )
    ]
    return {
        clave: re.findall(r"'(\w+)'", cajas)
        for clave, cajas in re.findall(r"\{k:'(\w+)',\s*cajas:\[([^\]]*)\]", bloque)
    }


def test_cada_opcion_de_que_quieres_hacer_declara_sus_cajas() -> None:
    modos = _modos()

    assert set(modos) == {"nuevas", "humo", "repetir", "fondo"}
    # El análisis a fondo es la capa de caja blanca: no se ofrece en negra ni en gris.
    assert modos["fondo"] == ["blanca"]
    # Estándar y Humo usan solo la especificación: no son de caja blanca.
    for clave in ("nuevas", "humo"):
        assert "blanca" not in modos[clave]
        assert {"negra", "gris"} <= set(modos[clave])
    # Regresión vuelve a correr lo guardado y puede medir su fortaleza (blanca).
    assert set(modos["repetir"]) == {"negra", "gris", "blanca"}


def test_que_quieres_hacer_muestra_solo_lo_de_la_pestana() -> None:
    cuerpo = _funcion_js("renderModosPreparar")

    assert "cajaActiva === 'todas' || o.cajas.includes(cajaActiva)" in cuerpo
    assert "ofrecidas.map(" in cuerpo
    # Si lo elegido está en otra pestaña, se avisa y no se cambia.
    assert "elegidaOculta" in cuerpo and "eleccionPruebas" in cuerpo
    assert "eleccionPruebas =" not in cuerpo


def test_cambiar_de_pestana_vuelve_a_dibujar_las_opciones() -> None:
    cuerpo = _funcion_js("elegirCaja")

    assert cuerpo.index("renderModosPreparar()") < cuerpo.index("aplicarCaja()")


def test_el_modo_de_la_corrida_no_es_un_tipo() -> None:
    js = _js()
    tarjeta = _etiqueta_con(js, 'aria-labelledby="prepModoTitulo"')

    assert "data-caja" not in tarjeta
    assert "data-caja" not in _etiqueta_con(js, 'id="prepComprobaciones"')
    assert "data-caja" not in _etiqueta_con(js, 'id="prepLimites"')


def test_una_pestana_sin_nada_explica_que_no_hay_pruebas_de_ese_tipo() -> None:
    js = _js()

    assert 'id="prepCajaVacia"' in js
    assert "integración entre funciones" in js  # lo que vendrá en la caja gris (#245)
    assert "prepCajaVacia" in _funcion_js("aplicarCaja")


def test_cambiar_de_pestana_no_cambia_lo_elegido() -> None:
    for nombre in ("elegirCaja", "aplicarCaja", "renderCajas", "teclasCajas"):
        cuerpo = _funcion_js(nombre)
        assert "elegirPruebas" not in cuerpo
        assert "eleccionPruebas =" not in cuerpo
    aplicar = _funcion_js("aplicarCaja")
    assert "classList.toggle('hide'" in aplicar  # solo muestra u oculta


def test_las_pestanas_no_llevan_numeros() -> None:
    """Solo filtran por tipo de prueba: no cuentan ni eligen nada."""
    js = _js()
    render = _funcion_js("renderCajas")

    assert "tiposElegidosPorCaja" not in js
    assert "${c.t}</button>" in render
    assert "(${" not in render


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


# --- Tres niveles de complejidad (#246) ---------------------------------------------


def _vista_js() -> str:
    ruta = RAIZ / "src" / "qagent" / "frontend" / "componentes" / "vista-previa"
    return (ruta / "vista-previa.js").read_text(encoding="utf-8")


def test_complejidad_tiene_tres_niveles_en_orden() -> None:
    js = _vista_js()
    cuerpo = js[
        js.index("function textoComplejidad(") : js.index(
            "\n}\n", js.index("function textoComplejidad(")
        )
    ]

    sin, pocas, muchas = (
        cuerpo.index(t) for t in ("Sin ramas", "Pocas ramas", "Muchas ramas")
    )
    assert sin < pocas < muchas
    assert "if(n === 0)" in cuerpo and "if(n < 3)" in cuerpo
    assert "Simple" not in cuerpo


def test_profundizar_se_propone_desde_la_primera_rama() -> None:
    """«Pocas ramas» y «Muchas ramas» vienen marcadas para profundizar; «Sin ramas», no."""
    from qagent.proyectos.vista_previa import generar_vista_previa  # noqa: F401

    fuente = (RAIZ / "src" / "qagent" / "proyectos" / "vista_previa.py").read_text(
        encoding="utf-8"
    )
    assert '"critica_propuesta": f.get("ramas", 0) > 0' in fuente
    assert "critica_propuesta ?? ((f.ramas || 0) > 0)" in _vista_js()


def test_los_campos_de_arquitectura_usan_el_diseno_de_la_interfaz() -> None:
    js = _js()

    for campo in ("prepArqDesde", "prepArqHacia"):
        etiqueta = _etiqueta_con(js, f'id="{campo}"')
        assert 'class="np-input"' in etiqueta
        assert f'<label class="np-etiqueta" for="{campo}">' in js
    assert "ini-input" not in js  # esa clase no tiene estilos: dejaba cajas blancas
    css = (PREP / "config-pruebas.css").read_text(encoding="utf-8")
    assert ".prep-arq-campo{" in css
