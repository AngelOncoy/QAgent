"""Configuración de las pruebas de la app: marcador `red` para pruebas con internet."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# El repo no es un paquete instalable todavía: se expone src/ para importar pyagent.
SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def pytest_configure(config: pytest.Config) -> None:
    """Registra el marcador de las pruebas que necesitan internet."""
    config.addinivalue_line(
        "markers",
        "red: prueba de integración que necesita internet (omitir con -m 'not red')",
    )
