"""Puente JS ↔ Python para la Bienvenida (se pasa a pywebview como ``js_api``)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from pyagent.app import recientes


class Api:
    """Métodos que la interfaz llama con ``window.pywebview.api.<método>()``."""

    def __init__(self, archivo_recientes: str | Path | None = None) -> None:
        self._archivo = archivo_recientes

    def listar_recientes(self) -> list[dict[str, Any]]:
        return recientes.listar(archivo=self._archivo)

    def abrir_reciente(self, ruta: str) -> dict[str, Any]:
        return recientes.abrir(ruta, archivo=self._archivo)

    def quitar_reciente(self, ruta: str) -> bool:
        return recientes.quitar(ruta, archivo=self._archivo)

    def registrar_reciente(
        self, nombre: str, origen: str, ruta: str, url: str | None = None
    ) -> None:
        """La usan HU-01 (abrir carpeta) y HU-02 (clonar) al abrir un proyecto."""
        recientes.registrar(nombre, origen, ruta, url, archivo=self._archivo)