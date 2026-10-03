"""Análisis estático del código del usuario (solo AST, nunca se ejecuta)."""

from pyagent.analysis.analyzer import analizar_proyecto, analizar_proyecto_json

__all__ = ["analizar_proyecto", "analizar_proyecto_json"]
