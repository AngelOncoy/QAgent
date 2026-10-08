"""Pruebas del orquestador de la corrida (EN-04) con la IA simulada: 0 tokens, sin Docker."""

from __future__ import annotations

import copy
import json
import time

import pytest

from pyagent.llm import FakeLLMClient, TokenTracker
from pyagent.orchestrator import (
    TRANSICIONES,
    BusEventos,
    Estado,
    Orquestador,
    TransicionInvalida,
    validar_transicion,
)
from tests.orchestrator.fakes import (
    MODULO,
    GeneratorSimulado,
    PlannerSimulado,
    ReviewerColgado,
    ReviewerGuionado,
    ReviewerSandboxCaido,
    ReviewerSandboxTimeout,
)

E = Estado


def armar(reviewer, *, plan=None, **opciones):
    """Orquestador con Planner y Generator simulados y un bus que guarda los eventos."""
    tracker = TokenTracker()
    planner = PlannerSimulado(tracker, plan)
    generator = GeneratorSimulado(tracker)
    if isinstance(reviewer, list):
        reviewer = ReviewerGuionado(tracker, reviewer)
    orquestador = Orquestador(
        planner, generator, reviewer, bus=BusEventos(), tracker=tracker, **opciones
    )
    return orquestador, planner, generator, reviewer


def plan_grabado() -> list[dict]:
    return json.loads(FakeLLMClient().generar("plan", rol="planner").contenido)


# --- Criterio 5: evidencia de aceptación ----------------------------------------


def test_camino_feliz_planificar_generar_revisar_fin() -> None:
    orquestador, planner, _, _ = armar(["accept"])

    resultado = orquestador.ejecutar(MODULO)

    assert resultado.traza_estados == [
        E.PLANIFICAR,
        E.GENERAR,
        E.EJECUTAR_REVISAR,
        E.FIN,
    ]
    assert resultado.estado_final is E.FIN
    assert resultado.motivo_fallo is None
    assert planner.llamadas == 1
    [objetivo] = resultado.objetivos
    assert (objetivo.objetivo, objetivo.decision, objetivo.intentos) == (
        "duplicar",
        "accept",
        1,
    )
    assert objetivo.cobertura == {"lineas": 100.0, "ramas": 100.0}


def test_timeout_del_sandbox_termina_en_fallo_controlado_sin_colgar() -> None:
    orquestador, *_ = armar(ReviewerSandboxTimeout())

    inicio = time.monotonic()
    resultado = orquestador.ejecutar(MODULO)

    assert time.monotonic() - inicio < 2
    assert resultado.estado_final is E.FALLO_CONTROLADO
    assert resultado.traza_estados[-2:] == [E.EJECUTAR_REVISAR, E.FALLO_CONTROLADO]
    assert "timeout" in resultado.motivo_fallo
    assert resultado.objetivos[0].decision is None  # se conserva lo avanzado


# --- Criterio 1: reintentos y estados -------------------------------------------


def test_retry_pasa_por_reintentar_y_no_vuelve_a_planificar() -> None:
    orquestador, planner, generator, reviewer = armar(["retry", "accept"])

    resultado = orquestador.ejecutar(MODULO)

    assert resultado.traza_estados == [
        E.PLANIFICAR,
        E.GENERAR,
        E.EJECUTAR_REVISAR,
        E.REINTENTAR,
        E.GENERAR,
        E.EJECUTAR_REVISAR,
        E.FIN,
    ]
    assert planner.llamadas == 1
    assert generator.feedbacks == [None, "ImportError en el intento 1"]
    assert reviewer.tests_anteriores[0] is None
    assert reviewer.tests_anteriores[1]["intento"] == 1
    assert resultado.objetivos[0].decision == "accept"
    assert resultado.objetivos[0].intentos == 2


def test_tres_intentos_fallidos_terminan_en_stalled() -> None:
    orquestador, *_ = armar(["retry", "retry", "stalled"])

    resultado = orquestador.ejecutar(MODULO)

    assert resultado.estado_final is E.FIN
    assert resultado.traza_estados.count(E.REINTENTAR) == 2
    assert resultado.objetivos[0].decision == "stalled"
    assert resultado.objetivos[0].intentos == 3


def test_max_intentos_menor_convierte_retry_en_stalled() -> None:
    orquestador, *_ = armar(["retry"], max_intentos=1)

    resultado = orquestador.ejecutar(MODULO)

    assert resultado.estado_final is E.FIN
    assert resultado.objetivos[0].decision == "stalled"
    assert E.REINTENTAR not in resultado.traza_estados


def test_bug_detectado_no_se_reintenta() -> None:
    orquestador, *_ = armar(["bug_detectado"])

    resultado = orquestador.ejecutar(MODULO)

    assert resultado.estado_final is E.FIN
    assert resultado.objetivos[0].decision == "bug_detectado"
    assert E.REINTENTAR not in resultado.traza_estados


def test_varios_objetivos_se_procesan_en_orden() -> None:
    segundo = copy.deepcopy(plan_grabado()[0])
    segundo["objetivo"] = "triplicar"
    orquestador, *_ = armar(
        ["accept", "bug_detectado"], plan=[*plan_grabado(), segundo]
    )

    resultado = orquestador.ejecutar(MODULO)

    assert [o.objetivo for o in resultado.objetivos] == ["duplicar", "triplicar"]
    assert resultado.traza_estados.count(E.GENERAR) == 2
    assert resultado.estado_final is E.FIN


def test_plan_vacio_termina_en_fin() -> None:
    orquestador, *_ = armar([], plan=[])

    resultado = orquestador.ejecutar(MODULO)

    assert resultado.traza_estados == [E.PLANIFICAR, E.FIN]


def test_transicion_no_permitida() -> None:
    with pytest.raises(TransicionInvalida):
        validar_transicion(E.REINTENTAR, E.PLANIFICAR)  # un reintento no rehace el plan
    with pytest.raises(TransicionInvalida):
        validar_transicion(E.FIN, E.GENERAR)
    assert all(not TRANSICIONES[t] for t in (E.FIN, E.FALLO_CONTROLADO))


# --- Criterio 2: solo contratos de EN-01 ----------------------------------------


def test_planner_que_rompe_el_contrato_termina_en_fallo_controlado() -> None:
    plan = plan_grabado()
    plan[0]["casos"][0]["origen"] = "ejecucion"  # oráculo prohibido
    orquestador, *_ = armar(["accept"], plan=plan)

    resultado = orquestador.ejecutar(MODULO)

    assert resultado.traza_estados == [E.PLANIFICAR, E.FALLO_CONTROLADO]
    assert "planner_contract.v2" in resultado.motivo_fallo


def test_reviewer_que_responde_por_otro_objetivo_es_fallo_controlado() -> None:
    class ReviewerConfundido(ReviewerGuionado):
        def revisar(self, contrato, test, test_anterior):
            respuesta = super().revisar(contrato, test, test_anterior)
            respuesta["objetivo"] = "otra_funcion"
            return respuesta

    tracker = TokenTracker()
    orquestador = Orquestador(
        PlannerSimulado(tracker),
        GeneratorSimulado(tracker),
        ReviewerConfundido(tracker, ["accept"]),
        tracker=tracker,
    )

    resultado = orquestador.ejecutar(MODULO)

    assert resultado.estado_final is E.FALLO_CONTROLADO
    assert "otra_funcion" in resultado.motivo_fallo


# --- Criterio 3: eventos para el Monitor ----------------------------------------


def test_emite_eventos_con_los_campos_del_monitor() -> None:
    orquestador, *_ = armar(["retry", "accept"])
    recibidos = []
    orquestador.bus.suscribir(recibidos.append)

    orquestador.ejecutar(MODULO)

    assert recibidos == orquestador.bus.historial
    for evento in recibidos:
        datos = evento.a_dict()
        assert {"agente", "archivo", "funcion", "mensaje", "hora"} <= datos.keys()
        assert datos["archivo"] == "modulo_simulado.py"
        assert datos["mensaje"]
        json.dumps(datos)  # serializable para la interfaz
    assert {e.agente for e in recibidos} == {
        "orquestador",
        "planner",
        "generator",
        "reviewer",
    }
    assert any(e.funcion == "duplicar" for e in recibidos)
    assert recibidos[-1].tipo == "fin"


def test_un_suscriptor_que_falla_no_detiene_la_corrida() -> None:
    orquestador, *_ = armar(["accept"])

    def monitor_roto(_evento):
        raise RuntimeError("la ventana se cerró")

    orquestador.bus.suscribir(monitor_roto)

    assert orquestador.ejecutar(MODULO).estado_final is E.FIN


# --- Criterio 4: errores del sandbox y agentes colgados -------------------------


def test_error_del_sandbox_termina_en_fallo_controlado() -> None:
    orquestador, *_ = armar(ReviewerSandboxCaido())

    resultado = orquestador.ejecutar(MODULO)

    assert resultado.estado_final is E.FALLO_CONTROLADO
    assert "ErrorSandbox" in resultado.motivo_fallo
    assert orquestador.bus.historial[-1].tipo == "fallo"


def test_agente_colgado_no_cuelga_la_corrida() -> None:
    orquestador, *_ = armar(ReviewerColgado(segundos=5), timeout_paso_s=0.2)

    inicio = time.monotonic()
    resultado = orquestador.ejecutar(MODULO)

    assert time.monotonic() - inicio < 2
    assert resultado.estado_final is E.FALLO_CONTROLADO
    assert "no respondió" in resultado.motivo_fallo


# --- Métricas y configuración ---------------------------------------------------


def test_tokens_por_agente_con_ia_simulada_son_cero() -> None:
    orquestador, *_ = armar(["retry", "accept"])

    resultado = orquestador.ejecutar(MODULO).a_dict()

    tokens = resultado["tokens_por_agente"]
    assert tokens["planner"]["llamadas"] == 1
    assert tokens["generator"]["llamadas"] == 2
    assert tokens["reviewer"]["llamadas"] == 2
    assert all(
        t["prompt_tokens"] == t["completion_tokens"] == 0 for t in tokens.values()
    )
    assert resultado["estado_final"] == "fin"
    json.dumps(resultado)


@pytest.mark.parametrize(
    "opciones", [{"max_intentos": 0}, {"max_intentos": 4}, {"timeout_paso_s": 0}]
)
def test_configuracion_invalida(opciones) -> None:
    with pytest.raises(ValueError):
        armar(["accept"], **opciones)
