"""IA grabada para probar los agentes Java productivos, incluidos los guardrails."""

import json
from pathlib import Path

from qagent.agents.generator import GeneratorAgent
from qagent.agents.planner import PlannerAgent
from qagent.agents.reviewer import ReviewerAgent
from qagent.lenguajes import JavaAdapter
from qagent.llm import FakeLLMClient, RespuestaLLM, TokenTracker
from qagent.llm.fake import MARCA_CONTRATO
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
        "import static org.junit.jupiter.api.Assertions.*;\nclass "
        + objetivo.split(".")[0]
        + "Test {\n"
        "@Test void contrato() { " + CASOS[objetivo][2] + " }\n}\n"
    )


class ClienteJavaGrabado:
    """Sustituye solo la respuesta del proveedor; no decide validez ni veredictos."""

    def generar(self, prompt: str, rol: str = "generator") -> RespuestaLLM:
        """Lee el contrato enviado por el Generator y devuelve su JUnit grabado."""
        assert rol == "generator"
        contrato = json.loads(prompt.rsplit(MARCA_CONTRATO, 1)[1].strip())
        return RespuestaLLM(
            contenido=codigo_controlado(contrato["objetivo"]),
            modelo="fake-java",
            tokens_entrada=0,
            tokens_salida=0,
            costo_usd=0,
        )


class GeneratorConRegistro(GeneratorAgent):
    """Instrumenta los reintentos sin reemplazar el código del Generator productivo."""

    def __init__(self, tracker: TokenTracker, proyecto: Path) -> None:
        super().__init__(
            ClienteJavaGrabado(), tracker, es_simulado=True, ruta_proyecto=proyecto
        )
        self.feedbacks = []

    def generar(self, contrato, intento, feedback):
        """Registra el feedback y ejecuta la generación productiva con #184."""
        self.feedbacks.append(feedback)
        return super().generar(contrato, intento, feedback)


def preparar_corrida(monkeypatch, proyecto: Path, ejecutor=None):
    """Los tres agentes y el adaptador reales; solo IA o runner se simulan."""
    adaptador = JavaAdapter()
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
    generator = GeneratorConRegistro(tracker, proyecto)
    from qagent.config import cargar_configuracion

    limites = cargar_configuracion(simulado=True).config.limites_sandbox("java")
    reviewer = ReviewerAgent(
        tracker, proyecto, "qagent-sandbox:java", ejecutor=ejecutor, limites=limites
    )
    orquestador = Orquestador(
        planner, generator, reviewer, tracker=tracker, timeout_paso_s=420
    )
    return orquestador, tracker, generator
