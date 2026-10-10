"""Agente Planner: diseña casos de prueba a partir del análisis AST (HU-11).

El LLM solo propone los **casos** (entrada, valor esperado u excepción y su origen).
Todo lo que ya se sabe por el análisis estático lo pone el código: versión del
contrato, módulo, huella SHA-256, tipo, nombre, firma, `critical` y `llama_a`. Así el
modelo no puede inventar esos campos, el prompt es más corto (menos tokens) y el
contrato siempre coincide con el código analizado.
"""

from __future__ import annotations

import json
from typing import Any

from pyagent import contracts
from pyagent.contracts import ContratoInvalido
from pyagent.llm import ClienteLLM, TokenTracker
from pyagent.llm.fake import MARCA_MODULO, MARCA_OBJETIVOS

#: Orígenes válidos de un valor esperado para una función (`planner_contract.v2`).
#: No existe "ejecucion": el valor esperado nunca sale de ejecutar el código.
ORIGENES = ("firma", "tipo", "docstring")

_EJEMPLO_RESPUESTA = [
    {
        "objetivo": "calcular_descuento",
        "casos": [
            {
                "id": "descuento_normal",
                "descripcion": "Aplica el porcentaje al precio",
                "entrada": {"precio": 100.0, "porcentaje": 20.0},
                "valor_esperado": 80.0,
                "origen": "docstring",
            },
            {
                "id": "porcentaje_invalido",
                "entrada": {"precio": 100.0, "porcentaje": 150.0},
                "excepcion": "ValueError",
                "origen": "docstring",
            },
        ],
    }
]

# Contrato mínimo para validar un caso suelto contra el schema del Planner.
_CONTRATO_DE_PRUEBA = {
    "version": "2",
    "modulo": "x.py",
    "huella": "0" * 64,
    "tipo": "funcion",
    "objetivo": "x",
    "firma": "()",
    "critical": False,
}


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
        #: Qué se descartó en la última llamada (objetivos o casos) y por qué.
        self.descartados: list[str] = []

    def planificar(self, modulo: dict[str, Any]) -> list[dict[str, Any]]:
        """Devuelve un `planner_contract.v2` por cada función del módulo con casos.

        Las funciones que el modelo no cubre, los objetivos que no existen en el
        módulo y los casos inválidos se descartan (quedan en `self.descartados`) en
        lugar de tumbar la corrida del módulo.

        Raises:
            ErrorRespuestaPlanner: si la respuesta no es una lista JSON, o si trae
                objetivos pero ninguno produce un contrato válido.
        """
        self.descartados = []
        funciones = {f["nombre"]: f for f in modulo.get("funciones", [])}
        if not funciones:
            return []

        respuesta = self.cliente.generar(self._crear_prompt(modulo), rol="planner")
        self.tracker.registrar(
            agente="planner",
            modelo=respuesta.modelo,
            tokens_entrada=respuesta.tokens_entrada,
            tokens_salida=respuesta.tokens_salida,
            costo_usd=respuesta.costo_usd,
            es_simulado=self.es_simulado,
        )

        try:
            propuesta = json.loads(_quitar_cerca_json(respuesta.contenido))
        except json.JSONDecodeError as error:
            raise ErrorRespuestaPlanner(
                "El Planner no devolvió JSON válido."
            ) from error
        if not isinstance(propuesta, list):
            raise ErrorRespuestaPlanner(
                "El Planner debe devolver una lista de objetivos."
            )

        plan: list[dict[str, Any]] = []
        for elemento in propuesta:
            vistos = {contrato["objetivo"] for contrato in plan}
            contrato = self._armar_contrato(modulo, funciones, elemento, vistos)
            if contrato is not None:
                plan.append(contrato)

        if propuesta and not plan:
            detalle = "; ".join(self.descartados[:3])
            raise ErrorRespuestaPlanner(
                f"El Planner no produjo ningún contrato válido ({detalle})."
            )
        return plan

    # --- Construcción del contrato ----------------------------------------------

    def _armar_contrato(
        self,
        modulo: dict[str, Any],
        funciones: dict[str, dict[str, Any]],
        elemento: Any,
        vistos: set[str],
    ) -> dict[str, Any] | None:
        if not isinstance(elemento, dict):
            self.descartados.append("un elemento del plan no es un objeto JSON")
            return None
        nombre = elemento.get("objetivo")
        if nombre not in funciones:
            self.descartados.append(f"objetivo desconocido: {nombre!r}")
            return None
        if nombre in vistos:
            self.descartados.append(f"objetivo repetido: {nombre}")
            return None

        funcion = funciones[nombre]
        casos = self._casos_validos(nombre, elemento.get("casos"))
        if not casos:
            self.descartados.append(f"{nombre}: sin casos válidos")
            return None

        contrato = {
            "version": "2",
            "modulo": modulo["ruta"],
            "huella": modulo["huella"],
            "tipo": "funcion",
            "objetivo": nombre,
            "firma": funcion.get("firma") or "()",
            # HU-06 (Sprint 2) permitirá marcar funciones críticas; hasta entonces
            # solo es crítica si el análisis lo indica.
            "critical": bool(funcion.get("critical", False)),
            "llama_a": list(dict.fromkeys(funcion.get("llama_a") or [])),
            "casos": casos,
        }
        try:
            contracts.validar(contracts.PLANNER, contrato)
        except ContratoInvalido as error:
            self.descartados.append(f"{nombre}: {error}")
            return None
        return contrato

    def _casos_validos(self, nombre: str, casos: Any) -> list[dict[str, Any]]:
        """Se queda con los casos que cumplen el schema; descarta el resto."""
        if not isinstance(casos, list):
            return []
        validos: list[dict[str, Any]] = []
        for caso in casos:
            if not isinstance(caso, dict):
                self.descartados.append(f"{nombre}: un caso no es un objeto JSON")
                continue
            if any(caso.get("id") == previo["id"] for previo in validos):
                self.descartados.append(f"{nombre}: caso repetido {caso.get('id')!r}")
                continue
            try:
                contracts.validar(
                    contracts.PLANNER, {**_CONTRATO_DE_PRUEBA, "casos": [caso]}
                )
            except ContratoInvalido as error:
                self.descartados.append(f"{nombre}: caso {caso.get('id')!r}: {error}")
                continue
            validos.append(caso)
        return validos

    # --- Prompt -------------------------------------------------------------------

    @staticmethod
    def _crear_prompt(modulo: dict[str, Any]) -> str:
        """Prompt compacto: solo firma y docstring de cada función (sin el código)."""
        objetivos = [
            {
                "nombre": funcion["nombre"],
                "firma": funcion.get("firma"),
                "docstring": funcion.get("docstring"),
            }
            for funcion in modulo.get("funciones", [])
        ]
        ejemplo = json.dumps(_EJEMPLO_RESPUESTA, ensure_ascii=False)
        return f"""
Diseña casos de prueba unitaria pytest para las funciones de un módulo Python.

REGLAS OBLIGATORIAS:
- No ejecutes ni importes el código del usuario: no lo tienes y no hace falta.
- El valor esperado sale SOLO de la firma, los tipos o el docstring. Si el docstring
  no permite deducir un valor con certeza, no inventes ese caso.
- Incluye casos normales, de límite y de error cuando el docstring los describa.
- Cada caso tiene: "id" (minúsculas, números y _), "entrada" (objeto con los
  argumentos por nombre), "origen" (uno de: {", ".join(ORIGENES)}) y
  "valor_esperado" o "excepcion" (nombre de la excepción, ej. "ValueError").
  "descripcion" es opcional.
- Devuelve SOLO una lista JSON con un objeto por función:
  {{"objetivo": nombre, "casos": [...]}}. Sin explicaciones ni bloques Markdown.

EJEMPLO DE RESPUESTA:
{ejemplo}

{MARCA_MODULO} {modulo["ruta"]}
{MARCA_OBJETIVOS} {json.dumps(objetivos, ensure_ascii=False)}
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
