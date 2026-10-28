"""#150: regresión profunda como opción de «Volver a correr las guardadas»."""

from __future__ import annotations

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "src" / "qagent" / "frontend"


def _leer(ruta: str) -> str:
    return (FRONTEND / ruta).read_text(encoding="utf-8")


def _cuerpo(js: str, inicio: str, fin: str) -> str:
    posicion = js.index(inicio)
    return js[posicion : js.index(fin, posicion)]


def test_repetir_muestra_la_casilla_sin_crear_un_quinto_modo() -> None:
    js = _leer("componentes/config-pruebas/config-pruebas.js")
    modos = _cuerpo(js, "const MODOS_PREPARAR", "];\n")

    assert modos.count("{k:") == 4
    assert "Medir la fortaleza de las críticas" in js
    assert "No consume tokens de IA, pero puede tardar más." in js
    assert 'id="prepRegDeep"' in js
    assert 'class="prep-reg-deep' in js


def test_perfil_de_eleccion_solo_activa_reg_deep_si_es_elegible() -> None:
    js = _leer("componentes/config-pruebas/config-pruebas.js")
    perfil = _cuerpo(js, "function perfilDeEleccion", "\n}\n")

    assert "profundizarRepetir && repetibles > 0 ? 'reg_deep' : 'reg'" in perfil
    assert "if (modo === 'humo') return 'humo';" in perfil
    assert "if (modo === 'fondo') return prioritarias > 0 ? 'deep' : 'std';" in perfil


def test_elegibilidad_usa_pruebas_repetibles_y_solo_funciones_seleccionadas() -> None:
    js = _leer("componentes/config-pruebas/config-pruebas.js")
    elegibles = _cuerpo(js, "function criticasRepetibles", "\n}\n")

    assert "PRUEBAS_REPETIBLES instanceof Set" in elegibles
    assert "eleccionPruebas.unitarias === false" in elegibles
    assert "f.inc && f.crit" in elegibles
    assert "PRUEBAS_REPETIBLES.has(m.path + '::' + f.n)" in elegibles
    assert ".endpoints" not in elegibles


def test_casilla_explica_todos_los_estados_de_no_disponibilidad() -> None:
    js = _leer("componentes/config-pruebas/config-pruebas.js")
    render = _cuerpo(js, "function renderRegresionProfunda", "\n}\n")

    assert "!HAS_PRIOR_RUN" in render
    assert "PRUEBAS_REPETIBLES instanceof Set" in render
    assert "Ninguna función crítica seleccionada" in render
    assert "disabled" in render
    assert "repetibles" in render


def test_cambio_de_modo_o_seleccion_invalida_limpia_la_casilla() -> None:
    js = _leer("componentes/config-pruebas/config-pruebas.js")
    elegir = _cuerpo(js, "function elegirPruebas", "\n}\n")
    calc = _cuerpo(js, "function calc()", "\n}\n")

    assert "cambio.modo && cambio.modo !== 'repetir'" in elegir
    assert "profundizarRepetir:false" in elegir
    assert "if (!repetibles && eleccionPruebas.profundizarRepetir)" in calc
    assert "profundizarRepetir:false" in calc


def test_reg_deep_conserva_cero_tokens_y_llega_a_start_run() -> None:
    config = _leer("componentes/config-pruebas/config-pruebas.js")
    monitor = _leer("componentes/monitor/monitor.js")

    assert "profile==='reg_deep' ? 'reg' : profile" in config
    assert "profile==='reg_deep'" in config
    assert (
        "window.pywebview.api.start_run(projectPath, profile, obtenerSeleccionObjetivos())"
        in monitor
    )


def test_estado_inicial_es_desmarcado_y_compatible_con_seleccion_persistida() -> None:
    estado = _leer("js/estado.js")
    vista = _leer("componentes/vista-previa/vista-previa.js")

    assert "profundizarRepetir:false" in estado
    assert "PRUEBAS_REPETIBLES = await pruebasRepetibles(ruta);" in vista
    assert "await restaurarSeleccionExplorar();" in vista
