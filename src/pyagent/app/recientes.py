"""Registro de proyectos recientes en ``~/.pyagent/recientes.json`` — HU-01.

Formato del archivo: una lista JSON (más reciente primero) de entradas
``{"nombre", "origen", "ruta", "url", "ultima_apertura"}``.

La HU-03 agrega ``listar`` (hasta 10, con ``encontrada``), ``abrir``, ``quitar``
y ``registrar_corrida``. Esta última guarda el campo opcional ``ultima_corrida``,
que ``registrar`` conserva al volver a abrir un proyecto.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

MAXIMO_RECIENTES = 50
MAXIMO_VISIBLES = 10
ORIGENES = ("local", "git")
CAMPOS = ("nombre", "origen", "ruta", "url", "ultima_apertura")
CAMPO_CORRIDA = (
    "ultima_corrida"  # opcional: solo existe si el proyecto tuvo una corrida
)


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
    return [_normalizar(e) for e in datos if _es_entrada_valida(e)]


def _normalizar(entrada: dict[str, Any]) -> dict[str, Any]:
    """Deja solo los campos conocidos; ``ultima_corrida`` únicamente si es un texto."""
    limpia = {c: entrada[c] for c in CAMPOS}
    corrida = entrada.get(CAMPO_CORRIDA)
    if isinstance(corrida, str) and corrida:
        limpia[CAMPO_CORRIDA] = corrida
    return limpia


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
    previas = cargar(destino)
    anterior = next((e for e in previas if _clave(e["ruta"]) == clave), None)
    if anterior and CAMPO_CORRIDA in anterior:
        nueva[CAMPO_CORRIDA] = anterior[
            CAMPO_CORRIDA
        ]  # reabrir no borra la última corrida
    resto = [e for e in previas if _clave(e["ruta"]) != clave]
    _escribir(destino, [nueva, *resto][:MAXIMO_RECIENTES])


def _existe(ruta: str) -> bool:
    """Indica si la carpeta del proyecto sigue en su lugar."""
    try:
        return Path(ruta).is_dir()
    except OSError:
        return False


def listar(
    archivo: str | os.PathLike[str] | None = None, limite: int = MAXIMO_VISIBLES
) -> list[dict[str, Any]]:
    """Devuelve los ``limite`` proyectos más recientes para la Bienvenida (HU-03).

    Cada entrada trae ``ultima_corrida`` (``None`` si no hubo corridas) y
    ``encontrada`` (``False`` si la carpeta ya no existe). Nunca lanza excepciones.
    """
    return [
        {**e, CAMPO_CORRIDA: e.get(CAMPO_CORRIDA), "encontrada": _existe(e["ruta"])}
        for e in cargar(archivo)[:limite]
    ]


def abrir(ruta: str, archivo: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Reabre un proyecto reciente: comprueba la carpeta y lo sube al inicio.

    Returns:
        ``{"ok": True, "proyecto": entrada}`` o ``{"ok": False, "motivo", "error"}``
        con motivo ``"no_en_lista"`` o ``"no_encontrada"``.

    Raises:
        OSError: si no se puede escribir el archivo.
    """
    entrada = next(
        (e for e in cargar(archivo) if _clave(e["ruta"]) == _clave(ruta)), None
    )
    if entrada is None:
        return {
            "ok": False,
            "motivo": "no_en_lista",
            "error": "El proyecto no está en Proyectos recientes.",
        }
    if not _existe(entrada["ruta"]):
        return {
            "ok": False,
            "motivo": "no_encontrada",
            "error": f"La carpeta ya no existe: {entrada['ruta']}",
        }
    registrar(
        entrada["nombre"], entrada["origen"], entrada["ruta"], entrada["url"], archivo
    )
    return {"ok": True, "proyecto": cargar(archivo)[0]}


def quitar(ruta: str, archivo: str | os.PathLike[str] | None = None) -> bool:
    """Quita un proyecto de la lista (nunca borra su carpeta). ``False`` si no estaba.

    Raises:
        OSError: si no se puede escribir el archivo.
    """
    destino = Path(archivo) if archivo is not None else ruta_por_defecto()
    entradas = cargar(destino)
    resto = [e for e in entradas if _clave(e["ruta"]) != _clave(ruta)]
    if len(resto) == len(entradas):
        return False
    _escribir(destino, resto)
    return True


def registrar_corrida(
    ruta: str,
    fecha: datetime | None = None,
    archivo: str | os.PathLike[str] | None = None,
) -> bool:
    """Guarda la fecha de la última corrida del proyecto (la llama EN-07 al cerrar una).

    Returns:
        ``False`` si el proyecto no está en la lista.
    """
    destino = Path(archivo) if archivo is not None else ruta_por_defecto()
    entradas = cargar(destino)
    for e in entradas:
        if _clave(e["ruta"]) == _clave(ruta):
            e[CAMPO_CORRIDA] = (fecha or datetime.now().astimezone()).isoformat(
                timespec="seconds"
            )
            _escribir(destino, entradas)
            return True
    return False