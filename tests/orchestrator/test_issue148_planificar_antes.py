"""Planificar un módulo antes de ejecutarlo (#148), con la IA simulada y sin Docker.

`Orquestador.planificar` solo llama al Planner, así la corrida puede planificar
mientras se construye el entorno aislado; `ejecutar(..., plan_previo=...)` usa ese plan
sin volver a llamar al Planner.
"""

from __future__ import annotations

from qagent.llm import TokenTracker
from qagent.orchestrator import BusEventos, Estado, Orquestador, PlanModulo
from tests.orchestrator.fakes import (
    MODULO,
    GeneratorSimulado,
    PlannerSimulado,
    ReviewerGuionado,
)

E = Estado


class PlannerQueFalla(PlannerSimulado):
    """Planner cuya respuesta no es una lista de contratos."""

    def planificar(self, modulo):  # type: ignore[override]
        self.llamadas += 1
        return {"no": "es una lista"}


def armar(decisiones, planner_cls=PlannerSimulado):
    tracker = TokenTracker()
    planner = planner_cls(tracker)
    generator = GeneratorSimulado(tracker)
    reviewer = ReviewerGuionado(tracker, decisiones)
    eventos = []
    bus = BusEventos()
    bus.suscribir(eventos.append)
    orquestador = Orquestador(planner, generator, reviewer, bus=bus, tracker=tracker)
    return orquestador, planner, generator, reviewer, eventos


def test_planificar_solo_llama_al_planner() -> None:
    orquestador, planner, generator, _, _ = armar(["accept"])

    plan = orquestador.planificar(MODULO)

    assert isinstance(plan, PlanModulo)
    assert plan.modulo == MODULO["ruta"]
    assert plan.error is None
    assert [c["objetivo"] for c in plan.contratos] == ["duplicar"]
    assert planner.llamadas == 1
    assert generator.feedbacks == []  # el Generator no se llamó


def test_ejecutar_con_plan_previo_no_vuelve_a_planificar() -> None:
    orquestador, planner, _, _, _ = armar(["accept"])
    plan = orquestador.planificar(MODULO)

    resultado = orquestador.ejecutar(MODULO, plan_previo=plan)

    assert planner.llamadas == 1
    assert resultado.traza_estados == [
        E.PLANIFICAR,
        E.GENERAR,
        E.EJECUTAR_REVISAR,
        E.FIN,
    ]
    assert [o.decision for o in resultado.objetivos] == ["accept"]
    assert [c["objetivo"] for c in resultado.plan_completo] == ["duplicar"]
    assert resultado.inicio == plan.inicio


def test_mismos_eventos_que_ejecutar_directo() -> None:
    directo, *_, eventos_directo = armar(["accept"])
    directo.ejecutar(MODULO)
    separado, *_, eventos_separado = armar(["accept"])
    separado.ejecutar(MODULO, plan_previo=separado.planificar(MODULO))

    assert [(e.agente, e.mensaje, e.estado) for e in eventos_separado] == [
        (e.agente, e.mensaje, e.estado) for e in eventos_directo
    ]


def test_planificar_otro_modulo_no_mezcla_el_estado() -> None:
    orquestador, planner, _, _, _ = armar(["accept"])
    otro = {**MODULO, "ruta": "otro.py"}

    plan = orquestador.planificar(MODULO)
    orquestador.planificar(otro)
    resultado = orquestador.ejecutar(MODULO, plan_previo=plan)

    assert planner.llamadas == 2
    assert resultado.modulo == MODULO["ruta"]
    assert resultado.estado_final is E.FIN
    assert resultado.traza_estados[0] is E.PLANIFICAR


def test_fallo_al_planificar_se_reporta_al_ejecutar() -> None:
    orquestador, _, generator, _, _ = armar(["accept"], PlannerQueFalla)

    plan = orquestador.planificar(MODULO)  # no lanza
    resultado = orquestador.ejecutar(MODULO, plan_previo=plan)

    assert plan.error is not None
    assert resultado.estado_final is E.FALLO_CONTROLADO
    assert "lista de contratos" in resultado.motivo_fallo
    assert resultado.traza_estados == [E.PLANIFICAR, E.FALLO_CONTROLADO]
    assert generator.feedbacks == []
