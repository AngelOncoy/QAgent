"""#194: acción accesible y explícita «Verificar corrección» en Historial."""

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
JS = (RAIZ / "src/qagent/frontend/componentes/historial/historial.js").read_text(
    encoding="utf-8"
)
CSS = (RAIZ / "src/qagent/frontend/componentes/historial/historial.css").read_text(
    encoding="utf-8"
)


def test_historial_muestra_accion_para_la_corrida_seleccionada() -> None:
    assert 'id="histVerificar"' in JS
    assert "Verificar corrección" in JS
    assert "verificarCorreccionSeleccionada()" in JS
    assert "api.verificar_correccion(projectPath, histSel)" in JS


def test_monitor_escucha_antes_de_iniciar_para_no_perder_el_fin() -> None:
    inicio = JS.index("iniciarMonitorReal();")
    llamada = JS.index("await api.verificar_correccion(projectPath, histSel)")
    assert inicio < llamada
    assert "monitorStarted = false;\n      go('history');" in JS


def test_confirma_prueba_original_y_cero_ia() -> None:
    assert "exactamente las pruebas guardadas de esta corrida" in JS
    assert "No se regenerarán pruebas ni se utilizará IA" in JS
    assert "Cero IA" in JS


def test_previene_doble_inicio_y_expone_estado_accesible() -> None:
    assert "if(!histSel || histVerificando) return" in JS
    assert "boton.disabled = true" in JS
    assert 'role="status" aria-live="polite"' in JS


def test_evaluacion_ia_no_se_encadena_a_la_verificacion() -> None:
    funcion = JS.split("async function verificarCorreccionSeleccionada()", 1)[1].split(
        "function abrirCorridaSeleccionada", 1
    )[0]
    assert "start_run" not in funcion
    assert "evalu" not in funcion.lower()
    assert "llm" not in funcion.lower()


def test_estilos_reutilizan_tokens_y_no_colores_literales() -> None:
    assert ".hst-acciones-corrida" in CSS
    assert "var(--" in CSS
    assert "#fff" not in CSS.lower()
