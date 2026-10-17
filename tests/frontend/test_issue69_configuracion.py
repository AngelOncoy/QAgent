"""Issue #69: la configuración de pruebas se elige como opciones, no como planes."""

from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
FRONTEND = RAIZ / "src" / "qagent" / "frontend"


def leer(ruta: str) -> str:
    return (FRONTEND / ruta).read_text(encoding="utf-8")


def cuerpo_de(js: str, inicio: str, fin: str) -> str:
    return js[js.index(inicio) : js.index(fin, js.index(inicio))]


def config() -> str:
    return leer("componentes/config-pruebas/config-pruebas.js")


def test_la_eleccion_por_defecto_equivale_al_perfil_por_defecto() -> None:
    estado = leer("js/estado.js")

    assert "let profile = 'deep';" in estado
    assert (
        "let eleccionPruebas = {modo:'nuevas', tipo:'std', profundizar:true};" in estado
    )


def test_la_eleccion_se_traduce_a_los_cuatro_perfiles_del_backend() -> None:
    cuerpo = cuerpo_de(config(), "function perfilDeEleccion", "function elegirPruebas")

    assert "if (modo === 'repetir') return 'reg';" in cuerpo
    assert "if (tipo === 'humo') return 'humo';" in cuerpo
    assert "return profundizar && prioritarias > 0 ? 'deep' : 'std';" in cuerpo


def test_elegir_recalcula_el_perfil_y_desbloquea_el_monitor() -> None:
    js = config()
    elegir = cuerpo_de(js, "function elegirPruebas", "}\n")
    recalcular = cuerpo_de(js, "function calc()", "}\n")

    assert "eleccionPruebas = {...eleccionPruebas, ...cambio};" in elegir
    assert "calc();" in elegir
    assert "desbloquearVista('monitor')" in elegir
    assert "profile = perfilDeEleccion(eleccionPruebas, prioritarias);" in recalcular


def test_la_pantalla_pregunta_que_hacer_y_el_tipo_de_prueba() -> None:
    js = config()

    assert "¿Qué quieres hacer?" in js
    assert "'Generar pruebas nuevas'" in js and "'Repetir pruebas guardadas'" in js
    assert "Tipos de prueba" in js
    assert "${opcion('humo')}" in js and "${opcion('std')}" in js
    assert 'type="radio" name="tipoPrueba"' in js


def test_repetir_requiere_una_corrida_previa() -> None:
    js = config()

    assert "!HAS_PRIOR_RUN" in cuerpo_de(js, "function renderOpcionesPruebas", "\n}\n")
    assert 'title="Requiere una corrida previa de este proyecto"' in js
    assert (
        "if (eleccionPruebas.modo === 'repetir' && !HAS_PRIOR_RUN) eleccionPruebas.modo = 'nuevas';"
        in js
    )


def test_profundizar_se_apaga_con_humo_o_sin_funciones_prioritarias() -> None:
    js = config()

    assert "const apagada = tipo === 'humo' || prioritarias === 0;" in js
    assert "Disponible con el tipo Estándar" in js
    assert "Marca funciones en la vista previa para profundizar" in js
    assert "onclick=\"go('preview');return false\">Cambiar cuáles</a>" in js


def test_ya_no_hay_tarjetas_comparacion_ni_estimacion() -> None:
    js = config()
    css = leer("componentes/config-pruebas/config-pruebas.css")

    for quitado in (
        'id="profiles"',
        "Comparación de perfiles",
        'id="cmpBody"',
        'id="eTok"',
        "function renderProfiles",
        "function renderCompare",
        "pickProfile",
    ):
        assert quitado not in js, quitado
    for regla in (".profiles{", ".prof{", "table.cmp", ".estimate{", ".eagents{"):
        assert regla not in css, regla
    assert "renderProfiles" not in leer("componentes/vista-previa/vista-previa.js")


def test_tokens_y_duracion_quedan_en_detalles_plegados() -> None:
    js = config()
    detalles = cuerpo_de(js, "function renderDetallesCorrida", "\n}\n")

    assert '<details class="cfg-detalles">' in js
    assert '<details class="cfg-detalles" open' not in js
    assert "Uso de IA estimado: <b>${usoIA(tok)}</b>" in detalles
    assert "Duración aproximada: <b>${p.duracion}</b>" in detalles
    assert "reutilizan su spec vigente" in detalles
    assert "mutmut se aplicará" in detalles


def test_el_uso_de_ia_se_expresa_en_palabras() -> None:
    cuerpo = cuerpo_de(config(), "function usoIA", "\n}\n")

    assert "if (!tok) return 'sin IA';" in cuerpo
    assert "tok < 50000 ? 'bajo' : tok < 200000 ? 'medio' : 'alto'" in cuerpo


def test_la_estimacion_sigue_disponible_para_ejecucion_e_informe() -> None:
    assert "runEstimate = {tok};" in cuerpo_de(config(), "function calc()", "}\n")
