"""Estados de la interfaz que se ponen al día sin reabrir el proyecto (#251).

Casos 2 (entorno al cambiar el motor), foco de la ventana, 8 (Volver a analizar) y 9
(corridas previas al terminar). Sin navegador: se comprueba la estructura del código.
"""

from __future__ import annotations

from pathlib import Path

COMPONENTES = Path(__file__).resolve().parents[2] / "src/qagent/frontend/componentes"


def _leer(ruta: str) -> str:
    return (COMPONENTES / ruta).read_text(encoding="utf-8")


def _cuerpo(js: str, funcion: str) -> str:
    resto = js[js.index(f"function {funcion}(") :]
    return resto[: resto.index("\n}\n")]


SIDEBAR = _leer("sidebar/sidebar.js")
VISTA = _leer("vista-previa/vista-previa.js")
MONITOR = _leer("monitor/monitor.js")


def test_al_cambiar_el_motor_se_vuelve_a_verificar_el_entorno():
    actualizar = _cuerpo(SIDEBAR, "actualizarSandbox")
    # Se compara con el estado anterior y solo se reacciona a un cambio.
    assert "const anterior = ESTADO_MOTOR && ESTADO_MOTOR.clave;" in actualizar
    assert "if (anterior && anterior !== ESTADO_MOTOR.clave) alCambiarMotor();" in (
        actualizar
    )
    assert actualizar.index("const anterior") < actualizar.index("ESTADO_MOTOR = {")
    assert "verificarEntorno()" in _cuerpo(SIDEBAR, "alCambiarMotor")


def test_sin_bucle_entre_motor_y_entorno():
    # verificarEntorno pide el motor, pero el motor solo vuelve a verificar ante un cambio,
    # y no hay dos consultas del motor a la vez.
    assert "actualizarSandbox()" in _cuerpo(VISTA, "verificarEntorno")
    actualizar = _cuerpo(SIDEBAR, "actualizarSandbox")
    assert "if (sandboxConsultando) return;" in actualizar
    assert "verificarEntorno" not in actualizar


def test_al_volver_a_la_ventana_se_consulta_al_instante():
    iniciar = _cuerpo(SIDEBAR, "iniciarEstadoSandbox")
    assert "window.addEventListener('focus', alVolverALaVentana)" in iniciar
    assert "document.addEventListener('visibilitychange', alVolverALaVentana)" in (
        iniciar
    )
    vuelta = _cuerpo(SIDEBAR, "alVolverALaVentana")
    assert "document.visibilityState === 'hidden'" in vuelta
    assert "ESPERA_VUELTA_MS" in vuelta  # foco y visibilidad llegan juntos: una vez
    assert "actualizarSandbox()" in vuelta and "verificarEntorno()" in vuelta
    assert "setInterval(actualizarSandbox, 15000)" in iniciar


def test_explorar_permite_volver_a_analizar_conservando_la_seleccion():
    assert 'id="expReanalizar" onclick="volverAAnalizar()"' in VISTA
    assert "Volver a analizar" in VISTA
    cuerpo = _cuerpo(VISTA, "volverAAnalizar")
    assert cuerpo.index("instantaneaSeleccionObjetivos()") < cuerpo.index(
        "cargarDatosVistaPrevia(res)"
    )
    assert cuerpo.index("cargarDatosVistaPrevia(res)") < cuerpo.index(
        "aplicarSeleccionObjetivos(seleccion)"
    )
    assert "VISTA_OBJETIVOS = vista" in cuerpo and "BUSQUEDA =" in cuerpo
    assert "renderTree()" in cuerpo
    assert "!runDone" in cuerpo  # no durante una corrida
    assert "boton.disabled = false" in cuerpo.split("finally", 1)[1]


def test_restaurar_y_volver_a_analizar_usan_la_misma_regla():
    assert "aplicarSeleccionObjetivos(respuesta && respuesta.seleccion)" in _cuerpo(
        VISTA, "restaurarSeleccionExplorar"
    )
    assert "await restaurarSeleccionExplorar();" in VISTA


def test_al_terminar_una_corrida_se_actualizan_las_corridas_previas():
    assert "actualizarCorridasPrevias()" in _cuerpo(MONITOR, "monitorFinReal")
    cuerpo = VISTA[VISTA.index("async function actualizarCorridasPrevias") :]
    cuerpo = cuerpo[: cuerpo.index("\n}\n")]
    assert "HAS_PRIOR_RUN = await hayCorridaPrevia(projectPath)" in cuerpo
    assert "PRUEBAS_REPETIBLES = await pruebasRepetibles(projectPath)" in cuerpo
    assert "calc()" in cuerpo
