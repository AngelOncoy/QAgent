"""Registro de proyectos recientes en ``~/.pyagent/recientes.json`` — HU-01.

Formato del archivo: una lista JSON (más reciente primero) de entradas
``{"nombre", "origen", "ruta", "url", "ultima_apertura"}``.

La HU-03 extenderá este módulo con listar, reabrir y quitar; aquí solo se
cargan y registran entradas.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

MAXIMO_RECIENTES = 50
ORIGENES = ("local", "git")
CAMPOS = ("nombre", "origen", "ruta", "url", "ultima_apertura")


def ruta_por_defecto() -> Path:
    """Devuelve la ubicación del archivo de recientes en el home del usuario."""
    return Path.home() / ".pyagent" / "recientes.json"


def _clave(ruta: str) -> str:
    """Normaliza una ruta para compararla (Windows no distingue mayúsculas)."""
    return os.path.normcase(os.path.normpath(ruta))


def _es_entrada_valida(entrada: Any) -> bool:
    """Indica si una entrada leída del archivo tiene el formato esperado."""
    if not isinstance(entrada, dict) or any(c not in entrada for c in CAMPOS):
        return False
    textos = ("nombre", "ruta", "ultima_apertura")
    return (
        all(isinstance(entrada[c], str) and entrada[c] for c in textos)
        and entrada["origen"] in ORIGENES
        and (entrada["url"] is None or isinstance(entrada["url"], str))
    )


def cargar(archivo: str | os.PathLike[str] | None = None) -> list[dict[str, Any]]:
    """Lee la lista completa de proyectos recientes, más reciente primero.

    Tolera un archivo ausente, ilegible o dañado (devuelve lista vacía) y
    descarta las entradas inválidas. Nunca lanza excepciones.

    Args:
        archivo: Ruta del JSON; por defecto ``ruta_por_defecto()``.
    """
    destino = Path(archivo) if archivo is not None else ruta_por_defecto()
    try:
        datos = json.loads(destino.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(datos, list):
        return []
    return [{c: e[c] for c in CAMPOS} for e in datos if _es_entrada_valida(e)]


def _escribir(destino: Path, entradas: list[dict[str, Any]]) -> None:
    """Escribe el JSON de forma atómica (temporal en la misma carpeta + replace)."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporal = tempfile.mkstemp(
        dir=destino.parent, prefix=".recientes-", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as salida:
            json.dump(entradas, salida, ensure_ascii=False, indent=2)
        os.replace(temporal, destino)
    except BaseException:
        Path(temporal).unlink(missing_ok=True)
        raise


def registrar(
    nombre: str,
    origen: str,
    ruta: str,
    url: str | None = None,
    archivo: str | os.PathLike[str] | None = None,
    ahora: datetime | None = None,
) -> None:
    """Agrega un proyecto al inicio de los recientes (o lo sube si ya estaba).

    Args:
        nombre: Nombre visible del proyecto.
        origen: ``"local"`` o ``"git"``.
        ruta: Carpeta del proyecto en disco.
        url: URL del repositorio (solo para ``origen="git"``).
        archivo: Ruta del JSON; por defecto ``ruta_por_defecto()``.
        ahora: Momento de la apertura; por defecto, la hora local actual (con zona horaria).

    Raises:
        ValueError: si ``origen`` no es válido o falta ``nombre`` o ``ruta``.
        OSError: si no se puede escribir el archivo.
    """
    if origen not in ORIGENES:
        raise ValueError(f"Origen no válido: {origen!r}. Use 'local' o 'git'.")
    if not nombre or not ruta:
        raise ValueError("El nombre y la ruta del proyecto son obligatorios.")

    destino = Path(archivo) if archivo is not None else ruta_por_defecto()
    momento = (ahora or datetime.now().astimezone()).isoformat(timespec="seconds")
    nueva = {
        "nombre": nombre,
        "origen": origen,
        "ruta": ruta,
        "url": url,
        "ultima_apertura": momento,
    }
    clave = _clave(ruta)
    resto = [e for e in cargar(destino) if _clave(e["ruta"]) != clave]
    _escribir(destino, [nueva, *resto][:MAXIMO_RECIENTES])
