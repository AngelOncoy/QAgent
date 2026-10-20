"""Pruebas del límite de tokens, alertas de presupuesto y detención controlada."""

from __future__ import annotations

import copy
import json
import threading
from typing import Any

from qagent.llm import FakeLLMClient, TokenTracker
from qagent.orchestrator import BusEventos, Estado, Evento, Orquestador
from qagent.orchestrator.orquestador import LIMITE_TOKENS
from tests.orchestrator.fakes import MODULO, veredicto


def crear_plan_dos_objetivos() -> list[dict[str, Any]]:
    """Genera dos contratos v2 válidos para simular múltiples objetivos."""
    base = json.loads(FakeLLMClient().generar("plan", rol="planner").contenido)[0]
    obj1 = copy.deepcopy(base)
    obj1["objetivo"] = "primera_funcion"

    obj2 = copy.deepcopy(base)
    obj2["objetivo"] = "segunda_funcion"
    return [obj1, obj2]


class PlannerInstrumentado:
    """Planner que simula consumo de tokens configurable."""

    def __init__(
        self,
        tracker: TokenTracker,
        plan: list[dict[str, Any]],
        tokens: int = 100,
        es_estimado: bool = False,
    ) -> None:
        self.tracker = tracker
        self.plan = plan
        self.tokens = tokens
        self.es_estimado = es_estimado
        self.llamadas = 0

    def planificar(self, modulo: dict[str, Any]) -> list[dict[str, Any]]:
        self.llamadas += 1
        mitad = self.tokens // 2
        self.tracker.registrar(
            "planner",
            "modelo-test",
            mitad,
            self.tokens - mitad,
            es_estimado=self.es_estimado,
        )
        return copy.deepcopy(self.plan)


class GeneratorInstrumentado:
    """Generator que simula consumo de tokens configurable y cuenta llamadas."""

    def __init__(
        self,
        tracker: TokenTracker,
        tokens_por_llamada: int = 200,
        es_estimado: bool = False,
    ) -> None:
        self.tracker = tracker
        self.tokens_por_llamada = tokens_por_llamada
        self.es_estimado = es_estimado
        self.llamadas = 0
        self.objetivos_llamados: list[str] = []

    def generar(
        self, contrato: dict[str, Any], intento: int, feedback: str | None
    ) -> dict[str, Any]:
        self.llamadas += 1
        self.objetivos_llamados.append(contrato["objetivo"])
        mitad = self.tokens_por_llamada // 2
        self.tracker.registrar(
            "generator",
            "modelo-test",
            mitad,
            self.tokens_por_llamada - mitad,
            es_estimado=self.es_estimado,
        )
        return {
            "version": "1",
            "objetivo": contrato["objetivo"],
            "intento": intento,
            "codigo": "def test_ok(): assert True",
            "casos_cubiertos": [c["id"] for c in contrato["casos"]],
        }


class ReviewerInstrumentado:
    """Reviewer que responde según una lista de decisiones y registra tokens."""

    def __init__(
        self,
        tracker: TokenTracker,
        decisiones: list[str],
        tokens_por_llamada: int = 150,
        es_estimado: bool = False,
    ) -> None:
        self.tracker = tracker
        self.decisiones = list(decisiones)
        self.tokens_por_llamada = tokens_por_llamada
        self.es_estimado = es_estimado
        self.llamadas = 0
        self.objetivos_llamados: list[str] = []

    def revisar(
        self,
        contrato: dict[str, Any],
        test: dict[str, Any],
        test_anterior: dict[str, Any] | None,
    ) -> dict[str, Any]:
        self.llamadas += 1
        self.objetivos_llamados.append(contrato["objetivo"])
        mitad = self.tokens_por_llamada // 2
        self.tracker.registrar(
            "reviewer",
            "modelo-test",
            mitad,
            self.tokens_por_llamada - mitad,
            es_estimado=self.es_estimado,
        )
        decision = self.decisiones.pop(0) if self.decisiones else "accept"
        return veredicto(contrato["objetivo"], test["intento"], decision)


def test_alerta_presupuesto_al_80_por_ciento() -> None:
    """Verifica que se emita una advertencia al alcanzar el 80% del límite de tokens."""
    tracker = TokenTracker()
    eventos: list[Evento] = []
    bus = BusEventos()
    bus.suscribir(eventos.append)

    plan = crear_plan_dos_objetivos()[:1]
    # Planner: 300 tokens, Generator: 350 tokens -> total 650 tokens.
    # Límite: 800 tokens. 80 % son 640 tokens.
    planner = PlannerInstrumentado(tracker, plan, tokens=300)
    generator = GeneratorInstrumentado(tracker, tokens_por_llamada=350)
    reviewer = ReviewerInstrumentado(tracker, ["accept"], tokens_por_llamada=50)

    orquestador = Orquestador(
        planner=planner,
        generator=generator,
        reviewer=reviewer,
        bus=bus,
        tracker=tracker,
        limite_tokens=800,
    )

    resultado = orquestador.ejecutar(MODULO)

    assert resultado.estado_final == Estado.FIN
    avisos_80 = [
        e
        for e in eventos
        if e.tipo == "aviso"
        and isinstance(e.datos, dict)
        and e.datos.get("alerta_presupuesto") is True
    ]
    # Se emitió al menos una alerta y no se duplica innecesariamente
    assert len(avisos_80) == 1
    aviso = avisos_80[0]
    assert aviso.datos["limite_tokens"] == 800
    assert aviso.datos["porcentaje"] >= 80
    assert "80 %" in aviso.mensaje or f"{aviso.datos['porcentaje']} %" in aviso.mensaje


def test_limite_tokens_corta_reintentos_y_evita_llamadas_innecesarias() -> None:
    """Cuando un objetivo pide retry pero se agotó el presupuesto, se corta a stalled."""
    tracker = TokenTracker()
    eventos: list[Evento] = []
    bus = BusEventos()
    bus.suscribir(eventos.append)

    plan = crear_plan_dos_objetivos()[:1]
    # Planner: 100, Gen 1: 150, Rev 1: 150 -> Total: 400 tokens.
    # Límite: 350 tokens.
    planner = PlannerInstrumentado(tracker, plan, tokens=100)
    generator = GeneratorInstrumentado(tracker, tokens_por_llamada=150)
    # Reviewer pide 'retry', pero el presupuesto ya fue superado
    reviewer = ReviewerInstrumentado(
        tracker, ["retry", "accept"], tokens_por_llamada=150
    )

    orquestador = Orquestador(
        planner=planner,
        generator=generator,
        reviewer=reviewer,
        bus=bus,
        tracker=tracker,
        limite_tokens=350,
    )

    resultado = orquestador.ejecutar(MODULO)

    # El objetivo debe quedar estancado por límite de tokens
    assert len(resultado.objetivos) == 1
    obj = resultado.objetivos[0]
    assert obj.decision == "stalled"
    assert obj.motivo_estancado == LIMITE_TOKENS
    assert obj.intentos == 1

    # Criterio: No se realizan llamadas LLM innecesarias tras alcanzar el límite
    assert generator.llamadas == 1
    assert reviewer.llamadas == 1


def test_limite_tokens_evita_iniciar_nuevos_objetivos_y_conserva_resultados() -> None:
    """Al alcanzar el límite, no se inician nuevos objetivos y se conservan los aprobados."""
    tracker = TokenTracker()
    plan = crear_plan_dos_objetivos()
    # Planner: 100.
    # Objetivo 1: Gen 1 (150) + Rev 1 (150) -> 300 tokens -> Total acumulado 400.
    # Con límite 350, Objetivo 1 termina (accept), pero Objetivo 2 no debe iniciar.
    planner = PlannerInstrumentado(tracker, plan, tokens=100)
    generator = GeneratorInstrumentado(tracker, tokens_por_llamada=150)
    reviewer = ReviewerInstrumentado(
        tracker, ["accept", "accept"], tokens_por_llamada=150
    )

    orquestador = Orquestador(
        planner=planner,
        generator=generator,
        reviewer=reviewer,
        tracker=tracker,
        limite_tokens=350,
    )

    resultado = orquestador.ejecutar(MODULO)

    assert resultado.estado_final == Estado.FALLO_CONTROLADO
    assert "presupuesto de tokens" in (resultado.motivo_fallo or "").lower()

    # Se conserva el resultado válido ya procesado
    assert len(resultado.objetivos) == 1
    assert resultado.objetivos[0].objetivo == "primera_funcion"
    assert resultado.objetivos[0].decision == "accept"

    # El segundo objetivo nunca se inició ni se llamó a los agentes para él
    assert "segunda_funcion" not in generator.objetivos_llamados
    assert "segunda_funcion" not in reviewer.objetivos_llamados
    assert generator.llamadas == 1
    assert reviewer.llamadas == 1


def test_detencion_controlada_por_cancelacion_conserva_resultados() -> None:
    """La detención solicitada por el usuario detiene la ejecución y conserva lo completado."""
    tracker = TokenTracker()
    plan = crear_plan_dos_objetivos()
    evento_cancelar = threading.Event()

    planner = PlannerInstrumentado(tracker, plan, tokens=50)
    generator = GeneratorInstrumentado(tracker, tokens_por_llamada=50)

    class ReviewerConCancelacion(ReviewerInstrumentado):
        def revisar(self, contrato, test, test_anterior):
            res = super().revisar(contrato, test, test_anterior)
            # Tras revisar el primer objetivo, el usuario pulsa detener
            if contrato["objetivo"] == "primera_funcion":
                evento_cancelar.set()
            return res

    reviewer = ReviewerConCancelacion(
        tracker, ["accept", "accept"], tokens_por_llamada=50
    )

    orquestador = Orquestador(
        planner=planner,
        generator=generator,
        reviewer=reviewer,
        tracker=tracker,
        cancelado=evento_cancelar.is_set,
    )

    resultado = orquestador.ejecutar(MODULO)

    assert resultado.estado_final == Estado.FALLO_CONTROLADO
    assert "detenida por el usuario" in (resultado.motivo_fallo or "").lower()

    # Se conserva el resultado válido procesado antes de la detención
    assert len(resultado.objetivos) == 1
    assert resultado.objetivos[0].objetivo == "primera_funcion"
    assert resultado.objetivos[0].decision == "accept"
    assert "segunda_funcion" not in generator.objetivos_llamados


def test_diferenciacion_tokens_reales_y_estimados_en_resultado() -> None:
    """Comprueba que el tracker distinga tokens reales y estimados en la corrida."""
    tracker = TokenTracker()
    plan = crear_plan_dos_objetivos()[:1]

    # Planner produce tokens reales (100)
    planner = PlannerInstrumentado(tracker, plan, tokens=100, es_estimado=False)
    # Generator produce tokens estimados (200)
    generator = GeneratorInstrumentado(
        tracker, tokens_por_llamada=200, es_estimado=True
    )
    # Reviewer produce tokens reales (150)
    reviewer = ReviewerInstrumentado(
        tracker, ["accept"], tokens_por_llamada=150, es_estimado=False
    )

    orquestador = Orquestador(
        planner=planner,
        generator=generator,
        reviewer=reviewer,
        tracker=tracker,
    )

    resultado = orquestador.ejecutar(MODULO)

    assert resultado.estado_final == Estado.FIN
    assert tracker.total_tokens == 450
    assert tracker.total_tokens_reales == 250
    assert tracker.total_tokens_estimados == 200
