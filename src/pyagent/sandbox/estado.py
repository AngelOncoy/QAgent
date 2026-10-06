"""Estado del sandbox para la interfaz: si Docker responde y si existe la imagen base."""

from __future__ import annotations

import contextlib

from pyagent.sandbox.modelos import (
    IMAGEN_BASE,
    MENSAJE_NO_INSTALADO,
    clasificar_docker_caido,
)

TIMEOUT_PING_S = 3

MENSAJE_OK = "Docker Desktop iniciado y la imagen base del sandbox está lista."
MENSAJE_SIN_IMAGEN = (
    f"Falta la imagen base '{IMAGEN_BASE}'. Constrúyela una vez con Docker Desktop abierto: "
    'set PYTHONPATH=src y python -c "from pyagent.sandbox import construir_imagen_base; '
    'construir_imagen_base()"'
)


def estado_docker() -> dict[str, str]:
    """Consulta el estado del sandbox sin lanzar excepciones.

    Usa un timeout corto para no bloquear a quien la llama si Docker no responde.

    Returns:
        Diccionario `{"estado": ..., "mensaje": ...}` con estado "ok", "sin_imagen",
        "no_iniciado" o "no_instalado".
    """
    try:
        import docker
        from docker.errors import ImageNotFound
    except ImportError:
        return _estado("no_instalado", MENSAJE_NO_INSTALADO)

    cliente = None
    try:
        cliente = docker.from_env(timeout=TIMEOUT_PING_S)
        cliente.ping()
        cliente.images.get(IMAGEN_BASE)
    except ImageNotFound:
        return _estado("sin_imagen", MENSAJE_SIN_IMAGEN)
    except Exception:  # noqa: BLE001 — cualquier fallo de conexión o timeout = Docker no disponible
        return _estado(*clasificar_docker_caido())
    finally:
        if cliente is not None:
            with contextlib.suppress(Exception):
                cliente.close()
    return _estado("ok", MENSAJE_OK)


def _estado(estado: str, mensaje: str) -> dict[str, str]:
    """Arma el diccionario de estado que consume la interfaz."""
    return {"estado": estado, "mensaje": mensaje}
