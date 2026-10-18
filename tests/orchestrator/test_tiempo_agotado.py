"""A2: un agente que no responde a tiempo deja solo esa función sin veredicto.

Antes, un timeout del Generator o del Reviewer tumbaba el módulo entero y las
funciones siguientes no se probaban. Sin IA real ni Docker.
"""

from __future__ import annotations

import copy
import json
import shutil
import threading
from pathlib import Path

import pytest

from qagent.almacenamiento import AlmacenProyecto
from qagent.app.monitor_eventos import a_fila_monitor
from qagent.config import cargar_configuracion
from qagent.config.carga import RUTA_CONFIG
from qagent.llm import TokenTracker
from qagent.llm.cliente import ErrorLLM, SinConexion, SinCredito
from qagent.orchestrator import BusEventos, Estado, Orquestador
from qagent.orchestrator.corrida import ejecutar_corrida
from qagent.orchestrator.orquestador import (
    TIEMPO_AGOTADO,
    FalloControlado,
    TimeoutPaso,
    es_falla_pasajera,
)
from qagent.sandbox import ResultadoSandbox
from tests.orchestrator.fakes import (
    MODULO,
    GeneratorSimulado,
    PlannerSimulado,
    ReviewerColgado,
    ReviewerGuionado,
)
from tests.orchestrator.test_orquestador import armar, plan_grabado

E = Estado


def plan_de_dos() -> list[dict]:
    segundo = copy.deepcopy(plan_grabado()[0])
    segundo["objetivo"] = "triplicar"
    return [*plan_grabado(), segundo]


class GeneratorColgadoEnLaPrimera(GeneratorSimulado):
    """No responde en la primera función; en las demás funciona normal.

    Al despertar registra tokens, como haría una llamada real que termina tarde.
    """

    def __init__(self, tracker: TokenTracker) -> None:
        super().__init__(tracker)
        self.despertar = threading.Event()
        self.terminado = threading.Event()

    def generar(self, contrato: dict, intento: int, feedback: str | None) -> dict:
        if contrato["objetivo"] == "duplicar":
            self.despertar.wait(5)
            self.tracker.registrar("generator", "lento", 7, 3)
            self.terminado.set()
        return super().generar(contrato, intento, feedback)


def orquestador_con_generator_colgado():
    tracker = TokenTracker()
    generator = GeneratorColgadoEnLaPrimera(tracker)
    orquestador = Orquestador(
        PlannerSimulado(tracker, plan_de_dos()),
        generator,
        ReviewerGuionado(tracker, ["accept"]),
        bus=BusEventos(),
        tracker=tracker,
        timeout_paso_s=0.2,
    )
    return orquestador, generator, tracker


def test_generator_colgado_deja_sin_veredicto_solo_esa_funcion() -> None:
    orquestador, generator, _ = orquestador_con_generator_colgado()

    resultado = orquestador.ejecutar(MODULO)
    generator.despertar.set()

    assert resultado.estado_final is E.FIN
    assert resultado.motivo_fallo is None
    primera, segunda = resultado.objetivos
    assert (primera.objetivo, primera.decision) == ("duplicar", None)
    assert primera.motivo_sin_veredicto == TIEMPO_AGOTADO
    assert (segunda.objetivo, segunda.decision) == ("triplicar", "accept")


def test_la_respuesta_tardia_cuenta_para_su_funcion_y_no_para_la_siguiente() -> None:
    orquestador, generator, tracker = orquestador_con_generator_colgado()

    orquestador.ejecutar(MODULO)
    generator.despertar.set()
    assert generator.terminado.wait(5)

    [tardia] = [r for r in tracker.llamadas if r.modelo == "lento"]
    assert (tardia.funcion, tardia.intento) == ("duplicar", 1)


def test_reviewer_colgado_no_cuelga_la_corrida_y_sigue_con_la_siguiente() -> None:
    orquestador, *_ = armar(
        ReviewerColgado(segundos=1), plan=plan_de_dos(), timeout_paso_s=0.1
    )

    resultado = orquestador.ejecutar(MODULO)

    assert resultado.estado_final is E.FIN
    assert [o.motivo_sin_veredicto for o in resultado.objetivos] == [
        TIEMPO_AGOTADO,
        TIEMPO_AGOTADO,
    ]


def test_el_monitor_muestra_el_tiempo_agotado_como_alerta() -> None:
    orquestador, generator, _ = orquestador_con_generator_colgado()

    orquestador.ejecutar(MODULO)
    generator.despertar.set()

    [evento] = [
        e
        for e in orquestador.bus.historial
        if (e.datos or {}).get("motivo") == TIEMPO_AGOTADO
    ]
    assert evento.tipo == "veredicto"  # cuenta para el progreso del Monitor
    fila = a_fila_monitor(evento.a_dict())
    assert fila["a"] == "watch"
    assert fila["guard"][1] == "SIN VEREDICTO"
    assert fila["identificador"] == "duplicar"


def _envuelto(causa: Exception) -> FalloControlado:
    """Como llega desde el cliente de IA: ErrorLLM envuelve al error original."""
    try:
        try:
            raise causa
        except Exception as original:
            raise ErrorLLM(str(original)) from original
    except ErrorLLM as envuelto:
        error = FalloControlado(f"Error en el generator: {envuelto}")
        error.__cause__ = envuelto
        return error


@pytest.mark.parametrize(
    "error, pasajera",
    [
        (TimeoutPaso("El generator no respondió en 240 s"), True),
        (_envuelto(SinConexion("no respondió en 90 segundos")), True),
        (_envuelto(SinCredito("HTTP 402")), False),
        (FalloControlado("Error en el reviewer: ErrorSandbox: sin Docker"), False),
    ],
)
def test_solo_tiempo_y_red_son_fallas_pasajeras(error, pasajera) -> None:
    assert es_falla_pasajera(error) is pasajera


def test_un_error_no_pasajero_sigue_deteniendo_el_modulo() -> None:
    class GeneratorSinCredito(GeneratorSimulado):
        def generar(self, contrato, intento, feedback):
            raise _envuelto(SinCredito("HTTP 402")).__cause__

    tracker = TokenTracker()
    orquestador = Orquestador(
        PlannerSimulado(tracker, plan_de_dos()),
        GeneratorSinCredito(tracker),
        ReviewerGuionado(tracker, ["accept", "accept"]),
        tracker=tracker,
    )

    resultado = orquestador.ejecutar(MODULO)

    assert resultado.estado_final is E.FALLO_CONTROLADO
    assert len(resultado.objetivos) == 1


# --- De punta a punta: results.json cumple el schema con el nuevo motivo ----------

BANCO = Path(__file__).resolve().parents[2] / "bench" / "banco_mvp.py"


def test_results_json_guarda_el_motivo_sin_veredicto(tmp_path: Path) -> None:
    shutil.copy(BANCO, tmp_path / "banco_mvp.py")
    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()
    run_id = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
    config = cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config

    def ejecutor(_imagen, _proyecto, _tests, _modulo) -> ResultadoSandbox:
        raise SinConexion("Docker no respondió a tiempo")

    resumen = ejecutar_corrida(
        tmp_path,
        "std",
        config,
        None,
        simulado=True,
        run_id=run_id,
        preparar_imagen=lambda _ruta: "imagen-prueba",
        ejecutor=ejecutor,
        seleccion=[
            {
                "ruta": "banco_mvp.py",
                "funciones": ["calcular_descuento", "es_palindromo"],
                "endpoints": [],
                "criticas": [],
            }
        ],
    )

    results = json.loads(
        (almacen.carpeta_run(run_id) / "results.json").read_text(encoding="utf-8")
    )
    assert resumen.estado == "fin"
    assert resumen.sin_veredicto == 2
    assert {o["motivo_sin_veredicto"] for o in results["objetivos"]} == {TIEMPO_AGOTADO}
