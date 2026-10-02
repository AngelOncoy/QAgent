"""Conexión con Docker mediante el SDK oficial (paquete `docker`)."""

from __future__ import annotations

import shutil

import docker
from docker.errors import DockerException

from pyagent.sandbox.modelos import DockerNoDisponible

MENSAJE_NO_INSTALADO = "Docker no está instalado. Instala Docker Desktop para ejecutar las pruebas en el sandbox."
MENSAJE_NO_INICIADO = "Docker Desktop no está iniciado. Ábrelo, espera a que termine de arrancar y vuelve a intentar."


def obtener_cliente() -> docker.DockerClient:
    """Crea un cliente Docker y verifica que el servicio responde.

    Returns:
        Cliente conectado al daemon de Docker.

    Raises:
        DockerNoDisponible: si Docker no está instalado o no está iniciado.
    """
    try:
        cliente = docker.from_env()
        cliente.ping()
    except DockerException as exc:
        raise DockerNoDisponible(_mensaje_docker_caido()) from exc
    return cliente


def _mensaje_docker_caido() -> str:
    """Elige el mensaje según si el ejecutable de Docker existe en el sistema."""
    if shutil.which("docker") is None:
        return MENSAJE_NO_INSTALADO
    return MENSAJE_NO_INICIADO
