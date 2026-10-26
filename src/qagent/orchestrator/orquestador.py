"""Orquestador de la corrida: máquina de estados que coordina a los 3 agentes (EN-04).

planificar -> generar -> ejecutar y revisar -> [reintentar -> generar ...] -> fin
Un error del sandbox o de un agente termina en fallo controlado, sin colgar la corrida
y devolviendo lo que se alcanzó a procesar. Si el problema es solo de tiempo o de red
(el agente no respondió a tiempo o el proveedor de IA está saturado), afecta a esa
función: queda sin veredicto y se sigue con la siguiente.
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
from qagent.llm.cliente import LimiteProveedor, SinConexion
from qagent.llm.tracker import TokenTracker
from qagent.orchestrator.estados import Estado, validar_transicion
from qagent.orchestrator.eventos import BusEventos, Evento
from qagent.orchestrator.puertos import Contrato, Generator, Planner, Reviewer
from qagent.orchestrator.tiempos import etapas_vacias, iso_utc, segundos, sumar_etapa

T = TypeVar("T")

MAX_INTENTOS_CONTRATO = 3  # tope de generated_test/review_result (EN-01)
TIMEOUT_PASO_POR_DEFECTO_S = 240.0  # mayor que el timeout del sandbox (120 s)
#: Lo que el paso del Reviewer espera además del sandbox: su llamada al LLM (90 s) y holgura.
MARGEN_PASO_SOBRE_SANDBOX_S = 120.0
SANDBOX_FALLIDO = frozenset({"timeout", "error"})
DECISIONES_FINALES = frozenset({"accept", "bug_detectado", "stalled"})
LIMITE_INTENTOS = "limite_intentos"  # motivos del corte (HU-14)
ERROR_REPETIDO = "error_repetido"
LIMITE_TOKENS = "limite_tokens"
_TEXTO_MOTIVO = {
    LIMITE_INTENTOS: "límite de intentos",
    ERROR_REPETIDO: "mismo error repetido",
    LIMITE_TOKENS: "límite de tokens",
}
#: Por qué un objetivo seleccionado no se probó (se muestran en Resultados).
MOTIVO_RUTA_SIN_RESOLVER = (
    "No se pudo saber la ruta completa del endpoint sin ejecutar la app (por ejemplo, "
    "el router se incluye dentro de un try o de una función), así que no se planificó."
)
MOTIVO_SIN_CONTRATO = (
    "El Planner no propuso un caso verificable para este objetivo a partir de su "
    "especificación."
)


def _frase(texto: str) -> str:
    """El motivo del Planner como frase: con mayúscula inicial y punto final."""
    texto = texto.strip()
    if not texto:
        return MOTIVO_SIN_CONTRATO
    texto = texto[0].upper() + texto[1:]
    return texto if texto.endswith(".") else texto + "."


def _segundos_de(valor: Any) -> float:
    """Duración numérica no negativa de un contrato, o 0 si falta."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return 0.0
    return round(max(0.0, float(valor)), 3)


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


class LimiteTokensSuperado(FalloControlado):
    """Se alcanzó el límite de presupuesto de tokens por corrida."""


class CorridaCancelada(FalloControlado):
    """La corrida fue cancelada por el usuario."""


#: Motivo de un objetivo sin veredicto porque un agente no respondió a tiempo.
TIEMPO_AGOTADO = "tiempo_agotado"
#: Motivo de un objetivo sin veredicto porque el contrato del Planner no es válido.
ERROR_CONTRATO_PLANNER = "error_contrato_planner"


def _resumen_error_contrato(error: BaseException) -> str:
    """Mensaje conciso y comprensible para el usuario ante un contrato inválido."""
    causa = getattr(error, "__cause__", None) or error
    if isinstance(causa, ContratoInvalido) and causa.errores:
        primer_error = causa.errores[0].strip()
        if len(primer_error) > 120:
            primer_error = primer_error[:117] + "…"
        return primer_error
    texto = str(causa).strip()
    if len(texto) > 120:
        texto = texto[:117] + "…"
    return texto or "formato no válido"


def es_falla_pasajera(error: BaseException) -> bool:
    """True si el error es de tiempo o de red y no del código, el test o la cuenta.

    El cliente de IA envuelve sus errores, así que se recorre la cadena de causas:
    sirven un `TimeoutPaso`, un `SinConexion` (incluye no responder en el plazo) o un
    `LimiteProveedor` que siguió tras los reintentos. No sirven, por ejemplo, la
    falta de crédito o una clave inválida: fallarían igual en todas las funciones.
    """
    actual: BaseException | None = error
    while actual is not None:
        if isinstance(actual, (TimeoutPaso, SinConexion, LimiteProveedor)):
            return True
        actual = actual.__cause__
    return False


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
    #: Por qué quedó sin veredicto (decision None) sin detener el módulo: hoy solo
    #: `TIEMPO_AGOTADO`. El detalle del error va en el Monitor y la bitácora.
    motivo_sin_veredicto: str | None = None
    #: Marcas UTC y desglose medido con reloj monotónico (#115).
    inicio: str | None = None
    fin: str | None = None
    duracion_generacion_s: float = 0.0
    duracion_revision_s: float = 0.0
    duracion_sandbox_s: float = 0.0
    duracion_pytest_s: float = 0.0
    tiempos_intentos: list[dict[str, Any]] = field(default_factory=list)


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
    #: Marcas UTC y desglose por etapa medidos con reloj monotónico (#115).
    inicio: str | None = None
    fin: str | None = None
    duracion_etapas: dict[str, float] = field(default_factory=dict)
    # Plan completo devuelto por el Planner (o cargado de la caché). Es interno:
    # permite persistir la spec aunque Generator/Reviewer falle en el primer objetivo.
    plan_completo: list[Contrato] = field(default_factory=list, repr=False)
    #: Objetivos seleccionados que quedaron fuera del plan, con su motivo: sin un
    #: resultado esperado verificable o con una ruta sin resolver. No son pendientes
    #: por una detención: se probaron hasta donde la especificación lo permite.
    omitidos: list[dict[str, str]] = field(default_factory=list)

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
        reloj: Callable[[], float] = time.monotonic,
        ahora: Callable[[], str] = iso_utc,
        limite_tokens: int | None = None,
        cancelado: Callable[[], bool] | None = None,
    ) -> None:
        """Crea el orquestador.

        Args:
            planner, generator, reviewer: agentes que cumplen los `puertos`.
            bus: bus de eventos para el Monitor; si es None se crea uno.
            tracker: registro de tokens compartido con los agentes.
            max_intentos: intentos por objetivo (1 a 3, límite de los contratos).
            timeout_paso_s: tiempo máximo que se espera a un agente en cada paso.
            reloj: reloj monotónico inyectable (los tests usan uno falso).
            ahora: marca UTC ISO inyectable (los tests usan una fija).
            limite_tokens: presupuesto máximo de tokens de la corrida, si existe.
            cancelado: consulta inyectable para detener la corrida.
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
        self._reloj = reloj
        self._ahora = ahora
        self.limite_tokens = limite_tokens
        self.cancelado = cancelado
        self._aviso_80_emitido = False
        self._estado = Estado.PLANIFICAR
        self._traza: list[Estado] = []
        self._archivo: str | None = None
        self._inicio_reloj = reloj()
        self._inicio_utc = ahora()
        self._etapas = etapas_vacias()
        self._objetivo_actual: ResultadoObjetivo | None = None
        #: Motivos del Planner para las funciones que omitió en el módulo actual.
        self._motivos_omision: dict[str, str] = {}
        self._inicio_objetivo_reloj = 0.0
        self._inicio_objetivo_utc: str | None = None

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
        inicio = self._reloj()
        self._inicio_reloj = inicio
        self._inicio_utc = self._ahora()
        self._etapas = etapas_vacias()
        self._archivo = modulo.get("ruta")
        self._estado = Estado.PLANIFICAR
        self._traza = [Estado.PLANIFICAR]
        self._emitir("orquestador", None, "Corrida iniciada", tipo="transicion")
        objetivos: list[ResultadoObjetivo] = []
        plan_completo: list[Contrato] = []
        omitidos: list[dict[str, str]] = []
        motivo: str | None = None
        self._motivos_omision = {}

        try:
            inicio_plan = self._reloj()
            try:
                plan = (
                    self._planificar(modulo)
                    if plan_reutilizado is None
                    else self._usar_plan_reutilizado(modulo, plan_reutilizado)
                )
            finally:
                sumar_etapa(
                    self._etapas, "planner", segundos(inicio_plan, self._reloj())
                )
            plan_completo = copy.deepcopy(plan)
            omitidos = self._omitidos(modulo, plan)
            for contrato in plan:
                if self.cancelado is not None and self.cancelado():
                    raise CorridaCancelada("Corrida detenida por el usuario.")
                if (
                    self.limite_tokens
                    and self.tracker.total_tokens >= self.limite_tokens
                ):
                    self._emitir(
                        "orquestador",
                        contrato["objetivo"],
                        f"Presupuesto de tokens alcanzado ({self.limite_tokens} tokens). "
                        "No se procesarán más objetivos en este módulo.",
                        tipo="aviso",
                        datos={
                            "alerta_presupuesto": True,
                            "tokens": self.tracker.total_tokens,
                        },
                    )
                    raise LimiteTokensSuperado(
                        f"Se alcanzó el presupuesto de tokens por corrida ({self.limite_tokens} tokens)."
                    )
                self._procesar_objetivo(contrato, objetivos)
            self._transicionar(Estado.FIN, None)
            self._emitir("orquestador", None, "Corrida terminada", tipo="fin")
        except FalloControlado as error:
            motivo = str(error)
            funcion = (
                objetivos[-1].objetivo
                if objetivos and objetivos[-1].decision is None
                else None
            )
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
            duracion_s=segundos(inicio, self._reloj()),
            inicio=self._inicio_utc,
            fin=self._ahora(),
            duracion_etapas=dict(self._etapas),
            plan_completo=plan_completo,
            omitidos=omitidos,
        )

    def _omitidos(
        self, modulo: dict[str, Any], plan: list[Contrato]
    ) -> list[dict[str, str]]:
        """Objetivos seleccionados del módulo que no entraron al plan, con su motivo.

        El motivo es el del Planner (función sin resultado esperado deducible), el de
        una ruta sin resolver o, si el Planner no propuso nada usable, uno genérico.
        """
        planificados = {c.get("objetivo") for c in plan if isinstance(c, dict)}
        omitidos: list[dict[str, str]] = []
        for funcion in modulo.get("funciones") or []:
            nombre = funcion.get("nombre")
            if nombre and nombre not in planificados:
                motivo = self._motivos_omision.get(nombre, MOTIVO_SIN_CONTRATO)
                omitidos.append(
                    {"objetivo": nombre, "tipo": "funcion", "motivo": _frase(motivo)}
                )
        for endpoint in modulo.get("endpoints") or []:
            objetivo = endpoint.get("objetivo") or endpoint.get("manejador")
            if not objetivo or objetivo in planificados:
                continue
            sin_ruta = not endpoint.get("objetivo") or not endpoint.get(
                "resuelta", True
            )
            motivo = MOTIVO_RUTA_SIN_RESOLVER if sin_ruta else MOTIVO_SIN_CONTRATO
            omitidos.append(
                {"objetivo": objetivo, "tipo": "endpoint", "motivo": motivo}
            )
        return omitidos

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
        # Funciones sin valor esperado deducible: se avisan y la corrida sigue.
        omitidas = getattr(self.planner, "omitidas", None) or {}
        self._motivos_omision = dict(omitidas)
        for nombre, motivo in omitidas.items():
            self._emitir(
                "planner",
                nombre,
                f"Función omitida: {motivo}",
                datos={"omitida": True},
            )
        plan_endpoints = self._planificar_endpoints(modulo)
        plan = [*plan, *plan_endpoints]
        for elemento in plan:
            if not isinstance(elemento, dict) or not elemento.get("objetivo"):
                raise FalloControlado(
                    "El Planner devolvió un contrato que no es un objeto con 'objetivo'"
                )
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
        objetivo = (
            contrato.get("objetivo")
            if isinstance(contrato, dict)
            else "objetivo_desconocido"
        )
        resultado = ResultadoObjetivo(
            objetivo=objetivo,
            critical=bool(contrato.get("critical", False))
            if isinstance(contrato, dict)
            else False,
            contrato=copy.deepcopy(contrato) if isinstance(contrato, dict) else None,
        )
        objetivos.append(resultado)
        tope = min(self.max_intentos, MAX_INTENTOS_CONTRATO)  # nunca más de 3
        intento, feedback, test_anterior, hash_anterior = 1, None, None, None
        inicio = self._reloj()
        resultado.inicio = self._ahora()
        self._objetivo_actual = resultado
        self._inicio_objetivo_reloj = inicio
        self._inicio_objetivo_utc = resultado.inicio

        try:
            try:
                self._validar(contracts.PLANNER, contrato, "planner")
            except FalloControlado as error:
                resultado.motivo_sin_veredicto = ERROR_CONTRATO_PLANNER
                resumen_err = _resumen_error_contrato(error)
                self._emitir(
                    "planner",
                    objetivo,
                    f"Sin veredicto en '{objetivo}': la propuesta del Planner no cumple "
                    f"el contrato ({resumen_err}). Se continúa con los siguientes objetivos.",
                    tipo="veredicto",
                    datos={
                        "decision": None,
                        "intento": 0,
                        "motivo": ERROR_CONTRATO_PLANNER,
                        "error": str(error),
                    },
                )
                return

            while True:
                if self.cancelado is not None and self.cancelado():
                    raise CorridaCancelada("Corrida detenida por el usuario.")
                n_intento = intento
                inicio_intento = self._reloj()
                generacion_s = 0.0
                revision_s = 0.0
                try:
                    self._transicionar(Estado.GENERAR, objetivo)
                    # Copia del contrato original del Planner: lo que un agente haga
                    # con su copia no llega a los intentos siguientes (HU-14, 3).
                    inicio_generacion = self._reloj()
                    try:
                        try:
                            test = self._generar(
                                copy.deepcopy(contrato), intento, feedback
                            )
                        except FalloControlado as error:
                            if es_falla_pasajera(error):
                                self._sin_veredicto(
                                    resultado, intento, inicio, "generator", error
                                )
                                return
                            causa = error.__cause__
                            if (
                                not isinstance(causa, ErrorRespuestaGenerator)
                                or not causa.codigo
                            ):
                                raise
                            # El Generator rechazó el candidato con ast.parse. Se
                            # entrega al Reviewer solo para producir feedback
                            # contractual; su validación de sintaxis impide que
                            # alcance el ejecutor del sandbox.
                            test = {
                                "version": "1",
                                "objetivo": objetivo,
                                "intento": intento,
                                "codigo": causa.codigo,
                                "casos_cubiertos": [
                                    caso["id"] for caso in contrato["casos"]
                                ],
                            }
                    finally:
                        generacion_s = segundos(inicio_generacion, self._reloj())
                        resultado.duracion_generacion_s = round(
                            resultado.duracion_generacion_s + generacion_s, 3
                        )
                        sumar_etapa(self._etapas, "generator", generacion_s)
                    resultado.codigo = test["codigo"]
                    self._transicionar(Estado.EJECUTAR_REVISAR, objetivo)
                    inicio_revision = self._reloj()
                    try:
                        revision = self._revisar(
                            copy.deepcopy(contrato), test, test_anterior, tope
                        )
                    except FalloControlado as error:
                        if not es_falla_pasajera(error):
                            raise
                        self._sin_veredicto(
                            resultado, intento, inicio, "reviewer", error
                        )
                        return
                    finally:
                        revision_s = segundos(inicio_revision, self._reloj())
                        resultado.duracion_revision_s = round(
                            resultado.duracion_revision_s + revision_s, 3
                        )
                        sumar_etapa(self._etapas, "reviewer", revision_s)

                    ejecucion = revision.get("ejecucion") or {}
                    sandbox_s = _segundos_de(ejecucion.get("duracion_s"))
                    pytest_s = _segundos_de(ejecucion.get("duracion_pytest_s"))
                    if sandbox_s:
                        resultado.duracion_sandbox_s = round(
                            resultado.duracion_sandbox_s + sandbox_s, 3
                        )
                        sumar_etapa(self._etapas, "sandbox", sandbox_s)
                    if pytest_s:
                        resultado.duracion_pytest_s = round(
                            resultado.duracion_pytest_s + pytest_s, 3
                        )
                        sumar_etapa(self._etapas, "pytest", pytest_s)

                    resultado.intentos = intento
                    resultado.duracion_s = segundos(inicio, self._reloj())
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

                    if self.cancelado is not None and self.cancelado():
                        raise CorridaCancelada("Corrida detenida por el usuario.")

                    if (
                        self.limite_tokens
                        and self.tracker.total_tokens >= self.limite_tokens
                    ):
                        decision = "stalled"
                        motivo = LIMITE_TOKENS
                        resultado.decision = decision
                        resultado.motivo_estancado = motivo
                        self._emitir(
                            "orquestador",
                            objetivo,
                            f"Presupuesto de tokens alcanzado ({self.limite_tokens} tokens). Reintento cancelado.",
                            tipo="aviso",
                            datos={
                                "alerta_presupuesto": True,
                                "tokens": self.tracker.total_tokens,
                            },
                        )
                        self._emitir_veredicto(objetivo, decision, intento, motivo)
                        return

                    self._transicionar(Estado.REINTENTAR, objetivo)
                    self._emitir(
                        "reviewer", objetivo, f"Reintento: {revision['feedback']}"
                    )
                    # Solo el último error: el feedback anterior se reemplaza.
                    intento, feedback, test_anterior = (
                        intento + 1,
                        revision["feedback"],
                        test,
                    )
                    hash_anterior = revision["hash_error"]
                finally:
                    resultado.tiempos_intentos.append(
                        {
                            "intento": n_intento,
                            "duracion_s": segundos(inicio_intento, self._reloj()),
                            "generacion_s": round(generacion_s, 3),
                            "revision_s": round(revision_s, 3),
                        }
                    )
        finally:
            resultado.fin = self._ahora()
            resultado.duracion_s = segundos(inicio, self._reloj())
            self._objetivo_actual = None

    def _sin_veredicto(
        self,
        resultado: ResultadoObjetivo,
        intento: int,
        inicio: float,
        agente: str,
        error: BaseException,
    ) -> None:
        """Cierra el objetivo sin veredicto por tiempo o red; el módulo sigue.

        Reintentar con el mismo proveedor lento casi nunca sirve y gastaría el
        tiempo de las demás funciones, así que se pasa a la siguiente.
        """
        resultado.intentos = intento
        resultado.duracion_s = segundos(inicio, self._reloj())
        resultado.motivo_sin_veredicto = TIEMPO_AGOTADO
        self._emitir(
            agente,
            resultado.objetivo,
            f"Sin veredicto: {error}. Se sigue con la siguiente función.",
            "veredicto",
            {"decision": None, "intento": intento, "motivo": TIEMPO_AGOTADO},
        )

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
        # El hilo registra sus tokens con el contexto de ahora, aunque termine tarde.
        contexto = self.tracker.contexto_actual()

        def objetivo_hilo() -> None:
            self.tracker.fijar_contexto_hilo(*contexto)
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

    def _revisar_alerta_presupuesto(self) -> None:
        """Emite una advertencia al alcanzar el 80 % del presupuesto de tokens."""
        if not self.limite_tokens or self._aviso_80_emitido:
            return
        if self.tracker.total_tokens >= int(self.limite_tokens * 0.80):
            self._aviso_80_emitido = True
            pct = round(self.tracker.total_tokens / self.limite_tokens * 100)
            self.bus.emitir(
                Evento(
                    agente="orquestador",
                    archivo=self._archivo,
                    funcion=None,
                    mensaje=(
                        f"Aviso de presupuesto: se ha consumido el {pct} % del límite de tokens "
                        f"({self.tracker.total_tokens} de {self.limite_tokens} tokens)."
                    ),
                    estado=self._estado.value,
                    tipo="aviso",
                    datos={
                        "alerta_presupuesto": True,
                        "tokens": self.tracker.total_tokens,
                        "limite_tokens": self.limite_tokens,
                        "porcentaje": pct,
                    },
                )
            )

    def _emitir(
        self,
        agente: str,
        funcion: str | None,
        mensaje: str,
        tipo: str = "agente",
        datos: dict[str, Any] | None = None,
    ) -> None:
        self._revisar_alerta_presupuesto()
        informacion: dict[str, Any] = {
            "inicio_corrida": self._inicio_utc,
            "transcurrido_s": segundos(self._inicio_reloj, self._reloj()),
            "etapas_s": dict(self._etapas),
        }
        if (
            self._objetivo_actual is not None
            and funcion == self._objetivo_actual.objetivo
        ):
            informacion["inicio_objetivo"] = self._inicio_objetivo_utc
            informacion["duracion_objetivo_s"] = segundos(
                self._inicio_objetivo_reloj, self._reloj()
            )
        self.bus.emitir(
            Evento(
                agente=agente,
                archivo=self._archivo,
                funcion=funcion,
                mensaje=mensaje,
                estado=self._estado.value,
                tipo=tipo,
                datos=datos,
                inicio_corrida=informacion["inicio_corrida"],
                transcurrido_s=informacion["transcurrido_s"],
                etapas_s=informacion["etapas_s"],
                inicio_objetivo=informacion.get("inicio_objetivo"),
                duracion_objetivo_s=informacion.get("duracion_objetivo_s"),
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
