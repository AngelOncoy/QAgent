"""Paso 1 del sandbox (con red): imagen base e imagen derivada por proyecto.

Construir una imagen puede tardar muchos minutos (por ejemplo, un requirements.txt con
torch u opencv). Si se pasa `avanzar`, el log de Docker se lee en streaming y cada paso
útil se traduce a un texto para personas («Descargando torch (821.0 MB)») que la corrida
reenvía al Monitor. Sin `avanzar`, la construcción es la de siempre (`images.build`).
"""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
import tempfile
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import docker
from docker.errors import APIError, BuildError, ImageNotFound

from qagent.sandbox.cliente import obtener_cliente
from qagent.sandbox.modelos import (
    IMAGEN_BASE,
    REPOSITORIO,
    ConstruccionCancelada,
    ErrorConstruccionImagen,
    ImagenNoEncontrada,
)

registro = logging.getLogger(__name__)

#: Recibe un texto para personas con el paso actual de la construcción.
Avance = Callable[[str], None]

DOCKERFILE_BASE = Path(__file__).with_name("Dockerfile")

DOCKERFILE_DERIVADO = f"""\
FROM {IMAGEN_BASE}
USER root
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt
USER sandbox
"""

#: Textos de cada fase (los ve la persona en el Monitor).
AVISO_BASE = (
    "Construyendo el entorno aislado base: solo la primera vez en este equipo "
    "y necesita internet"
)
AVISO_DEPENDENCIAS = (
    "Instalando las dependencias del proyecto (requirements.txt): la primera vez "
    "puede tardar varios minutos"
)
AVISO_LISTO = "Dependencias instaladas en el entorno aislado"

_COLECTANDO = re.compile(r"^Collecting\s+([A-Za-z0-9][A-Za-z0-9_.\-]*)")
_DESCARGANDO = re.compile(r"^Downloading\s+(\S+?)(?:\s+\(([^)]+)\))?\s*$")
_INSTALANDO = re.compile(r"^Installing collected packages:\s*(.+)$")
_INSTALADO = re.compile(r"^Successfully installed\b")


def construir_imagen_base(
    cliente: docker.DockerClient | None = None, avanzar: Avance | None = None
) -> str:
    """Construye la imagen base del sandbox a partir del Dockerfile del módulo.

    El contexto de build es una carpeta temporal que solo contiene el Dockerfile.

    Args:
        cliente: cliente Docker; si es None se crea uno con `obtener_cliente()`.
        avanzar: recibe el avance de la construcción en textos para personas.

    Returns:
        Etiqueta de la imagen base.

    Raises:
        ErrorConstruccionImagen: si la construcción falla.
    """
    cliente = cliente or obtener_cliente()
    _avisar(avanzar, AVISO_BASE)
    contexto = Path(tempfile.mkdtemp(prefix="qagent-base-"))
    try:
        shutil.copyfile(DOCKERFILE_BASE, contexto / "Dockerfile")
        _construir(
            cliente,
            contexto,
            IMAGEN_BASE,
            "No se pudo construir la imagen base",
            avanzar,
        )
    finally:
        shutil.rmtree(contexto, ignore_errors=True)
    return IMAGEN_BASE


def etiqueta_para_requirements(contenido: bytes) -> str:
    """Devuelve la etiqueta de la imagen derivada según el hash del requirements.txt.

    Args:
        contenido: bytes del archivo requirements.txt.

    Returns:
        Etiqueta con la forma `qagent-sandbox:req-<sha256[:12]>`.
    """
    return f"{REPOSITORIO}:req-{hashlib.sha256(contenido).hexdigest()[:12]}"


def preparar_imagen(
    ruta_proyecto: str | Path,
    cliente: docker.DockerClient | None = None,
    avanzar: Avance | None = None,
) -> str:
    """Prepara la imagen con las dependencias del proyecto (paso 1, con red).

    Si el proyecto tiene requirements.txt, construye (o reutiliza) una imagen derivada
    de la base que lo instala. El contexto de build solo contiene ese archivo: nunca el
    código del proyecto ni su `.env`. Si la imagen ya existe no se construye nada ni se
    informa avance.

    Args:
        ruta_proyecto: carpeta raíz del proyecto del usuario.
        cliente: cliente Docker; si es None se crea uno con `obtener_cliente()`.
        avanzar: recibe el avance de la construcción en textos para personas.

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

    _avisar(avanzar, AVISO_DEPENDENCIAS)
    contexto = Path(tempfile.mkdtemp(prefix="qagent-req-"))
    try:
        (contexto / "requirements.txt").write_bytes(contenido)
        (contexto / "Dockerfile").write_text(DOCKERFILE_DERIVADO, encoding="utf-8")
        _construir(
            cliente,
            contexto,
            etiqueta,
            "No se pudieron instalar las dependencias del requirements.txt del proyecto",
            avanzar,
        )
    finally:
        shutil.rmtree(contexto, ignore_errors=True)
    _avisar(avanzar, AVISO_LISTO)
    return etiqueta


def describir_linea(linea: str) -> str | None:
    """Traduce una línea del log de construcción a un texto para personas.

    Solo se informan los pasos útiles de pip; el resto (pasos de Docker, rutas,
    advertencias) devuelve None.

    Args:
        linea: una línea del log de `docker build`.

    Returns:
        Texto como «Descargando torch (821.0 MB)», o None si la línea no aporta.
    """
    texto = linea.strip()
    if coincidencia := _DESCARGANDO.match(texto):
        archivo = coincidencia.group(1).rstrip("/").rsplit("/", 1)[-1]
        nombre = re.split(r"-\d", archivo, maxsplit=1)[0]
        tamano = coincidencia.group(2)
        return f"Descargando {nombre}" + (f" ({tamano})" if tamano else "")
    if coincidencia := _COLECTANDO.match(texto):
        return f"Preparando {coincidencia.group(1)}"
    if coincidencia := _INSTALANDO.match(texto):
        paquetes = [p for p in coincidencia.group(1).split(",") if p.strip()]
        cantidad = len(paquetes)
        return f"Instalando {cantidad} {'paquete' if cantidad == 1 else 'paquetes'}"
    if _INSTALADO.match(texto):
        return AVISO_LISTO
    return None


def _imagen_existe(cliente: docker.DockerClient, etiqueta: str) -> bool:
    """Indica si la imagen existe localmente."""
    try:
        cliente.images.get(etiqueta)
    except ImageNotFound:
        return False
    return True


def _construir(
    cliente: docker.DockerClient,
    contexto: Path,
    etiqueta: str,
    mensaje: str,
    avanzar: Avance | None = None,
) -> None:
    """Construye una imagen y traduce los errores de Docker a `ErrorConstruccionImagen`.

    Con `avanzar`, lee el log en streaming (API de bajo nivel) para informar el avance.
    """
    if avanzar is not None:
        _construir_con_avance(cliente, contexto, etiqueta, mensaje, avanzar)
        return
    try:
        cliente.images.build(path=str(contexto), tag=etiqueta, rm=True, forcerm=True)
    except BuildError as exc:
        raise ErrorConstruccionImagen(
            f"{mensaje}: {exc.msg}", _texto_log(exc.build_log)
        ) from exc
    except APIError as exc:
        raise ErrorConstruccionImagen(f"{mensaje}: {exc.explanation}") from exc


def _construir_con_avance(
    cliente: docker.DockerClient,
    contexto: Path,
    etiqueta: str,
    mensaje: str,
    avanzar: Avance,
) -> None:
    """`docker build` leyendo el log a medida que llega; cada paso útil va a `avanzar`."""
    log: list[str] = []
    partes = None
    try:
        partes = cliente.api.build(
            path=str(contexto), tag=etiqueta, rm=True, forcerm=True, decode=True
        )
        for parte in partes:
            if parte.get("error"):
                log.append(str(parte["error"]))
                raise ErrorConstruccionImagen(
                    f"{mensaje}: {str(parte['error']).strip()}", "".join(log)
                )
            texto = parte.get("stream")
            if not texto:
                continue
            log.append(texto)
            for linea in texto.splitlines():
                descripcion = describir_linea(linea)
                if descripcion:
                    _avisar(avanzar, descripcion)
    except ConstruccionCancelada:
        # #148: cerrar el log corta la conexión con Docker en vez de esperar el final.
        cerrar = getattr(partes, "close", None)
        if cerrar is not None:
            cerrar()
        raise
    except APIError as exc:
        raise ErrorConstruccionImagen(
            f"{mensaje}: {exc.explanation}", "".join(log)
        ) from exc


def _avisar(avanzar: Avance | None, texto: str) -> None:
    """Informa el avance sin dejar que un fallo de quien escucha corte la construcción."""
    if avanzar is None:
        return
    try:
        avanzar(texto)
    except ConstruccionCancelada:
        raise
    except Exception:  # noqa: BLE001 - el avance es solo informativo
        registro.warning(
            "No se pudo informar el avance de la construcción.", exc_info=True
        )


def _texto_log(build_log: Iterable[dict[str, Any]]) -> str:
    """Une las líneas del log de build de Docker en un solo texto."""
    partes = []
    for entrada in build_log:
        texto = entrada.get("stream") or entrada.get("error") or ""
        partes.append(texto)
    return "".join(partes)
