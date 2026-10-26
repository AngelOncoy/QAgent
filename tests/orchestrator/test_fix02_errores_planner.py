"""FIX-02 (#127): un error recuperable del Planner no detiene toda la corrida.

Proyecto de tres módulos independientes (`mod_a.py`, `mod_b.py`, `mod_c.py`), una
función cada uno. El Planner se reemplaza para fallar en el módulo indicado y el
sandbox por un ejecutor que siempre pasa (sin Docker ni red, 0 tokens).

Escenarios obligatorios de la issue:

* A: los tres objetivos se procesan bien.
* B: el Planner falla de forma recuperable en el segundo; el tercero continúa.
* C: el usuario cancela; no se procesa nada más.
* D: se agota el presupuesto de tokens; no se procesa nada más.
* E: un error global (cuenta sin crédito) detiene la corrida; un error desconocido
  sigue tratándose como fallo controlado, sin esconderse.
"""

from __future__ import annotations

import copy
import dataclasses
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from qagent.agents.planner import ErrorRespuestaPlanner
from qagent.almacenamiento import AlmacenProyecto
from qagent.almacenamiento.historial import construir_historial
from qagent.app.monitor_eventos import a_fila_monitor
from qagent.config import cargar_configuracion
from qagent.config.carga import RUTA_CONFIG
from qagent.llm import TokenTracker
from qagent.llm.cliente import ErrorLLM, SinConexion, SinCredito
from qagent.orchestrator import BusEventos, Estado, Orquestador
from qagent.orchestrator.corrida import ResumenCorrida, ejecutar_corrida
from qagent.orchestrator.orquestador import (
    ERROR_PLANNER,
    TimeoutPaso,
    es_error_global,
    es_error_planner_recuperable,
)
from qagent.sandbox import ResultadoSandbox
from tests.orchestrator.fakes import (
    MODULO,
    GeneratorSimulado,
    PlannerSimulado,
    ReviewerGuionado,
)
from tests.orchestrator.test_orquestador import plan_grabado

FUNCIONES = {"mod_a.py": "uno", "mod_b.py": "dos", "mod_c.py": "tres"}


@pytest.fixture
def proyecto(tmp_path: Path) -> Path:
    for archivo, nombre in FUNCIONES.items():
        (tmp_path / archivo).write_text(
            f'def {nombre}(x: int) -> int:\n    """Devuelve x."""\n    return x\n',
            encoding="utf-8",
        )
    AlmacenProyecto(tmp_path).inicializar()
    return tmp_path


def _contrato(modulo: dict[str, Any]) -> dict[str, Any]:
    contrato = copy.deepcopy(plan_grabado()[0])
    contrato.update(
        modulo=modulo["ruta"],
        huella=modulo["huella"],
        objetivo=modulo["funciones"][0]["nombre"],
    )
    return contrato


def _planner_falso(
    monkeypatch: pytest.MonkeyPatch,
    fallos: dict[str, BaseException] | None = None,
    tokens: dict[str, int] | None = None,
) -> list[str]:
    """Reemplaza al Planner: falla o consume tokens en los módulos indicados.

    Devuelve la lista de módulos que se planificaron, en orden.
    """
    llamados: list[str] = []

    def planificar(self, modulo: dict[str, Any]) -> list[dict[str, Any]]:
        llamados.append(modulo["ruta"])
        gasto = (tokens or {}).get(modulo["ruta"])
        if gasto:
            self.tracker.registrar("planner", "simulado", gasto, 0, es_simulado=True)
        error = (fallos or {}).get(modulo["ruta"])
        if error is not None:
            raise error
        return [_contrato(modulo)]

    monkeypatch.setattr(
        "qagent.orchestrator.corrida.PlannerAgent.planificar", planificar
    )
    return llamados


def _ejecutor_ok(al_ejecutar: Callable[[], None] | None = None):
    def ejecutor(_imagen, _proyecto, _tests, _modulo) -> ResultadoSandbox:
        if al_ejecutar is not None:
            al_ejecutar()
        return ResultadoSandbox(
            exit_code=0, stdout="=== 1 passed ===", stderr="", duracion_s=0.1
        )

    return ejecutor


def _correr(
    proyecto: Path,
    *,
    config: Any = None,
    cancelado: Callable[[], bool] | None = None,
    al_ejecutar: Callable[[], None] | None = None,
) -> tuple[ResumenCorrida, list[dict[str, Any]]]:
    config = (
        config
        or cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config
    )
    run_id = AlmacenProyecto(proyecto).crear_run(tipos_prueba=["funcion"])["run_id"]
    eventos: list[dict[str, Any]] = []
    resumen = ejecutar_corrida(
        proyecto,
        "deep",
        config,
        None,
        simulado=True,
        run_id=run_id,
        al_evento=eventos.append,
        preparar_imagen=lambda _ruta, _avanzar=None: "imagen-falsa",
        ejecutor=_ejecutor_ok(al_ejecutar),
        cancelado=cancelado,
    )
    return resumen, eventos


def _resultados(proyecto: Path, run_id: str) -> dict[str, dict[str, Any]]:
    """Objetivos de results.json por nombre de función."""
    carpeta = AlmacenProyecto(proyecto).carpeta_run(run_id)
    datos = json.loads((carpeta / "results.json").read_text(encoding="utf-8"))
    return {f["funcion"]: f for f in datos["objetivos"]}


# --- Clasificación de errores ------------------------------------------------------


@pytest.mark.parametrize(
    "error",
    [
        ErrorRespuestaPlanner("El Planner no devolvió JSON válido."),
        TimeoutPaso("El planner no respondió en 60 s"),
        SinConexion("sin red"),
    ],
)
def test_errores_recuperables_del_planner(error: BaseException) -> None:
    envuelto = RuntimeError("Error en el planner")
    envuelto.__cause__ = error
    assert es_error_planner_recuperable(error)
    assert es_error_planner_recuperable(envuelto)


@pytest.mark.parametrize(
    "error",
    [
        SinCredito("sin crédito", codigo=402),
        RuntimeError("fallo de programación"),
        KeyError("objetivo"),
    ],
)
def test_errores_no_recuperables_del_planner(error: BaseException) -> None:
    assert not es_error_planner_recuperable(error)


@pytest.mark.parametrize(
    ("error", "global_"),
    [
        (SinCredito("sin crédito", codigo=402), True),
        (ErrorLLM("clave inválida", codigo=401), True),
        (ErrorLLM("prohibido", codigo=403), True),
        (ErrorLLM("error del servidor", codigo=500), False),
        (ErrorRespuestaPlanner("JSON roto"), False),
    ],
)
def test_errores_globales_de_la_cuenta(error: BaseException, global_: bool) -> None:
    assert es_error_global(error) is global_


# --- Caso A: tres objetivos correctos -----------------------------------------------


def test_caso_a_tres_objetivos_procesados(
    proyecto: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    llamados = _planner_falso(monkeypatch)

    resumen, _ = _correr(proyecto)

    assert llamados == ["mod_a.py", "mod_b.py", "mod_c.py"]
    assert resumen.estado == "fin"
    assert resumen.tipo_terminacion == "completada"
    assert resumen.aceptadas == 3
    assert resumen.total_pendientes == 0
    resultados = _resultados(proyecto, resumen.run_id)
    assert {n: r["decision"] for n, r in resultados.items()} == {
        "uno": "accept",
        "dos": "accept",
        "tres": "accept",
    }


# --- Caso B: fallo recuperable en el segundo; el tercero continúa -------------------


def test_caso_b_fallo_recuperable_del_planner_no_detiene_el_tercero(
    proyecto: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    llamados = _planner_falso(
        monkeypatch,
        fallos={
            "mod_b.py": ErrorRespuestaPlanner("El Planner no devolvió JSON válido.")
        },
    )

    resumen, eventos = _correr(proyecto)

    # El tercero se planificó y se aprobó.
    assert llamados == ["mod_a.py", "mod_b.py", "mod_c.py"]
    resultados = _resultados(proyecto, resumen.run_id)
    assert resultados["uno"]["decision"] == "accept"
    assert resultados["tres"]["decision"] == "accept"

    # El fallido conserva su error y no aparece como aprobado ni como pendiente.
    dos = resultados["dos"]
    assert dos["decision"] is None
    assert dos["motivo_sin_veredicto"] == ERROR_PLANNER
    assert resumen.aceptadas == 2
    assert resumen.sin_veredicto == 1
    assert resumen.total_pendientes == 0

    # El estado global dice que hubo errores, sin presentarse como detenida.
    assert resumen.estado == "fin"
    assert resumen.tipo_terminacion == "completada_con_errores"
    assert "completada con errores" in (resumen.motivo or "").lower()

    # run.json e Historial cuentan los tres objetivos.
    run = AlmacenProyecto(proyecto).leer_run(resumen.run_id)
    assert run["estado"] != "fallo_controlado"
    [corrida] = construir_historial(proyecto)["corridas"]
    assert corrida["total_objetivos"] == 3
    assert corrida["pasaron"] == 2

    # El Monitor muestra el objetivo sin veredicto con el error del Planner.
    veredictos = [
        e
        for e in eventos
        if e.get("tipo") == "veredicto"
        and (e.get("datos") or {}).get("motivo") == ERROR_PLANNER
    ]
    assert [e["funcion"] for e in veredictos] == ["dos"]
    assert "JSON" in veredictos[0]["mensaje"]
    fila = a_fila_monitor(veredictos[0])
    assert fila["a"] == "watch"
    assert fila["guard"] == ["El Planner no pudo planificarlo", "SIN VEREDICTO"]
    assert fila["fn"] == "dos"


def test_caso_b_tiempo_agotado_del_planner_tambien_es_recuperable(
    proyecto: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    llamados = _planner_falso(
        monkeypatch, fallos={"mod_b.py": SinConexion("El proveedor no respondió")}
    )

    resumen, _ = _correr(proyecto)

    assert llamados == ["mod_a.py", "mod_b.py", "mod_c.py"]
    assert _resultados(proyecto, resumen.run_id)["tres"]["decision"] == "accept"
    assert resumen.tipo_terminacion == "completada_con_errores"


class PlannerEndpointsRotos(PlannerSimulado):
    """Planifica bien las funciones y falla al planificar los endpoints."""

    def planificar_endpoints(self, modulo: dict, fuente: str | None) -> list[dict]:
        raise ErrorRespuestaPlanner("El Planner no devolvió JSON válido.")


def test_caso_b_fallan_los_endpoints_y_las_funciones_siguen() -> None:
    """Dentro de un módulo, el fallo de una parte no se lleva el plan de la otra."""
    tracker = TokenTracker()
    contrato = plan_grabado()[0]
    modulo = {
        **MODULO,
        "endpoints": [{"objetivo": "GET /items", "manejador": "listar"}],
    }
    orquestador = Orquestador(
        planner=PlannerEndpointsRotos(tracker, [contrato]),
        generator=GeneratorSimulado(tracker),
        reviewer=ReviewerGuionado(tracker, ["accept"]),
        bus=BusEventos(),
        tracker=tracker,
    )

    resultado = orquestador.ejecutar(modulo)

    assert resultado.estado_final is Estado.FIN
    decisiones = {o.objetivo: o for o in resultado.objetivos}
    assert decisiones[contrato["objetivo"]].decision == "accept"
    endpoint = decisiones["GET /items"]
    assert endpoint.decision is None
    assert endpoint.motivo_sin_veredicto == ERROR_PLANNER
    assert endpoint.tipo == "endpoint"
    assert resultado.omitidos == []


# --- Caso C: cancelación del usuario ------------------------------------------------


def test_caso_c_cancelacion_detiene_el_procesamiento(
    proyecto: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    llamados = _planner_falso(monkeypatch)
    estado = {"cancelado": False}

    def cancelar() -> None:
        estado["cancelado"] = True

    resumen, _ = _correr(
        proyecto, cancelado=lambda: estado["cancelado"], al_ejecutar=cancelar
    )

    assert llamados == ["mod_a.py"]
    assert resumen.cancelada is True
    assert resumen.tipo_terminacion == "cancelada"
    # Lo procesado antes de cancelar se conserva.
    assert _resultados(proyecto, resumen.run_id)["uno"]["decision"] == "accept"


# --- Caso D: presupuesto de tokens agotado ------------------------------------------


def test_caso_d_limite_de_tokens_detiene_la_corrida(
    proyecto: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    llamados = _planner_falso(monkeypatch, tokens={"mod_b.py": 5000})
    config = cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config
    config = dataclasses.replace(
        config,
        presupuesto=dataclasses.replace(
            config.presupuesto, max_tokens_por_corrida=1000
        ),
    )

    resumen, _ = _correr(proyecto, config=config)

    assert llamados == ["mod_a.py", "mod_b.py"]
    assert resumen.tipo_terminacion == "limitada_recursos"
    resultados = _resultados(proyecto, resumen.run_id)
    assert resultados["uno"]["decision"] == "accept"
    assert "tres" not in resultados


# --- Caso E: error crítico global ---------------------------------------------------


def test_caso_e_error_global_detiene_la_corrida(
    proyecto: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    llamados = _planner_falso(
        monkeypatch,
        fallos={"mod_b.py": SinCredito("La cuenta no tiene crédito", codigo=402)},
    )

    resumen, _ = _correr(proyecto)

    # No se insiste con el tercero: fallaría igual y gastaría llamadas.
    assert llamados == ["mod_a.py", "mod_b.py"]
    assert resumen.estado == "fallo_controlado"
    assert resumen.tipo_terminacion == "detenida_error"
    assert "crédito" in (resumen.motivo or "")
    resultados = _resultados(proyecto, resumen.run_id)
    assert resultados["uno"]["decision"] == "accept"
    assert "dos" not in resultados or resultados["dos"]["decision"] != "accept"


def test_caso_e_error_desconocido_no_se_esconde(
    proyecto: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _planner_falso(monkeypatch, fallos={"mod_b.py": RuntimeError("fallo inesperado")})

    resumen, _ = _correr(proyecto)

    assert resumen.estado == "fallo_controlado"
    assert resumen.tipo_terminacion == "detenida_error"
    assert "fallo inesperado" in (resumen.motivo or "")
    resultados = _resultados(proyecto, resumen.run_id)
    assert resultados.get("dos", {}).get("motivo_sin_veredicto") != ERROR_PLANNER
