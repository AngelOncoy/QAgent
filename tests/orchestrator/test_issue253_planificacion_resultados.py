"""#253: fallos reales de contrato conservan diagnóstico, lenguaje y progreso."""

import json
from pathlib import Path

import pytest

from qagent import contracts
from qagent.agents.planner import ErrorRespuestaPlanner, PlannerAgent
from qagent.lenguajes import JavaAdapter
from qagent.llm import FakeLLMClient, TokenTracker, cargar_precios
from qagent.orchestrator import Orquestador
from qagent.storage import escribir_corrida
from qagent.storage.vista_ejecucion import vista_ejecucion
from qagent.storage.vista_reporte import leer_detalle, vista_reporte
from tests.orchestrator.fakes import GeneratorSimulado, ReviewerGuionado
from tests.orchestrator.test_fix02_errores_planner import (
    FUNCIONES,
    _correr,
    _planner_falso,
)


def test_fallo_java_llega_a_results_y_reporte_sin_inventar_pruebas(
    tmp_path: Path,
) -> None:
    """Un caso sin resultado esperado falla sin Docker y conserva la causa exacta."""
    (tmp_path / "Banco.java").write_text(
        "class Banco { /** Devuelve true si edad es al menos 18. */ "
        "public boolean mayor(int edad) {return edad >= 18;} }",
        encoding="utf-8",
    )
    [modulo] = JavaAdapter().analizar(tmp_path)["modulos"]
    tracker = TokenTracker()
    planner = PlannerAgent(
        FakeLLMClient(
            grabaciones={
                "Banco.java::Banco.mayor": [
                    {"id": "mayor", "entrada": {"edad": 18}, "origen": "docstring"}
                ]
            }
        ),
        tracker,
        adaptador=JavaAdapter(),
        es_simulado=True,
    )
    resultado = Orquestador(
        planner,
        GeneratorSimulado(tracker),
        ReviewerGuionado(tracker, []),
        tracker=tracker,
    ).ejecutar(modulo)
    [objetivo] = resultado.objetivos
    assert objetivo.motivo_sin_veredicto == "error_planner"
    assert objetivo.lenguaje == "java"
    assert objetivo.contrato is objetivo.codigo is objetivo.decision is None
    assert objetivo.intentos == 0
    assert "casos/0" in objetivo.detalle_error_planner
    assert tracker.total_tokens == 0

    rutas = escribir_corrida(tmp_path, resultado, tracker, cargar_precios(), "std")
    results = json.loads(rutas.results.read_text(encoding="utf-8"))
    contracts.validar(contracts.RUN_LOG, results)
    [registrado] = results["objetivos"]
    assert registrado["lenguaje"] == "java"
    assert registrado["detalle_error_planner"] == objetivo.detalle_error_planner
    [fila] = vista_ejecucion(results)["modulos"][0]["pruebas"]
    reporte = vista_reporte(results, leer_detalle(tmp_path, rutas.run_id))
    for vista in (fila, reporte["funciones"][0]):
        assert vista["lenguaje"] == "java"
        assert vista["detalle_error_planner"] == objetivo.detalle_error_planner

    # Las corridas anteriores siguen siendo válidas sin el nuevo dato opcional.
    registrado.pop("detalle_error_planner")
    contracts.validar(contracts.RUN_LOG, results)


def test_diagnostico_guardado_no_expone_un_secreto(tmp_path: Path) -> None:
    """El detalle pasa por el saneamiento de secretos antes de escribirse."""
    from qagent.orchestrator import Estado, ResultadoCorrida, ResultadoObjetivo

    secreto = "sk-ant-" + "a1B2c3D4" * 8
    objetivo = ResultadoObjetivo(
        "Banco.mayor",
        False,
        lenguaje="java",
        motivo_sin_veredicto="error_planner",
        detalle_error_planner=f"casos/0: token={secreto}",
    )
    resultado = ResultadoCorrida("Banco.java", Estado.FIN, None, [objetivo], [], {}, 0)
    rutas = escribir_corrida(
        tmp_path, resultado, TokenTracker(), cargar_precios(), "std"
    )
    texto = rutas.results.read_text(encoding="utf-8")
    assert secreto not in texto
    assert "casos/0" in texto


@pytest.mark.parametrize("duplicar_veredicto", [False, True])
def test_progreso_con_varios_modulos_y_planes_vacios(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, duplicar_veredicto: bool
) -> None:
    """El plan vacío no reduce lo seleccionado ni duplica objetivos procesados."""
    for archivo, nombre in FUNCIONES.items():
        (tmp_path / archivo).write_text(
            f'def {nombre}(x: int) -> int:\n    """Devuelve x."""\n    return x\n',
            encoding="utf-8",
        )
    _planner_falso(
        monkeypatch,
        fallos={
            archivo: ErrorRespuestaPlanner("casos/0: formato inválido")
            for archivo in FUNCIONES
        },
    )
    if duplicar_veredicto:
        emitir = Orquestador._emitir

        def repetido(self, *args, **kwargs):
            emitir(self, *args, **kwargs)
            if kwargs.get("tipo") == "veredicto":
                emitir(self, *args, **kwargs)

        monkeypatch.setattr(Orquestador, "_emitir", repetido)
    resumen, eventos = _correr(tmp_path)
    assert resumen.total_seleccionados == resumen.total_procesados == 3
    assert resumen.sin_veredicto == 3
    assert all(e["progreso"]["total"] == 3 for e in eventos)
    veredictos = [e["progreso"]["hechos"] for e in eventos if e["tipo"] == "veredicto"]
    assert veredictos == ([1, 1, 2, 2, 3, 3] if duplicar_veredicto else [1, 2, 3])
