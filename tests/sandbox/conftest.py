"""Configuración de las pruebas del sandbox: marcador `docker` y fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# El repo no es un paquete instalable todavía: se expone src/ para importar pyagent.
SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pyagent.sandbox import (
    DockerNoDisponible,
    construir_imagen_base,
    obtener_cliente,
)
from pyagent.sandbox.imagen import IMAGEN_BASE, _imagen_existe


def pytest_configure(config: pytest.Config) -> None:
    """Registra el marcador de las pruebas que necesitan Docker."""
    config.addinivalue_line(
        "markers", "docker: prueba de integración que necesita Docker Desktop iniciado"
    )


@pytest.fixture(scope="session")
def cliente_docker():
    """Cliente Docker real; omite la prueba si Docker no está disponible."""
    try:
        return obtener_cliente()
    except DockerNoDisponible as exc:
        pytest.skip(str(exc))


@pytest.fixture(scope="session")
def imagen_base(cliente_docker) -> str:
    """Imagen base del sandbox; la construye una vez si no existe."""
    if not _imagen_existe(cliente_docker, IMAGEN_BASE):
        construir_imagen_base(cliente_docker)
    return IMAGEN_BASE
