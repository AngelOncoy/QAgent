"""Limpieza de lo que el sandbox deja en Docker: contenedores huérfanos e imágenes viejas.

Cada ejecución borra su contenedor al terminar (`ejecucion._eliminar`), pero si la app se
cierra de golpe a mitad de una corrida ese paso no llega a correr y el contenedor queda.
Además, `preparar_imagen` guarda una imagen `qagent-sandbox:req-<hash>` por cada
requirements.txt distinto; sirve de caché, pero cada una ocupa cientos de MB.

`limpiar_al_iniciar` resuelve las dos cosas al abrir la app. Nunca toca la imagen base ni
contenedores sin la etiqueta del sandbox, y nunca lanza excepciones.
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from qagent.almacenamiento.disco import escribir_json_atomico
from qagent.sandbox.modelos import ETIQUETA_CONTENEDOR, REPOSITORIO
from qagent.usuario import carpeta_usuario

registro = logging.getLogger(__name__)

#: Último uso de cada imagen `req-` (segundos desde la época), en `~/.qagent/`.
RUTA_USOS = carpeta_usuario() / "imagenes_sandbox.json"
#: Prefijo del tag de las imágenes derivadas por requirements.txt.
PREFIJO_REQ = "req-"
#: Una imagen `req-` sin usar durante este tiempo se borra (se reconstruye si vuelve a hacer falta).
DIAS_SIN_USO = 30
#: Un contenedor del sandbox que sigue corriendo se considera huérfano pasado este tiempo.
#: Ninguna ejecución dura tanto (el timeout por defecto es de 120 s); el margen evita
#: borrar el contenedor de otra ventana de QAgent que esté corriendo pruebas.
ANTIGUEDAD_HUERFANO_S = 60 * 60
TIMEOUT_DOCKER_S = 10

_NANOSEGUNDOS = re.compile(r"(\.\d{1,6})\d*")


def leer_usos(ruta: Path | None = None) -> dict[str, float]:
    """Último uso de cada imagen `req-`; vacío si el archivo no existe o está dañado."""
    ruta = ruta or RUTA_USOS
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(datos, dict):
        return {}
    return {
        str(k): float(v)
        for k, v in datos.items()
        if isinstance(v, (int, float)) and not isinstance(v, bool)
    }


def registrar_uso(
    imagen: str, ruta: Path | None = None, ahora: float | None = None
) -> None:
    """Anota que una corrida usó `imagen`. Solo cuenta para las imágenes `req-`.

    No lanza excepciones: si no se puede escribir, la imagen solo pierde su fecha de uso.
    """
    if not _es_imagen_req(imagen):
        return
    ruta = ruta or RUTA_USOS
    usos = leer_usos(ruta)
    usos[imagen] = time.time() if ahora is None else ahora
    try:
        escribir_json_atomico(ruta, usos)
    except OSError as exc:
        registro.warning("No se pudo anotar el uso de la imagen %s: %s", imagen, exc)


def eliminar_contenedores_huerfanos(cliente: Any, ahora: float | None = None) -> int:
    """Borra los contenedores del sandbox que quedaron de una corrida interrumpida.

    Se borran los detenidos y los que siguen corriendo desde hace más de
    `ANTIGUEDAD_HUERFANO_S`. Solo se buscan los que llevan `ETIQUETA_CONTENEDOR`.

    Returns:
        Cuántos contenedores se borraron.
    """
    ahora = time.time() if ahora is None else ahora
    filtro = {"label": [f"{k}={v}" for k, v in ETIQUETA_CONTENEDOR.items()]}
    borrados = 0
    for contenedor in cliente.containers.list(all=True, filters=filtro):
        if contenedor.status == "running":
            creado = _segundos(contenedor.attrs.get("Created"))
            if creado is None or ahora - creado < ANTIGUEDAD_HUERFANO_S:
                continue
        try:
            contenedor.remove(force=True)
            borrados += 1
        except Exception as exc:  # noqa: BLE001 — uno que no se borra no detiene los demás
            registro.warning(
                "No se pudo borrar el contenedor %s: %s", contenedor.id, exc
            )
    return borrados


def eliminar_imagenes_sin_uso(
    cliente: Any, usos: dict[str, float], ahora: float | None = None
) -> list[str]:
    """Borra las imágenes `req-` que no se usan desde hace más de `DIAS_SIN_USO` días.

    El último uso sale de `usos`; si una imagen no aparece, cuenta su fecha de creación.
    Una imagen que está usando un contenedor no se borra (Docker lo rechaza).

    Returns:
        Etiquetas de las imágenes borradas.
    """
    ahora = time.time() if ahora is None else ahora
    limite = ahora - DIAS_SIN_USO * 24 * 60 * 60
    borradas = []
    for imagen in cliente.images.list(name=REPOSITORIO):
        for etiqueta in imagen.tags:
            if not _es_imagen_req(etiqueta):
                continue
            ultimo = usos.get(etiqueta, _segundos(imagen.attrs.get("Created")))
            if ultimo is None or ultimo > limite:
                continue
            try:
                cliente.images.remove(etiqueta)
                borradas.append(etiqueta)
            except Exception as exc:  # noqa: BLE001 — en uso o ya borrada: se intenta la próxima vez
                registro.warning("No se pudo borrar la imagen %s: %s", etiqueta, exc)
    return borradas


def limpiar_al_iniciar(cliente: Any = None, ruta_usos: Path | None = None) -> dict:
    """Borra contenedores huérfanos e imágenes `req-` sin uso. Pensada para el arranque.

    Si Docker no está instalado o no responde, no hace nada.

    Returns:
        `{"contenedores": int, "imagenes": [etiquetas]}`, o `{}` si Docker no respondió.
    """
    propio = cliente is None
    try:
        if propio:
            import docker

            cliente = docker.from_env(timeout=TIMEOUT_DOCKER_S)
            cliente.ping()
        contenedores = eliminar_contenedores_huerfanos(cliente)
        ruta_usos = ruta_usos or RUTA_USOS
        imagenes = eliminar_imagenes_sin_uso(cliente, leer_usos(ruta_usos))
    except Exception:  # noqa: BLE001 — sin Docker no hay nada que limpiar
        return {}
    finally:
        if propio and cliente is not None:
            with contextlib.suppress(Exception):
                cliente.close()
    if imagenes:
        usos = leer_usos(ruta_usos)
        with contextlib.suppress(OSError):
            escribir_json_atomico(
                ruta_usos, {k: v for k, v in usos.items() if k not in imagenes}
            )
    return {"contenedores": contenedores, "imagenes": imagenes}


def _es_imagen_req(etiqueta: str) -> bool:
    """True si la etiqueta es una imagen derivada `qagent-sandbox:req-…`."""
    return etiqueta.startswith(f"{REPOSITORIO}:{PREFIJO_REQ}")


def _segundos(fecha: Any) -> float | None:
    """Convierte una fecha de Docker («2026-10-18T10:00:00.123456789Z») a segundos."""
    if not isinstance(fecha, str):
        return None
    # Docker da nanosegundos; datetime solo acepta hasta microsegundos.
    texto = _NANOSEGUNDOS.sub(r"\1", fecha.strip()).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(texto).timestamp()
    except ValueError:
        return None
