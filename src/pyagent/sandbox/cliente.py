"""Conexión con Docker mediante el SDK oficial (paquete `docker`)."""

from __future__ import annotations

import docker
from docker.errors import DockerException

from pyagent.sandbox.modelos import DockerNoDisponible, clasificar_docker_caido


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
        _, mensaje = clasificar_docker_caido()
        raise DockerNoDisponible(mensaje) from exc
    return cliente
