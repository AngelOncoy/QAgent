"""Agente Generator: convierte un contrato del Planner en código pytest."""

from __future__ import annotations

import json
from typing import Any

from pyagent import contracts
from pyagent.llm import ClienteLLM, TokenTracker


class ErrorRespuestaGenerator(ValueError):
    """El Generator devolvió una respuesta que no puede utilizarse."""


class GeneratorAgent:
    """Genera el test de un único objetivo a partir de su contrato."""

    def __init__(
        self,
        cliente: ClienteLLM,
        tracker: TokenTracker,
        *,
        es_simulado: bool = False,
    ) -> None:
        """Inicializa el Generator con su cliente y registro de tokens."""
        self.cliente = cliente
        self.tracker = tracker
        self.es_simulado = es_simulado

    def generar(
        self,
        contrato: dict[str, Any],
        intento: int,
        feedback: str | None,
    ) -> dict[str, Any]:
        """Genera o corrige un test pytest."""
        prompt = self._crear_prompt(contrato, intento, feedback)
        respuesta = self.cliente.generar(prompt, rol="generator")

        self.tracker.registrar(
            agente="generator",
            modelo=respuesta.modelo,
            tokens_entrada=respuesta.tokens_entrada,
            tokens_salida=respuesta.tokens_salida,
            costo_usd=respuesta.costo_usd,
            es_simulado=self.es_simulado,
        )

        codigo = _quitar_cerca_python(respuesta.contenido)
        if not codigo.strip():
            raise ErrorRespuestaGenerator("El Generator devolvió código vacío.")

        generado = {
            "version": "1",
            "objetivo": contrato["objetivo"],
            "intento": intento,
            "codigo": codigo,
            "casos_cubiertos": [caso["id"] for caso in contrato["casos"]],
        }
        contracts.validar(contracts.GENERATED_TEST, generado)
        return generado

    @staticmethod
    def _crear_prompt(
        contrato: dict[str, Any],
        intento: int,
        feedback: str | None,
    ) -> str:
        contrato_json = json.dumps(contrato, ensure_ascii=False, indent=2)
        correccion = (
            feedback
            if feedback
            else "No existe feedback porque este es el primer intento."
        )
        return f"""
Escribe un archivo pytest completo para el contrato indicado.

REGLAS OBLIGATORIAS:
- Usa exactamente los valores esperados del contrato.
- No ejecutes el código para descubrir resultados.
- No elimines, cambies ni debilites las aserciones.
- Simula con mocks las funciones incluidas en llama_a.
- Para endpoints FastAPI usa TestClient y dependency_overrides.
- Devuelve únicamente código Python, sin explicaciones.
- Este es el intento {intento}.

FEEDBACK DEL INTENTO ANTERIOR:
{correccion}

CONTRATO DEL PLANNER:
{contrato_json}
""".strip()


def _quitar_cerca_python(contenido: str) -> str:
    """Elimina una cerca Markdown ```python si el modelo la agregó."""
    texto = contenido.strip()
    if texto.startswith("```"):
        lineas = texto.splitlines()
        if lineas and lineas[0].strip().startswith("```"):
            lineas.pop(0)
        if lineas and lineas[-1].strip() == "```":
            lineas.pop()
        texto = "\n".join(lineas).strip()
    return texto + "\n" if texto else ""
