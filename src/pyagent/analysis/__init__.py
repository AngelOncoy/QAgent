"""Análisis estático del código del usuario (solo AST, nunca se ejecuta)."""

from pyagent.analysis.analyzer import analizar_proyecto, analizar_proyecto_json
from pyagent.analysis.laundering import (
    Asercion,
    DiferenciaAsercion,
    ResultadoComparacion,
    comparar_aserciones,
    extraer_aserciones,
)

__all__ = [
    "Asercion",
    "DiferenciaAsercion",
    "ResultadoComparacion",
    "analizar_proyecto",
    "analizar_proyecto_json",
    "comparar_aserciones",
    "extraer_aserciones",
]
