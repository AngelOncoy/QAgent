"""Interfaces que el orquestador espera de cada agente (contratos de EN-01).

Los agentes reales (HU-11, HU-14) y los simulados de los tests las implementan.
Ningún agente conoce a los otros: solo reciben y devuelven dicts de contrato.
"""

from __future__ import annotations

from typing import Any, Protocol

Contrato = dict[str, Any]


class Planner(Protocol):
    """Rol Planner: diseña los casos de prueba de un módulo."""

    def planificar(self, modulo: dict[str, Any]) -> list[Contrato]:
        """Recibe un módulo de `analizar_proyecto()` y devuelve sus planner_contract.v2."""
        ...


class Generator(Protocol):
    """Rol Generator: escribe el test de un objetivo."""

    def generar(
        self, contrato: Contrato, intento: int, feedback: str | None
    ) -> Contrato:
        """Devuelve un generated_test para `contrato` en el intento indicado."""
        ...


class Reviewer(Protocol):
    """Rol Reviewer/Executor: ejecuta en el sandbox y emite el veredicto."""

    def revisar(
        self, contrato: Contrato, test: Contrato, test_anterior: Contrato | None
    ) -> Contrato:
        """Devuelve un review_result para el test."""
        ...
