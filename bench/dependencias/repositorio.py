"""Repositorio en memoria para transacciones de la API."""

from __future__ import annotations

from typing import Any


class RepositorioTransferencias:
    """Almacenamiento de transacciones para la API."""

    def __init__(self) -> None:
        self._transferencias: dict[str, dict[str, Any]] = {}

    def guardar(self, id_transaccion: str, datos: dict[str, Any]) -> None:
        self._transferencias[id_transaccion] = datos

    def obtener(self, id_transaccion: str) -> dict[str, Any] | None:
        return self._transferencias.get(id_transaccion)


_REPOSITORIO_GLOBAL = RepositorioTransferencias()


def obtener_repositorio() -> RepositorioTransferencias:
    """Dependencia inyectable de FastAPI para el repositorio."""
    return _REPOSITORIO_GLOBAL
