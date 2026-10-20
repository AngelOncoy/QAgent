"""Integración de tiempos reales (#115) con límites de tokens (PR #121)."""

from __future__ import annotations

from typing import Any

from qagent.llm import TokenTracker
from qagent.orchestrator import BusEventos, Estado, Orquestador
from qagent.orchestrator.corrida import ResumenCorrida, _registrar_limite_tokens
from qagent.orchestrator.orquestador import LIMITE_TOKENS
from tests.orchestrator.fakes import MODULO
from tests.orchestrator.test_issue115_tiempos import AhoraFalsa, RelojFalso
from tests.orchestrator.test_limite_tokens import (
    GeneratorInstrumentado,
    PlannerInstrumentado,
    ReviewerInstrumentado,
    crear_plan_dos_objetivos,
)


class PlannerMedido(PlannerInstrumentado):
    def __init__(self, tracker: TokenTracker, reloj: RelojFalso, plan: list[dict]):
        super().__init__(tracker, plan, tokens=100)
        self.reloj = reloj

    def planificar(self, modulo: dict[str, Any]) -> list[dict[str, Any]]:
        self.reloj.avanzar(0.5)
        return super().planificar(modulo)


class GeneratorMedido(GeneratorInstrumentado):
    def __init__(self, tracker: TokenTracker, reloj: RelojFalso):
        super().__init__(tracker, tokens_por_llamada=200)
        self.reloj = reloj

    def generar(
        self, contrato: dict[str, Any], intento: int, feedback: str | None
    ) -> dict[str, Any]:
        self.reloj.avanzar(1.0)
        return super().generar(contrato, intento, feedback)


class ReviewerMedido(ReviewerInstrumentado):
    def __init__(
        self, tracker: TokenTracker, reloj: RelojFalso, decisiones: list[str]
    ) -> None:
        super().__init__(tracker, decisiones, tokens_por_llamada=150)
        self.reloj = reloj

    def revisar(
        self,
        contrato: dict[str, Any],
        test: dict[str, Any],
        test_anterior: dict[str, Any] | None,
    ) -> dict[str, Any]:
        self.reloj.avanzar(2.0)
        return super().revisar(contrato, test, test_anterior)


def _armar(
    decisiones: list[str], *, limite_tokens: int | None = None
) -> tuple[Orquestador, TokenTracker, RelojFalso, list]:
    reloj = RelojFalso()
    tracker = TokenTracker()
    eventos = []
    bus = BusEventos()
    bus.suscribir(eventos.append)
    plan = crear_plan_dos_objetivos()[:1]
    orquestador = Orquestador(
        PlannerMedido(tracker, reloj, plan),
        GeneratorMedido(tracker, reloj),
        ReviewerMedido(tracker, reloj, decisiones),
        bus=bus,
        tracker=tracker,
        limite_tokens=limite_tokens,
        reloj=reloj,
        ahora=AhoraFalsa(),
    )
    return orquestador, tracker, reloj, eventos


def test_caso_a_corrida_normal_sin_limite_conserva_tiempos() -> None:
    orquestador, tracker, _, _ = _armar(["accept"])

    resultado = orquestador.ejecutar(MODULO)

    [objetivo] = resultado.objetivos
    assert resultado.estado_final == Estado.FIN
    assert resultado.duracion_s == 3.5
    assert objetivo.duracion_s == 3.0
    assert objetivo.fin is not None
    assert tracker.total_tokens == 450


def test_caso_b_presupuesto_suficiente_expone_tokens_y_tiempos() -> None:
    orquestador, tracker, _, eventos = _armar(["accept"], limite_tokens=1000)

    resultado = orquestador.ejecutar(MODULO)

    veredicto = next(evento for evento in eventos if evento.tipo == "veredicto")
    assert resultado.estado_final == Estado.FIN
    assert tracker.total_tokens == 450
    assert veredicto.transcurrido_s == 3.5
    assert veredicto.duracion_objetivo_s == 3.0
    assert veredicto.etapas_s["generator"] == 1.0


def test_caso_c_presupuesto_agotado_cierra_tiempos_y_evitar_reintento() -> None:
    orquestador, tracker, _, eventos = _armar(["retry", "accept"], limite_tokens=350)

    resultado = orquestador.ejecutar(MODULO)

    [objetivo] = resultado.objetivos
    assert objetivo.decision == "stalled"
    assert objetivo.motivo_estancado == LIMITE_TOKENS
    assert objetivo.intentos == 1
    assert objetivo.duracion_s == 3.0
    assert objetivo.fin is not None
    assert len(objetivo.tiempos_intentos) == 1
    assert tracker.total_tokens == 450
    assert any(
        evento.tipo == "aviso"
        and evento.datos
        and evento.datos.get("alerta_presupuesto") is True
        for evento in eventos
    )
    resumen = ResumenCorrida(None, "fin", None, 1)
    assert _registrar_limite_tokens(resumen, resultado, 350) is True
    assert resumen.estado == "fallo_controlado"
    assert "presupuesto de tokens" in (resumen.motivo or "").lower()


def test_caso_d_reintentos_no_duplican_tiempo_ni_tokens() -> None:
    orquestador, tracker, _, _ = _armar(["retry", "accept"], limite_tokens=1000)

    resultado = orquestador.ejecutar(MODULO)

    [objetivo] = resultado.objetivos
    assert objetivo.intentos == 2
    assert [i["duracion_s"] for i in objetivo.tiempos_intentos] == [3.0, 3.0]
    assert objetivo.duracion_s == 6.0
    assert resultado.duracion_s == 6.5
    assert tracker.total_tokens == 800


def test_caso_f_error_tecnico_conserva_medicion_y_no_se_vuelve_exito() -> None:
    orquestador, tracker, _, _ = _armar(["accept"], limite_tokens=1000)

    def fallar(*_args: Any) -> dict[str, Any]:
        orquestador._reloj.avanzar(2.0)  # type: ignore[attr-defined]
        raise RuntimeError("fallo técnico simulado")

    orquestador.reviewer.revisar = fallar  # type: ignore[method-assign]
    resultado = orquestador.ejecutar(MODULO)

    [objetivo] = resultado.objetivos
    assert resultado.estado_final == Estado.FALLO_CONTROLADO
    assert "fallo técnico simulado" in (resultado.motivo_fallo or "")
    assert objetivo.decision is None
    assert objetivo.duracion_s == 3.0
    assert objetivo.fin is not None
    assert tracker.total_tokens == 300
