"""Entradas JUnit explícitas para probar #182 mientras #184 no está implementada.

Solo las pruebas usan este doble del puerto de generación/guardrail. No registra
un adaptador completo ni cambia la disponibilidad de Java en la aplicación.
"""

from pathlib import Path
from types import SimpleNamespace

from qagent import contracts
from qagent.agents.planner import PlannerAgent
from qagent.agents.reviewer import ReviewerAgent
from qagent.lenguajes import JavaAdapter
from qagent.lenguajes.java_revision import ReglasRevisionJava
from qagent.llm import FakeLLMClient, TokenTracker
from qagent.orchestrator import Orquestador

RAIZ = Path(__file__).resolve().parents[2]
CASOS = {
    "BancoCorrecto.sumarPrecios": (
        {"precios": [10, 20]},
        30,
        "assertEquals(30.0, BancoCorrecto.sumarPrecios(List.of(10.0, 20.0)));",
    ),
    "BancoCorrecto.aplicarDescuento": (
        {"precio": 100, "porcentaje": 20},
        80,
        "assertEquals(80.0, BancoCorrecto.aplicarDescuento(100.0, 20.0));",
    ),
    "BancoCorrecto.esMayorDeEdad": (
        {"edad": 18},
        True,
        "assertTrue(BancoCorrecto.esMayorDeEdad(18));",
    ),
    "BancoDefectuoso.calcularPromedio": (
        {"numeros": [2, 3]},
        2.5,
        "assertEquals(2.5, BancoDefectuoso.calcularPromedio(List.of(2, 3)));",
    ),
    "BancoDefectuoso.calcularEnvio": (
        {"importe": 100},
        0,
        "assertEquals(0.0, BancoDefectuoso.calcularEnvio(100.0));",
    ),
    "BancoDefectuoso.calcularTotalConImpuesto": (
        {"subtotal": 100, "porcentaje": 18},
        118,
        "assertEquals(118.0, BancoDefectuoso.calcularTotalConImpuesto(100.0, 18.0));",
    ),
}


def codigo_controlado(objetivo: str) -> str:
    """Fuente fija cuyo esperado procede de casos.md/Javadoc, sin ejecutar el banco."""
    return (
        "package org.qagent.bench;\nimport java.util.List;\nimport org.junit.jupiter.api.Test;\n"
        "import static org.junit.jupiter.api.Assertions.*;\nclass BancoControladoTest {\n"
        "@Test void contrato() { " + CASOS[objetivo][2] + " }\n}\n"
    )


class ReglasControladas(ReglasRevisionJava):
    """Acepta exclusivamente las seis fuentes conocidas de esta fixture, byte a byte."""

    def validar_oraculo(self, contrato, codigo):
        """No valida Java arbitrario; limita la prueba de integración a su fixture."""
        return (
            None
            if codigo == codigo_controlado(contrato["objetivo"])
            else "Fuente ajena a la fixture de #182."
        )


class AdaptadorControlado(JavaAdapter):
    """Sustituye únicamente los dos puertos de #184 para estas pruebas."""

    def reglas_revision(self):
        """Mantiene sintaxis, clasificación y rangos reales con oráculo de fixture."""
        return ReglasControladas()

    def comparar_aserciones(self, original, reparado):
        """La fixture no permite reparaciones: ambas fuentes deben ser idénticas."""
        return SimpleNamespace(
            es_laundering=original != reparado, resumen="La fuente controlada cambió."
        )


class GeneratorControlado:
    """Entrega JUnit conocido; no implementa ni simula seguridad para entradas libres."""

    def __init__(self):
        self.feedbacks = []

    def generar(self, contrato, intento, feedback):
        """Conserva el código y registra qué errores llegan a un nuevo intento."""
        self.feedbacks.append(feedback)
        return contracts.generated_test_para(
            contrato,
            intento,
            codigo_controlado(contrato["objetivo"]),
            "BancoControladoTest.java",
        )


def preparar_corrida(monkeypatch, proyecto: Path, ejecutor=None):
    """Planner y Reviewer reales; solo el Generator y su guardrail son controlados."""
    adaptador = AdaptadorControlado()
    monkeypatch.setattr(
        "qagent.agents.reviewer.adaptador_de_contrato", lambda contrato: adaptador
    )
    grabadas = {
        nombre.split(".")[0] + ".java::" + nombre: [
            {
                "id": "contrato",
                "entrada": entrada,
                "valor_esperado": esperado,
                "origen": "docstring",
                "categoria": "limite" if nombre.endswith("calcularEnvio") else "normal",
            }
        ]
        for nombre, (entrada, esperado, _) in CASOS.items()
    }
    tracker = TokenTracker()
    planner = PlannerAgent(
        FakeLLMClient(grabaciones=grabadas),
        tracker,
        es_simulado=True,
        adaptador=adaptador,
    )
    generator = GeneratorControlado()
    from qagent.config import cargar_configuracion

    limites = cargar_configuracion(simulado=True).config.limites_sandbox("java")
    reviewer = ReviewerAgent(
        tracker, proyecto, "qagent-sandbox:java", ejecutor=ejecutor, limites=limites
    )
    orquestador = Orquestador(
        planner, generator, reviewer, tracker=tracker, timeout_paso_s=420
    )
    return orquestador, tracker, generator
