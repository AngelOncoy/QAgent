"""#115: mediciÃ³n real de tiempos con relojes inyectados (sin dormir)."""

from __future__ import annotations

from typing import Any

from qagent.llm import TokenTracker
from qagent.orchestrator.eventos import BusEventos
from qagent.orchestrator.orquestador import Orquestador
from qagent.orchestrator.tiempos import etapas_vacias
from tests.orchestrator.fakes import (
    MODULO,
    GeneratorSimulado,
    PlannerSimulado,
    veredicto,
)


class RelojFalso:
    """Reloj monotÃ³nico que solo avanza cuando un doble lo pide."""

    def __init__(self) -> None:
        self.valor = 0.0

    def __call__(self) -> float:
        return self.valor

    def avanzar(self, segundos: float) -> None:
        self.valor += segundos


class AhoraFalsa:
    """Marca UTC correlativa: no depende de la hora de la mÃ¡quina."""

    def __init__(self) -> None:
        self.minuto = 0

    def __call__(self) -> str:
        self.minuto += 1
        return f"2026-10-20T12:{self.minuto:02d}:00Z"


def _ejecucion(sandbox_s: float, pytest_s: float | None) -> dict[str, Any]:
    return {
        "exit_code": 0,
        "duracion_s": sandbox_s,
        "duracion_pytest_s": pytest_s,
        "salida": "1 passed",
        "totales": {
            "total": 1,
            "pasaron": 1,
            "fallaron": 0,
            "errores": 0,
            "omitidos": 0,
        },
        "casos": [],
        "entorno": {
            "imagen": "qagent-sandbox:base",
            "comando": "pytest",
            "limites": {"cpus": 1.0, "memoria": "1g", "timeout_s": 60},
        },
    }


class PlannerReloj(PlannerSimulado):
    def __init__(self, tracker: TokenTracker, reloj: RelojFalso) -> None:
        super().__init__(tracker)
        self.reloj = reloj

    def planificar(self, modulo: dict[str, Any]) -> list[dict]:
        self.reloj.avanzar(0.5)
        return super().planificar(modulo)


class GeneratorReloj(GeneratorSimulado):
    def __init__(self, tracker: TokenTracker, reloj: RelojFalso) -> None:
        super().__init__(tracker)
        self.reloj = reloj

    def generar(self, contrato: dict, intento: int, feedback: str | None) -> dict:
        self.reloj.avanzar(1.0)
        return super().generar(contrato, intento, feedback)


class ReviewerReloj:
    """Cada revisiÃ³n tarda 2 s; el sandbox y pytest traen su propio desglose."""

    def __init__(self, reloj: RelojFalso, decisiones: list[str]) -> None:
        self.reloj = reloj
        self.decisiones = list(decisiones)

    def revisar(self, contrato: dict, test: dict, test_anterior: dict | None) -> dict:
        self.reloj.avanzar(2.0)
        resultado = veredicto(
            contrato["objetivo"],
            test["intento"],
            self.decisiones.pop(0),
            ejecucion=_ejecucion(0.75, 0.25),
        )
        return resultado


def _armar(decisiones: list[str]) -> tuple[Orquestador, RelojFalso, AhoraFalsa]:
    reloj = RelojFalso()
    ahora = AhoraFalsa()
    tracker = TokenTracker()
    orquestador = Orquestador(
        PlannerReloj(tracker, reloj),
        GeneratorReloj(tracker, reloj),
        ReviewerReloj(reloj, decisiones),
        bus=BusEventos(),
        tracker=tracker,
        reloj=reloj,
        ahora=ahora,
    )
    return orquestador, reloj, ahora


def test_mide_etapas_y_duracion_del_objetivo() -> None:
    orquestador, _, _ = _armar(["accept"])

    resultado = orquestador.ejecutar(MODULO)

    [objetivo] = resultado.objetivos
    assert resultado.duracion_s == 3.5
    assert resultado.duracion_etapas == {
        "planner": 0.5,
        "generator": 1.0,
        "reviewer": 2.0,
        "sandbox": 0.75,
        "pytest": 0.25,
    }
    assert (objetivo.duracion_generacion_s, objetivo.duracion_revision_s) == (
        1.0,
        2.0,
    )
    assert (objetivo.duracion_sandbox_s, objetivo.duracion_pytest_s) == (
        0.75,
        0.25,
    )
    assert objetivo.duracion_s == 3.0


def test_mide_cada_intento_y_suma_reintentos() -> None:
    orquestador, _, _ = _armar(["retry", "accept"])

    resultado = orquestador.ejecutar(MODULO)

    [objetivo] = resultado.objetivos
    assert objetivo.intentos == 2
    assert [t["intento"] for t in objetivo.tiempos_intentos] == [1, 2]
    assert [t["duracion_s"] for t in objetivo.tiempos_intentos] == [3.0, 3.0]
    assert objetivo.duracion_generacion_s == 2.0
    assert objetivo.duracion_revision_s == 4.0
    assert objetivo.duracion_s == 6.0


def test_marcas_de_inicio_y_fin_son_utc_y_correlativas() -> None:
    orquestador, _, _ = _armar(["accept"])

    resultado = orquestador.ejecutar(MODULO)

    [objetivo] = resultado.objetivos
    assert resultado.inicio == "2026-10-20T12:02:00Z"
    assert resultado.fin > resultado.inicio
    assert objetivo.inicio is not None
    assert objetivo.fin >= objetivo.inicio
    assert resultado.inicio <= objetivo.inicio <= objetivo.fin <= resultado.fin


def test_eventos_llevan_medicion_sin_cambiar_el_contrato_datos() -> None:
    orquestador, _, _ = _armar(["accept"])
    eventos = []
    orquestador.bus.suscribir(eventos.append)

    orquestador.ejecutar(MODULO)

    veredicto_final = next(e for e in eventos if e.tipo == "veredicto")
    assert veredicto_final.datos == {"decision": "accept", "intento": 1}
    assert veredicto_final.inicio_corrida == "2026-10-20T12:02:00Z"
    assert veredicto_final.transcurrido_s == 3.5
    assert veredicto_final.inicio_objetivo is not None
    assert veredicto_final.duracion_objetivo_s == 3.0
    assert veredicto_final.etapas_s == {
        "planner": 0.5,
        "generator": 1.0,
        "reviewer": 2.0,
        "sandbox": 0.75,
        "pytest": 0.25,
    }


def test_sin_ejecucion_no_inventa_tiempo_de_sandbox() -> None:
    class ReviewerSinEjecucion(ReviewerReloj):
        def revisar(self, contrato, test, test_anterior):
            self.reloj.avanzar(2.0)
            return veredicto(
                contrato["objetivo"], test["intento"], self.decisiones.pop(0)
            )

    reloj = RelojFalso()
    tracker = TokenTracker()
    orquestador = Orquestador(
        PlannerReloj(tracker, reloj),
        GeneratorReloj(tracker, reloj),
        ReviewerSinEjecucion(reloj, ["accept"]),
        tracker=tracker,
        reloj=reloj,
        ahora=AhoraFalsa(),
    )

    [objetivo] = orquestador.ejecutar(MODULO).objetivos

    assert objetivo.duracion_sandbox_s == 0.0
    assert objetivo.duracion_pytest_s == 0.0


def test_etapas_vacias_no_se_comparten_entre_objetivos() -> None:
    primera, segunda = etapas_vacias(), etapas_vacias()
    primera["planner"] = 9.0

    assert segunda["planner"] == 0.0


def test_el_monitor_recibe_los_tiempos_del_backend() -> None:
    from qagent.app.monitor_eventos import a_fila_monitor

    fila = a_fila_monitor(
        {
            "agente": "reviewer",
            "archivo": "a.py",
            "funcion": "duplicar",
            "mensaje": "Veredicto: accept",
            "tipo": "veredicto",
            "datos": {"decision": "accept", "intento": 1},
            "inicio_corrida": "2026-10-20T12:00:00Z",
            "transcurrido_s": 3.5,
            "etapas_s": {"planner": 0.5},
            "inicio_objetivo": "2026-10-20T12:00:01Z",
            "duracion_objetivo_s": 3.0,
        }
    )

    assert fila is not None
    assert fila["inicio_corrida"] == "2026-10-20T12:00:00Z"
    assert fila["transcurrido_s"] == 3.5
    assert fila["etapas_s"] == {"planner": 0.5}
    assert fila["inicio_objetivo"] == "2026-10-20T12:00:01Z"
    assert fila["duracion_objetivo_s"] == 3.0


def test_el_monitor_no_inventa_tiempos_si_el_evento_no_los_trae() -> None:
    from qagent.app.monitor_eventos import a_fila_monitor

    fila = a_fila_monitor({"agente": "planner", "mensaje": "Plan con 1"})

    assert fila is not None
    assert fila["transcurrido_s"] is None
    assert fila["duracion_objetivo_s"] is None
    assert fila["etapas_s"] is None
