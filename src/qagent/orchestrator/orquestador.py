"""Orquestador de la corrida: máquina de estados que coordina a los 3 agentes (EN-04).

planificar -> generar -> ejecutar y revisar -> [reintentar -> generar ...] -> fin
Cualquier timeout o error del sandbox (o de un agente) termina en fallo controlado,
sin colgar la corrida y devolviendo lo que se alcanzó a procesar.
"""

from __future__ import annotations

import copy
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any, TypeVar

from qagent import contracts
from qagent.agents.generator import ErrorRespuestaGenerator
from qagent.contracts import ContratoInvalido
from qagent.llm.tracker import TokenTracker
from qagent.orchestrator.estados import Estado, validar_transicion
from qagent.orchestrator.eventos import BusEventos, Evento
from qagent.orchestrator.puertos import Contrato, Generator, Planner, Reviewer

T = TypeVar("T")

MAX_INTENTOS_CONTRATO = 3  # tope de generated_test/review_result (EN-01)
TIMEOUT_PASO_POR_DEFECTO_S = 240.0  # mayor que el timeout del sandbox (120 s)
#: Lo que el paso del Reviewer espera además del sandbox: su llamada al LLM (90 s) y holgura.
MARGEN_PASO_SOBRE_SANDBOX_S = 120.0
SANDBOX_FALLIDO = frozenset({"timeout", "error"})
DECISIONES_FINALES = frozenset({"accept", "bug_detectado", "stalled"})
LIMITE_INTENTOS = "limite_intentos"  # motivos del corte (HU-14)
ERROR_REPETIDO = "error_repetido"
_TEXTO_MOTIVO = {
    LIMITE_INTENTOS: "límite de intentos",
    ERROR_REPETIDO: "mismo error repetido",
}


def timeout_paso_para(timeout_sandbox_s: float) -> float:
    """Tiempo máximo por paso para un sandbox con `timeout_sandbox_s` (`[sandbox]`).

    El paso del Reviewer incluye la ejecución en el sandbox, así que siempre debe durar
    más: nunca baja de `TIMEOUT_PASO_POR_DEFECTO_S` y crece si el sandbox se alarga.
    """
    return max(
        TIMEOUT_PASO_POR_DEFECTO_S, timeout_sandbox_s + MARGEN_PASO_SOBRE_SANDBOX_S
    )


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
    motivo_estancado: str | None = None
    revisiones: list[Contrato] = field(default_factory=list)
    #: Contrato del Planner (se guarda como spec en `.qagent/specs/`, EN-07).
    contrato: Contrato | None = None
    #: Código del último test generado; si la decisión es `accept`, es la prueba aprobada.
    codigo: str | None = None
    #: Segundos desde el primer intento hasta el veredicto (generar + sandbox + revisar).
    duracion_s: float = 0.0
    reutilizada: bool = False
    motivo_regresion: str | None = None
    #: Mutation testing de una función crítica aprobada (EN-09): estado, puntuacion,
    #: detectados, sobrevivientes y mensaje. None si no se ejecutó mutmut.
    mutacion: dict[str, Any] | None = None


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
    # Plan completo devuelto por el Planner (o cargado de la caché). Es interno:
    # permite persistir la spec aunque Generator/Reviewer falle en el primer objetivo.
    plan_completo: list[Contrato] = field(default_factory=list, repr=False)

    def a_dict(self) -> dict[str, Any]:
        """Versión serializable a JSON (insumo de log.json en EN-07)."""
        datos = asdict(self)
        datos.pop("plan_completo", None)
        datos["estado_final"] = self.estado_final.value
        datos["traza_estados"] = [e.value for e in self.traza_estados]
        return datos


def decidir_corte(
    decision: str,
    intento: int,
    tope: int,
    hash_actual: str | None,
    hash_anterior: str | None,
) -> tuple[str, str | None]:
    """Aplica la Regla 2 (HU-14) a la decisión del Reviewer.

    Corta en `stalled` si el hash del error se repite respecto del intento anterior
    (y no es null) o si se llegó al tope de intentos. Un `stalled` del Reviewer se
    clasifica con la misma regla.

    Returns:
        (decisión final, motivo): el motivo es `error_repetido`, `limite_intentos`
        o None si la decisión no es `stalled`.
    """
    if decision not in ("retry", "stalled"):
        return decision, None
    if hash_actual is not None and hash_actual == hash_anterior:
        return "stalled", ERROR_REPETIDO
    if decision == "stalled" or intento >= tope:
        return "stalled", LIMITE_INTENTOS
    return "retry", None


def etiqueta_estancado(intento: int, motivo: str) -> str:
    """Texto para la interfaz, ej. "Estancado 3/3 · límite de intentos"."""
    return f"Estancado {intento}/{MAX_INTENTOS_CONTRATO} · {_TEXTO_MOTIVO[motivo]}"


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

    def ejecutar(
        self,
        modulo: dict[str, Any],
        plan_reutilizado: list[Contrato] | None = None,
    ) -> ResultadoCorrida:
        """Ejecuta la corrida de un módulo (una entrada de `analizar_proyecto()["modulos"]`).

        Nunca lanza excepciones por fallos de agentes o del sandbox: los convierte en
        un `ResultadoCorrida` con estado FALLO_CONTROLADO y el motivo. Si recibe un
        plan vigente de HU-24, valida sus contratos y omite la llamada al Planner.
        """
        inicio = time.monotonic()
        self._archivo = modulo.get("ruta")
        self._estado = Estado.PLANIFICAR
        self._traza = [Estado.PLANIFICAR]
        self._emitir("orquestador", None, "Corrida iniciada", tipo="transicion")
        objetivos: list[ResultadoObjetivo] = []
        plan_completo: list[Contrato] = []
        motivo: str | None = None

        try:
            plan = (
                self._planificar(modulo)
                if plan_reutilizado is None
                else self._usar_plan_reutilizado(modulo, plan_reutilizado)
            )
            plan_completo = copy.deepcopy(plan)
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
            plan_completo=plan_completo,
        )

    # --- Pasos de la máquina -----------------------------------------------------

    def _planificar(self, modulo: dict[str, Any]) -> list[Contrato]:
        self._emitir("planner", None, "Planificando módulo")
        self.tracker.fijar_contexto(None, None)  # el plan es por módulo
        plan = self._llamar("planner", self.planner.planificar, modulo)
        if not isinstance(plan, list):
            raise FalloControlado("El Planner no devolvió una lista de contratos")
        # Avisos de las funciones (casos de más en Humo #75, categorías corregidas #76)
        # y casos descartados, por ejemplo un límite sin oráculo (#76).
        for aviso in getattr(self.planner, "avisos", None) or []:
            self._emitir("planner", None, f"Aviso: {aviso}")
        for descarte in getattr(self.planner, "descartados", None) or []:
            self._emitir("planner", None, f"Caso descartado: {descarte}")
        plan_endpoints = self._planificar_endpoints(modulo)
        plan = [*plan, *plan_endpoints]
        for contrato in plan:
            self._validar(contracts.PLANNER, contrato, "planner")
        self._emitir(
            "planner",
            None,
            f"Plan con {len(plan)} objetivo(s)",
            datos={"objetivos_planificados": len(plan)},
        )
        return plan

    def _planificar_endpoints(self, modulo: dict[str, Any]) -> list[Contrato]:
        """Pide al Planner los casos de los endpoints FastAPI del módulo (EN-16)."""
        planificar = getattr(self.planner, "planificar_endpoints", None)
        if not modulo.get("endpoints") or planificar is None:
            return []
        plan = self._llamar("planner", planificar, modulo, modulo.get("fuente"))
        if not isinstance(plan, list):
            raise FalloControlado("El Planner no devolvió una lista de contratos")
        for aviso in getattr(self.planner, "avisos", None) or []:
            self._emitir("planner", None, f"Aviso: {aviso}")
        for descarte in getattr(self.planner, "descartados", None) or []:
            self._emitir("planner", None, f"Caso descartado: {descarte}")
        return plan

    def _usar_plan_reutilizado(
        self, modulo: dict[str, Any], plan: list[Contrato]
    ) -> list[Contrato]:
        """Valida una spec vigente sin llamar al Planner ni registrar tokens."""
        if not isinstance(plan, list) or not plan:
            raise FalloControlado("La spec reutilizada no contiene contratos")
        copia = copy.deepcopy(plan)
        for contrato in copia:
            self._validar(contracts.PLANNER, contrato, "spec reutilizada")
            if contrato["modulo"] != modulo.get("ruta") or contrato[
                "huella"
            ] != modulo.get("huella"):
                raise FalloControlado(
                    "La spec reutilizada no coincide con el módulo analizado"
                )
        # HU-06 y #74: la marca Profundizar es la de esta corrida, no la que se guardó.
        # Los objetivos que no vienen en el módulo conservan su marca guardada.
        marcas = {
            ("funcion", funcion.get("nombre")): bool(funcion.get("critical", False))
            for funcion in modulo.get("funciones") or []
        }
        marcas.update(
            {
                ("endpoint", endpoint.get("objetivo")): bool(
                    endpoint.get("critical", False)
                )
                for endpoint in modulo.get("endpoints") or []
            }
        )
        for contrato in copia:
            clave = (contrato["tipo"], contrato["objetivo"])
            if clave in marcas:
                contrato["critical"] = marcas[clave]
        self.tracker.fijar_contexto(None, None)
        self._emitir(
            "planner",
            None,
            f"Spec reutilizado: Planner omitido (0 tokens, {len(copia)} objetivo(s))",
            datos={"objetivos_planificados": len(copia)},
        )
        return copia

    def _procesar_objetivo(
        self, contrato: Contrato, objetivos: list[ResultadoObjetivo]
    ) -> None:
        """Bucle generar -> ejecutar y revisar -> [reintentar] de un objetivo.

        El resultado se agrega a `objetivos` antes de empezar, para que un fallo
        controlado conserve lo avanzado (decision queda en None).
        """
        objetivo = contrato["objetivo"]
        resultado = ResultadoObjetivo(
            objetivo=objetivo,
            critical=contrato["critical"],
            contrato=copy.deepcopy(contrato),
        )
        objetivos.append(resultado)
        tope = min(self.max_intentos, MAX_INTENTOS_CONTRATO)  # nunca más de 3
        intento, feedback, test_anterior, hash_anterior = 1, None, None, None
        inicio = time.monotonic()

        while True:
            self._transicionar(Estado.GENERAR, objetivo)
            # Copia del contrato original del Planner: lo que un agente haga con su
            # copia no llega a los intentos siguientes (HU-14, criterio 3).
            try:
                test = self._generar(copy.deepcopy(contrato), intento, feedback)
            except FalloControlado as error:
                causa = error.__cause__
                if not isinstance(causa, ErrorRespuestaGenerator) or not causa.codigo:
                    raise
                # El Generator rechazó el candidato con ast.parse. Se entrega al
                # Reviewer solo para producir feedback contractual; su validación de
                # sintaxis impide que alcance el ejecutor del sandbox.
                test = {
                    "version": "1",
                    "objetivo": objetivo,
                    "intento": intento,
                    "codigo": causa.codigo,
                    "casos_cubiertos": [caso["id"] for caso in contrato["casos"]],
                }
            resultado.codigo = test["codigo"]
            self._transicionar(Estado.EJECUTAR_REVISAR, objetivo)
            revision = self._revisar(copy.deepcopy(contrato), test, test_anterior, tope)

            resultado.intentos = intento
            resultado.duracion_s = round(time.monotonic() - inicio, 3)
            resultado.revisiones.append(revision)
            resultado.cobertura = revision["cobertura"]
            resultado.laundering_detectado |= revision["laundering_detectado"]
            decision, motivo = decidir_corte(
                revision["decision"],
                intento,
                tope,
                revision["hash_error"],
                hash_anterior,
            )

            if decision in DECISIONES_FINALES:
                resultado.decision = decision
                resultado.motivo_estancado = motivo
                self._emitir_veredicto(objetivo, decision, intento, motivo)
                return

            self._transicionar(Estado.REINTENTAR, objetivo)
            self._emitir("reviewer", objetivo, f"Reintento: {revision['feedback']}")
            # Solo el último error: el feedback anterior se reemplaza, no se acumula.
            intento, feedback, test_anterior = intento + 1, revision["feedback"], test
            hash_anterior = revision["hash_error"]

    def _emitir_veredicto(
        self, objetivo: str, decision: str, intento: int, motivo: str | None
    ) -> None:
        """Evento final del objetivo; si quedó estancado lleva el intento y el motivo."""
        datos: dict[str, Any] = {"decision": decision, "intento": intento}
        mensaje = f"Veredicto: {decision}"
        if motivo is not None:
            mensaje = etiqueta_estancado(intento, motivo)
            datos.update(
                max_intentos=MAX_INTENTOS_CONTRATO, motivo=motivo, etiqueta=mensaje
            )
        self._emitir("reviewer", objetivo, mensaje, "veredicto", datos)

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
        self,
        contrato: Contrato,
        test: Contrato,
        test_anterior: Contrato | None,
        tope: int,
    ) -> Contrato:
        objetivo = contrato["objetivo"]
        self._emitir(
            "reviewer", objetivo, f"Ejecutando en sandbox (intento {test['intento']})"
        )
        self.tracker.fijar_contexto(objetivo, test["intento"])
        revision = self._llamar(
            "reviewer", self.reviewer.revisar, contrato, test, test_anterior
        )
        if (
            isinstance(revision, dict)
            and revision.get("decision") == "retry"
            and test["intento"] >= tope
        ):
            # Pedir otro intento sobre el tope no rompe la corrida: se corta (HU-14).
            revision = {**revision, "decision": "stalled"}
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
        self,
        agente: str,
        funcion: str | None,
        mensaje: str,
        tipo: str = "agente",
        datos: dict[str, Any] | None = None,
    ) -> None:
        self.bus.emitir(
            Evento(
                agente=agente,
                archivo=self._archivo,
                funcion=funcion,
                mensaje=mensaje,
                estado=self._estado.value,
                tipo=tipo,
                datos=datos,
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
