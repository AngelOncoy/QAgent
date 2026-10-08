"""Fixtures de las pruebas del sandbox (el marcador `docker` está registrado en pytest.ini)."""

from __future__ import annotations

import pytest

from pyagent.sandbox import (
    DockerNoDisponible,
    construir_imagen_base,
    obtener_cliente,
)
from pyagent.sandbox.imagen import IMAGEN_BASE, _imagen_existe


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
