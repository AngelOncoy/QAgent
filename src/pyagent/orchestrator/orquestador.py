"""Orquestador de la corrida: máquina de estados que coordina a los 3 agentes (EN-04).

planificar -> generar -> ejecutar y revisar -> [reintentar -> generar ...] -> fin
Cualquier timeout o error del sandbox (o de un agente) termina en fallo controlado,
sin colgar la corrida y devolviendo lo que se alcanzó a procesar.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any, TypeVar

from pyagent import contracts
from pyagent.contracts import ContratoInvalido
from pyagent.llm.tracker import TokenTracker
from pyagent.orchestrator.estados import Estado, validar_transicion
from pyagent.orchestrator.eventos import BusEventos, Evento
from pyagent.orchestrator.puertos import Contrato, Generator, Planner, Reviewer

T = TypeVar("T")

MAX_INTENTOS_CONTRATO = 3  # tope de generated_test/review_result (EN-01)
TIMEOUT_PASO_POR_DEFECTO_S = 120.0  # mayor que el timeout del sandbox (60 s)
SANDBOX_FALLIDO = frozenset({"timeout", "error"})
DECISIONES_FINALES = frozenset({"accept", "bug_detectado", "stalled"})


class FalloControlado(Exception):
    """Motivo por el que la corrida termina en FALLO_CONTROLADO."""


class TimeoutPaso(FalloControlado):
    """Un agente no respondió dentro de `timeout_paso_s`."""


@dataclass
class ResultadoObjetivo:
    """Resultado de una función o endpoint del plan."""

    objetivo: str
    critical: bool
    decision: str | None = None
    intentos: int = 0
    cobertura: dict[str, Any] | None = None
    laundering_detectado: bool = False
    revisiones: list[Contrato] = field(default_factory=list)


@dataclass
class ResultadoCorrida:
    """Resultado de la corrida de un módulo."""

    modulo: str
    estado_final: Estado
    motivo_fallo: str | None
    objetivos: list[ResultadoObjetivo]
    traza_estados: list[Estado]
    tokens_por_agente: dict[str, dict[str, int]]
    duracion_s: float

    def a_dict(self) -> dict[str, Any]:
        """Versión serializable a JSON (insumo de log.json en EN-07)."""
        datos = asdict(self)
        datos["estado_final"] = self.estado_final.value
        datos["traza_estados"] = [e.value for e in self.traza_estados]
        return datos


class Orquestador:
    """Coordina Planner, Generator y Reviewer solo a través de contratos validados."""

    def __init__(
        self,
        planner: Planner,
        generator: Generator,
        reviewer: Reviewer,
        *,
        bus: BusEventos | None = None,
        tracker: TokenTracker | None = None,
        max_intentos: int = 3,
        timeout_paso_s: float = TIMEOUT_PASO_POR_DEFECTO_S,
    ) -> None:
        """Crea el orquestador.

        Args:
            planner, generator, reviewer: agentes que cumplen los `puertos`.
            bus: bus de eventos para el Monitor; si es None se crea uno.
            tracker: registro de tokens compartido con los agentes.
            max_intentos: intentos por objetivo (1 a 3, límite de los contratos).
            timeout_paso_s: tiempo máximo que se espera a un agente en cada paso.
        """
        if not 1 <= max_intentos <= MAX_INTENTOS_CONTRATO:
            raise ValueError(
                f"max_intentos debe estar entre 1 y {MAX_INTENTOS_CONTRATO}"
            )
        if timeout_paso_s <= 0:
            raise ValueError("timeout_paso_s debe ser mayor que 0")
        self.planner = planner
        self.generator = generator
        self.reviewer = reviewer
        self.bus = bus or BusEventos()
        self.tracker = tracker or TokenTracker()
        self.max_intentos = max_intentos
        self.timeout_paso_s = timeout_paso_s
        self._estado = Estado.PLANIFICAR
        self._traza: list[Estado] = []
        self._archivo: str | None = None

    @property
    def estado(self) -> Estado:
        """Estado actual de la máquina."""
        return self._estado

    def ejecutar(self, modulo: dict[str, Any]) -> ResultadoCorrida:
        """Ejecuta la corrida de un módulo (una entrada de `analizar_proyecto()["modulos"]`).

        Nunca lanza excepciones por fallos de agentes o del sandbox: los convierte en
        un `ResultadoCorrida` con estado FALLO_CONTROLADO y el motivo.
        """
        inicio = time.monotonic()
        self._archivo = modulo.get("ruta")
        self._estado = Estado.PLANIFICAR
        self._traza = [Estado.PLANIFICAR]
        self._emitir("orquestador", None, "Corrida iniciada", tipo="transicion")
        objetivos: list[ResultadoObjetivo] = []
        motivo: str | None = None

        try:
            plan = self._planificar(modulo)
            for contrato in plan:
                self._procesar_objetivo(contrato, objetivos)
            self._transicionar(Estado.FIN, None)
            self._emitir("orquestador", None, "Corrida terminada", tipo="fin")
        except FalloControlado as error:
            motivo = str(error)
            funcion = objetivos[-1].objetivo if objetivos else None  # el que falló
            self._transicionar(Estado.FALLO_CONTROLADO, funcion)
            self._emitir("orquestador", funcion, f"Fallo controlado: {motivo}", "fallo")

        self.tracker.fijar_contexto(None, None)
        return ResultadoCorrida(
            modulo=self._archivo or "",
            estado_final=self._estado,
            motivo_fallo=motivo,
            objetivos=objetivos,
            traza_estados=list(self._traza),
            tokens_por_agente=self._tokens_por_agente(),
            duracion_s=round(time.monotonic() - inicio, 3),
        )

    # --- Pasos de la máquina -----------------------------------------------------

    def _planificar(self, modulo: dict[str, Any]) -> list[Contrato]:
        self._emitir("planner", None, "Planificando módulo")
        self.tracker.fijar_contexto(None, None)  # el plan es por módulo
        plan = self._llamar("planner", self.planner.planificar, modulo)
        if not isinstance(plan, list):
            raise FalloControlado("El Planner no devolvió una lista de contratos")
        for contrato in plan:
            self._validar(contracts.PLANNER, contrato, "planner")
        self._emitir("planner", None, f"Plan con {len(plan)} objetivo(s)")
        return plan

    def _procesar_objetivo(
        self, contrato: Contrato, objetivos: list[ResultadoObjetivo]
    ) -> None:
        """Bucle generar -> ejecutar y revisar -> [reintentar] de un objetivo.

        El resultado se agrega a `objetivos` antes de empezar, para que un fallo
        controlado conserve lo avanzado (decision queda en None).
        """
        objetivo = contrato["objetivo"]
        resultado = ResultadoObjetivo(objetivo=objetivo, critical=contrato["critical"])
        objetivos.append(resultado)
        intento, feedback, test_anterior = 1, None, None

        while True:
            self._transicionar(Estado.GENERAR, objetivo)
            test = self._generar(contrato, intento, feedback)
            self._transicionar(Estado.EJECUTAR_REVISAR, objetivo)
            revision = self._revisar(contrato, test, test_anterior)

            resultado.intentos = intento
            resultado.revisiones.append(revision)
            resultado.cobertura = revision["cobertura"]
            resultado.laundering_detectado |= revision["laundering_detectado"]
            decision = revision["decision"]

            if decision == "retry" and intento >= self.max_intentos:
                decision = "stalled"  # max_intentos de config.toml menor que 3
            if decision in DECISIONES_FINALES:
                resultado.decision = decision
                self._emitir(
                    "reviewer", objetivo, f"Veredicto: {decision}", "veredicto"
                )
                return

            self._transicionar(Estado.REINTENTAR, objetivo)
            self._emitir("reviewer", objetivo, f"Reintento: {revision['feedback']}")
            intento, feedback, test_anterior = intento + 1, revision["feedback"], test

    def _generar(
        self, contrato: Contrato, intento: int, feedback: str | None
    ) -> Contrato:
        objetivo = contrato["objetivo"]
        self._emitir("generator", objetivo, f"Generando test (intento {intento})")
        self.tracker.fijar_contexto(objetivo, intento)
        test = self._llamar(
            "generator", self.generator.generar, contrato, intento, feedback
        )
        self._validar(contracts.GENERATED_TEST, test, "generator")
        self._coherente(test, objetivo, intento, "generator")
        return test

    def _revisar(
        self, contrato: Contrato, test: Contrato, test_anterior: Contrato | None
    ) -> Contrato:
        objetivo = contrato["objetivo"]
        self._emitir(
            "reviewer", objetivo, f"Ejecutando en sandbox (intento {test['intento']})"
        )
        self.tracker.fijar_contexto(objetivo, test["intento"])
        revision = self._llamar(
            "reviewer", self.reviewer.revisar, contrato, test, test_anterior
        )
        self._validar(contracts.REVIEW_RESULT, revision, "reviewer")
        self._coherente(revision, objetivo, test["intento"], "reviewer")
        if revision["estado_sandbox"] in SANDBOX_FALLIDO:
            raise FalloControlado(
                f"Sandbox con estado '{revision['estado_sandbox']}' en {objetivo}"
            )
        return revision

    # --- Utilidades -------------------------------------------------------------

    def _transicionar(self, destino: Estado, funcion: str | None) -> None:
        validar_transicion(self._estado, destino)
        self._estado = destino
        self._traza.append(destino)
        self._emitir("orquestador", funcion, f"Estado: {destino.value}", "transicion")

    def _llamar(self, agente: str, funcion: Callable[..., T], *args: Any) -> T:
        """Llama a un agente con tiempo máximo; traduce sus errores a FalloControlado.

        Usa un hilo daemon: si el agente se cuelga, la corrida sigue y el hilo no
        impide que el proceso termine.
        """
        salida: dict[str, Any] = {}

        def objetivo_hilo() -> None:
            try:
                salida["valor"] = funcion(*args)
            except BaseException as error:  # noqa: BLE001 — se reporta como fallo controlado
                salida["error"] = error

        hilo = threading.Thread(
            target=objetivo_hilo, name=f"qagent-{agente}", daemon=True
        )
        hilo.start()
        hilo.join(self.timeout_paso_s)
        if hilo.is_alive():
            raise TimeoutPaso(f"El {agente} no respondió en {self.timeout_paso_s:g} s")
        if "error" in salida:
            error = salida["error"]
            raise FalloControlado(
                f"Error en el {agente}: {type(error).__name__}: {error}"
            ) from error
        return salida["valor"]

    def _validar(self, nombre: str, dato: Any, agente: str) -> None:
        try:
            contracts.validar(nombre, dato)
        except ContratoInvalido as error:
            raise FalloControlado(f"El {agente} rompió el contrato: {error}") from error

    @staticmethod
    def _coherente(dato: Contrato, objetivo: str, intento: int, agente: str) -> None:
        if dato["objetivo"] != objetivo or dato["intento"] != intento:
            raise FalloControlado(
                f"El {agente} respondió por '{dato['objetivo']}' intento {dato['intento']}; "
                f"se esperaba '{objetivo}' intento {intento}"
            )

    def _emitir(
        self, agente: str, funcion: str | None, mensaje: str, tipo: str = "agente"
    ) -> None:
        self.bus.emitir(
            Evento(
                agente=agente,
                archivo=self._archivo,
                funcion=funcion,
                mensaje=mensaje,
                estado=self._estado.value,
                tipo=tipo,
            )
        )

    def _tokens_por_agente(self) -> dict[str, dict[str, int]]:
        totales: dict[str, dict[str, int]] = {}
        for llamada in self.tracker.llamadas:
            agente = totales.setdefault(
                llamada.agente,
                {"prompt_tokens": 0, "completion_tokens": 0, "llamadas": 0},
            )
            agente["prompt_tokens"] += llamada.tokens_entrada
            agente["completion_tokens"] += llamada.tokens_salida
            agente["llamadas"] += 1
        return totales
