"""Paso 1 del sandbox (con red): imagen base e imagen derivada por proyecto."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import docker
from docker.errors import APIError, BuildError, ImageNotFound

from pyagent.sandbox.cliente import obtener_cliente
from pyagent.sandbox.modelos import ErrorConstruccionImagen, ImagenNoEncontrada

REPOSITORIO = "pyagent-sandbox"
IMAGEN_BASE = f"{REPOSITORIO}:base"
DOCKERFILE_BASE = Path(__file__).with_name("Dockerfile")

DOCKERFILE_DERIVADO = f"""\
FROM {IMAGEN_BASE}
USER root
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt
USER sandbox
"""


def construir_imagen_base(cliente: docker.DockerClient | None = None) -> str:
    """Construye la imagen base del sandbox a partir del Dockerfile del módulo.

    El contexto de build es una carpeta temporal que solo contiene el Dockerfile.

    Args:
        cliente: cliente Docker; si es None se crea uno con `obtener_cliente()`.

    Returns:
        Etiqueta de la imagen base.

    Raises:
        ErrorConstruccionImagen: si la construcción falla.
    """
    cliente = cliente or obtener_cliente()
    contexto = Path(tempfile.mkdtemp(prefix="pyagent-base-"))
    try:
        shutil.copyfile(DOCKERFILE_BASE, contexto / "Dockerfile")
        _construir(
            cliente, contexto, IMAGEN_BASE, "No se pudo construir la imagen base"
        )
    finally:
        shutil.rmtree(contexto, ignore_errors=True)
    return IMAGEN_BASE


def etiqueta_para_requirements(contenido: bytes) -> str:
    """Devuelve la etiqueta de la imagen derivada según el hash del requirements.txt.

    Args:
        contenido: bytes del archivo requirements.txt.

    Returns:
        Etiqueta con la forma `pyagent-sandbox:req-<sha256[:12]>`.
    """
    return f"{REPOSITORIO}:req-{hashlib.sha256(contenido).hexdigest()[:12]}"


def preparar_imagen(
    ruta_proyecto: str | Path, cliente: docker.DockerClient | None = None
) -> str:
    """Prepara la imagen con las dependencias del proyecto (paso 1, con red).

    Si el proyecto tiene requirements.txt, construye (o reutiliza) una imagen derivada
    de la base que lo instala. El contexto de build solo contiene ese archivo: nunca el
    código del proyecto ni su `.env`.

    Args:
        ruta_proyecto: carpeta raíz del proyecto del usuario.
        cliente: cliente Docker; si es None se crea uno con `obtener_cliente()`.

    Returns:
        Etiqueta de la imagen a usar en el paso 2.

    Raises:
        ImagenNoEncontrada: si no existe la imagen base.
        ErrorConstruccionImagen: si falla la instalación de dependencias.
    """
    cliente = cliente or obtener_cliente()
    if not _imagen_existe(cliente, IMAGEN_BASE):
        raise ImagenNoEncontrada(
            f"No existe la imagen base '{IMAGEN_BASE}'. Constrúyela con construir_imagen_base()."
        )

    requirements = Path(ruta_proyecto).resolve() / "requirements.txt"
    if not requirements.is_file():
        return IMAGEN_BASE

    contenido = requirements.read_bytes()
    etiqueta = etiqueta_para_requirements(contenido)
    if _imagen_existe(cliente, etiqueta):
        return etiqueta

    contexto = Path(tempfile.mkdtemp(prefix="pyagent-req-"))
    try:
        (contexto / "requirements.txt").write_bytes(contenido)
        (contexto / "Dockerfile").write_text(DOCKERFILE_DERIVADO, encoding="utf-8")
        _construir(
            cliente,
            contexto,
            etiqueta,
            "No se pudieron instalar las dependencias del requirements.txt del proyecto",
        )
    finally:
        shutil.rmtree(contexto, ignore_errors=True)
    return etiqueta


def _imagen_existe(cliente: docker.DockerClient, etiqueta: str) -> bool:
    """Indica si la imagen existe localmente."""
    try:
        cliente.images.get(etiqueta)
    except ImageNotFound:
        return False
    return True


def _construir(
    cliente: docker.DockerClient, contexto: Path, etiqueta: str, mensaje: str
) -> None:
    """Construye una imagen y traduce los errores de Docker a `ErrorConstruccionImagen`."""
    try:
        cliente.images.build(path=str(contexto), tag=etiqueta, rm=True, forcerm=True)
    except BuildError as exc:
        raise ErrorConstruccionImagen(
            f"{mensaje}: {exc.msg}", _texto_log(exc.build_log)
        ) from exc
    except APIError as exc:
        raise ErrorConstruccionImagen(f"{mensaje}: {exc.explanation}") from exc


def _texto_log(build_log: Iterable[dict[str, Any]]) -> str:
    """Une las líneas del log de build de Docker en un solo texto."""
    partes = []
    for entrada in build_log:
        texto = entrada.get("stream") or entrada.get("error") or ""
        partes.append(texto)
    return "".join(partes)
