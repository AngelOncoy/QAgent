"""Almacenamiento de las corridas en `.pyagent/` dentro del proyecto analizado."""

from pyagent.storage.registro import (
    RutasCorrida,
    construir_log,
    construir_results,
    escribir_corrida,
    nuevo_run_id,
)

__all__ = [
    "RutasCorrida",
    "construir_log",
    "construir_results",
    "escribir_corrida",
    "nuevo_run_id",
]
