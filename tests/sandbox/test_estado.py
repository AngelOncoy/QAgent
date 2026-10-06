"""Pruebas de `estado_docker` con el cliente Docker simulado (no necesitan Docker)."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import docker
import pytest
from docker.errors import DockerException, ImageNotFound
from requests.exceptions import ConnectionError as ErrorConexion
from requests.exceptions import ReadTimeout

from pyagent.sandbox import IMAGEN_BASE, estado_docker, modelos
from pyagent.sandbox.estado import TIMEOUT_PING_S


def _consultar(
    cliente: MagicMock | None = None,
    error: Exception | None = None,
    ejecutable="docker",
):
    """Ejecuta `estado_docker` con `docker.from_env` y el ejecutable de Docker simulados.

    Returns:
        Tupla (estado devuelto, mock de `docker.from_env`).
    """
    with (
        patch.object(
            docker, "from_env", return_value=cliente, side_effect=error
        ) as from_env,
        patch.object(modelos.shutil, "which", return_value=ejecutable),
    ):
        return estado_docker(), from_env


def test_sdk_no_instalado():
    with patch.dict(sys.modules, {"docker": None}):
        estado = estado_docker()

    assert estado["estado"] == "no_instalado"
    assert "Instala Docker Desktop" in estado["mensaje"]


def test_ejecutable_ausente_es_no_instalado():
    estado, _ = _consultar(error=DockerException("sin pipe"), ejecutable=None)

    assert estado == {"estado": "no_instalado", "mensaje": modelos.MENSAJE_NO_INSTALADO}


@pytest.mark.parametrize(
    "error",
    [DockerException("sin pipe"), ErrorConexion("rechazada")],
    ids=["docker", "conexion"],
)
def test_daemon_apagado_es_no_iniciado(error):
    estado, _ = _consultar(error=error)

    assert estado == {"estado": "no_iniciado", "mensaje": modelos.MENSAJE_NO_INICIADO}


def test_timeout_del_ping_es_no_iniciado():
    cliente = MagicMock()
    cliente.ping.side_effect = ReadTimeout("sin respuesta")

    estado, from_env = _consultar(cliente)

    assert estado["estado"] == "no_iniciado"
    assert from_env.call_args.kwargs["timeout"] == TIMEOUT_PING_S
    cliente.close.assert_called_once()


def test_ping_ok_sin_imagen_base():
    cliente = MagicMock()
    cliente.images.get.side_effect = ImageNotFound("no existe")

    estado, _ = _consultar(cliente)

    assert estado["estado"] == "sin_imagen"
    assert "construir_imagen_base" in estado["mensaje"]
    cliente.images.get.assert_called_once_with(IMAGEN_BASE)
    cliente.close.assert_called_once()


def test_ping_ok_con_imagen_base():
    cliente = MagicMock()

    estado, _ = _consultar(cliente)

    assert estado["estado"] == "ok"
    cliente.ping.assert_called_once()
    cliente.close.assert_called_once()


def test_nunca_lanza_excepciones_aunque_falle_close():
    cliente = MagicMock()
    cliente.close.side_effect = RuntimeError("fallo al cerrar")

    estado, _ = _consultar(cliente)

    assert estado["estado"] == "ok"
