"""Análisis estático del código del usuario (tree-sitter, nunca se ejecuta)."""

from qagent.analysis.analyzer import analizar_proyecto, analizar_proyecto_json
from qagent.analysis.laundering import (
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
