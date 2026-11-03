"""Humo E2E determinista con Playwright (#186)."""

from qagent.e2e.deteccion import detectar_plan_e2e
from qagent.e2e.ejecucion import ejecutar_humo_e2e, leer_resultado_e2e

__all__ = ["detectar_plan_e2e", "ejecutar_humo_e2e", "leer_resultado_e2e"]
