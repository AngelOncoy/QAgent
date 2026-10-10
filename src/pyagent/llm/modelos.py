"""Tipos compartidos por los clientes LLM real y simulado."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class RespuestaLLM:
    """Respuesta uniforme producida por cualquier cliente LLM.

    Atributos:
        contenido: texto generado por el modelo.
        tokens_entrada: tokens consumidos por el prompt.
        tokens_salida: tokens generados en la respuesta.
        costo_usd: costo informado o calculado para la llamada.
        modelo: identificador del modelo utilizado.
        datos_json: respuesta JSON original, si se necesita conservar.
    """

    contenido: str
    tokens_entrada: int
    tokens_salida: int
    costo_usd: float
    modelo: str
    datos_json: dict[str, Any] | None = None


class ClienteLLM(Protocol):
    """Interfaz común que deben cumplir los clientes LLM."""

    def generar(self, prompt: str, rol: str = "generator") -> RespuestaLLM:
        """Genera una respuesta para el rol indicado."""
        ...
