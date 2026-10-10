"""Agente Planner: diseña casos de prueba a partir del análisis AST."""

from __future__ import annotations

import json
from typing import Any

from pyagent import contracts
from pyagent.llm import ClienteLLM, TokenTracker


class ErrorRespuestaPlanner(ValueError):
    """El Planner devolvió una respuesta que no puede utilizarse."""


class PlannerAgent:
    """Genera contratos de prueba sin ejecutar el código del usuario."""

    def __init__(
        self,
        cliente: ClienteLLM,
        tracker: TokenTracker,
        *,
        es_simulado: bool = False,
    ) -> None:
        """Inicializa el Planner con su cliente y registro de tokens."""
        self.cliente = cliente
        self.tracker = tracker
        self.es_simulado = es_simulado

    def planificar(self, modulo: dict[str, Any]) -> list[dict[str, Any]]:
        """Genera un contrato por cada función o endpoint del módulo."""
        prompt = self._crear_prompt(modulo)
        respuesta = self.cliente.generar(prompt, rol="planner")

        self.tracker.registrar(
            agente="planner",
            modelo=respuesta.modelo,
            tokens_entrada=respuesta.tokens_entrada,
            tokens_salida=respuesta.tokens_salida,
            costo_usd=respuesta.costo_usd,
            es_simulado=self.es_simulado,
        )

        try:
            plan = json.loads(_quitar_cerca_json(respuesta.contenido))
        except json.JSONDecodeError as error:
            raise ErrorRespuestaPlanner(
                "El Planner no devolvió JSON válido."
            ) from error

        if not isinstance(plan, list):
            raise ErrorRespuestaPlanner(
                "El Planner debe devolver una lista de contratos."
            )

        for contrato in plan:
            if not isinstance(contrato, dict):
                raise ErrorRespuestaPlanner(
                    "Cada elemento del plan debe ser un objeto JSON."
                )
            contracts.validar(contracts.PLANNER, contrato)

        return plan

    @staticmethod
    def _crear_prompt(modulo: dict[str, Any]) -> str:
        estructura = json.dumps(modulo, ensure_ascii=False, indent=2)
        return f"""
Diseña casos de prueba pytest para el módulo descrito abajo.

REGLAS OBLIGATORIAS:
- No ejecutes ni importes el código del usuario.
- Usa únicamente la firma, tipos, docstring y declaraciones FastAPI.
- Cada valor esperado debe declarar su origen.
- Devuelve una lista JSON de contratos planner_contract.v2.
- No agregues explicaciones ni bloques Markdown.
- Genera un contrato independiente por función o endpoint.
- Las funciones llamadas por el objetivo deben aparecer en llama_a.

ESTRUCTURA DEL MÓDULO:
{estructura}
""".strip()


def _quitar_cerca_json(contenido: str) -> str:
    """Elimina una cerca Markdown ```json si el modelo la agregó."""
    texto = contenido.strip()
    if not texto.startswith("```"):
        return texto

    lineas = texto.splitlines()
    if lineas and lineas[0].strip().startswith("```"):
        lineas.pop(0)
    if lineas and lineas[-1].strip() == "```":
        lineas.pop()
    return "\n".join(lineas).strip()
