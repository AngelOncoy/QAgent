"""Agentes simulados para probar el orquestador sin API ni Docker (0 tokens)."""

from __future__ import annotations

import json
import time
from typing import Any

from pyagent.llm import FakeLLMClient, TokenTracker
from pyagent.sandbox.modelos import ErrorSandbox
from pyagent.sandbox.normalizacion import hash_error

MODULO = {
    "ruta": "modulo_simulado.py",
    "huella": "0" * 64,
    "funciones": [{"nombre": "duplicar", "firma": "(x: int) -> int"}],
}


def _registrar(
    tracker: TokenTracker, agente: str, cliente: FakeLLMClient, rol: str
) -> str:
    """Llama a la IA simulada y registra el consumo (siempre 0 tokens)."""
    respuesta = cliente.generar(prompt=f"tarea de {rol}", rol=rol)
    tracker.registrar(
        agente=agente,
        modelo=respuesta.modelo,
        tokens_entrada=respuesta.tokens_entrada,
        tokens_salida=respuesta.tokens_salida,
        costo_usd=respuesta.costo_usd,
        es_simulado=True,
    )
    return respuesta.contenido


class PlannerSimulado:
    """Devuelve el plan grabado de la IA simulada (lista de planner_contract.v2)."""

    def __init__(self, tracker: TokenTracker, plan: list[dict] | None = None) -> None:
        self.tracker = tracker
        self.cliente = FakeLLMClient()
        self.plan = plan
        self.llamadas = 0

    def planificar(self, modulo: dict[str, Any]) -> list[dict]:
        self.llamadas += 1
        contenido = _registrar(self.tracker, "planner", self.cliente, "planner")
        return self.plan if self.plan is not None else json.loads(contenido)


class GeneratorSimulado:
    """Envuelve el código grabado en un generated_test y anota el feedback recibido."""

    def __init__(self, tracker: TokenTracker) -> None:
        self.tracker = tracker
        self.cliente = FakeLLMClient()
        self.feedbacks: list[str | None] = []

    def generar(self, contrato: dict, intento: int, feedback: str | None) -> dict:
        self.feedbacks.append(feedback)
        codigo = _registrar(self.tracker, "generator", self.cliente, "generator")
        return {
            "version": "1",
            "objetivo": contrato["objetivo"],
            "intento": intento,
            "codigo": codigo,
            "casos_cubiertos": [c["id"] for c in contrato["casos"]],
        }


def veredicto(objetivo: str, intento: int, decision: str, **extra: Any) -> dict:
    """Arma un review_result válido para la decisión indicada."""
    base = {
        "version": "1",
        "objetivo": objetivo,
        "intento": intento,
        "estado_sandbox": "ok",
        "cobertura": {"lineas": 100.0, "ramas": 100.0},
        "laundering_detectado": False,
        "tipo_fallo": None,
        "hash_error": None,
        "decision": decision,
        "feedback": "Test aprobado en sandbox.",
    }
    if decision == "retry":
        base.update(
            estado_sandbox="fallo",
            tipo_fallo="error_test",
            hash_error=f"{intento:08x}",
            feedback=f"ImportError en el intento {intento}",
        )
    elif decision == "stalled":
        base.update(
            estado_sandbox="fallo", tipo_fallo="error_test", feedback="sin avance"
        )
    elif decision == "bug_detectado":
        base.update(
            estado_sandbox="fallo", tipo_fallo="bug_codigo", feedback="assert 19 == 20"
        )
    base.update(extra)
    return base


class ReviewerGuionado:
    """Devuelve las decisiones del guion en orden, una por intento."""

    def __init__(self, tracker: TokenTracker, decisiones: list[str]) -> None:
        self.tracker = tracker
        self.cliente = FakeLLMClient()
        self.decisiones = list(decisiones)
        self.tests_anteriores: list[dict | None] = []

    def revisar(self, contrato: dict, test: dict, test_anterior: dict | None) -> dict:
        self.tests_anteriores.append(test_anterior)
        _registrar(self.tracker, "reviewer", self.cliente, "reviewer")
        return veredicto(contrato["objetivo"], test["intento"], self.decisiones.pop(0))


class ReviewerSandboxTimeout:
    """Simula que el contenedor excedió su timeout (ResultadoSandbox.timed_out)."""

    def revisar(self, contrato: dict, test: dict, test_anterior: dict | None) -> dict:
        return veredicto(
            contrato["objetivo"],
            test["intento"],
            "stalled",
            estado_sandbox="timeout",
            cobertura=None,
            feedback="El contenedor excedió 60 s y se detuvo.",
        )


class ReviewerSandboxCaido:
    """Simula que Docker no pudo crear el contenedor."""

    def revisar(self, contrato: dict, test: dict, test_anterior: dict | None) -> dict:
        raise ErrorSandbox("Docker no pudo crear el contenedor")


class ReviewerColgado:
    """Simula un Reviewer que nunca responde."""

    def __init__(self, segundos: float = 5.0) -> None:
        self.segundos = segundos

    def revisar(self, contrato: dict, test: dict, test_anterior: dict | None) -> dict:
        time.sleep(self.segundos)
        return {}


class ReviewerConErrores:
    """Simula pytest fallando con los errores dados, uno por intento (HU-14).

    Un error es un traceback simulado: se devuelve `retry` con su `hash_error`
    calculado con la normalización real. `None` en la lista es un test que pasó.
    La decisión de cortar la toma el orquestador, no este Reviewer.
    """

    def __init__(self, errores: list[str | None]) -> None:
        self.errores = list(errores)
        self.contratos: list[dict] = []

    def revisar(self, contrato: dict, test: dict, test_anterior: dict | None) -> dict:
        self.contratos.append(contrato)
        error = self.errores.pop(0)
        if error is None:
            return veredicto(contrato["objetivo"], test["intento"], "accept")
        return veredicto(
            contrato["objetivo"],
            test["intento"],
            "retry",
            hash_error=hash_error(error),
            feedback=error,
        )


class GeneratorEspia(GeneratorSimulado):
    """Generator que guarda copia de lo que recibe y luego daña su contrato.

    Sirve para comprobar que cada intento recibe el contrato original del Planner
    y solo el último feedback, aunque un agente modifique lo que se le pasó.
    """

    def __init__(self, tracker: TokenTracker) -> None:
        super().__init__(tracker)
        self.contratos: list[dict] = []

    def generar(self, contrato: dict, intento: int, feedback: str | None) -> dict:
        self.contratos.append(json.loads(json.dumps(contrato)))
        test = super().generar(contrato, intento, feedback)
        contrato["casos"].clear()  # un agente que muta su entrada
        contrato["objetivo_modificado"] = True
        return test
