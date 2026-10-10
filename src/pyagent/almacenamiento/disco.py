"""Lectura y escritura de archivos del almacenamiento (EN-07).

Todo se escribe de forma atómica: primero en un temporal de la misma carpeta y luego
`os.replace`, para que un cierre a mitad de escritura nunca deje un archivo a medias.
Siempre en UTF-8, para que el contenido sea el mismo en Windows y en Linux.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class ErrorAlmacen(Exception):
    """Error base del almacenamiento; su mensaje se puede mostrar al usuario."""


class DatoNoEncontrado(ErrorAlmacen):
    """El archivo pedido no existe."""


class DatoCorrupto(ErrorAlmacen):
    """El archivo existe pero no es un JSON válido o no tiene el formato esperado."""


def escribir_texto_atomico(ruta: Path, texto: str) -> None:
    """Escribe `texto` en `ruta` de forma atómica, creando la carpeta si falta.

    Raises:
        OSError: si no se puede escribir.
    """
    ruta.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporal = tempfile.mkstemp(
        prefix=f".{ruta.name}.", suffix=".tmp", dir=ruta.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as archivo:
            archivo.write(texto)
        os.replace(temporal, ruta)
    except BaseException:
        Path(temporal).unlink(missing_ok=True)
        raise


def escribir_json_atomico(ruta: Path, datos: Any) -> None:
    """Escribe `datos` como JSON legible (indentado, sin escapar acentos).

    Raises:
        OSError: si no se puede escribir.
    """
    escribir_texto_atomico(ruta, json.dumps(datos, indent=2, ensure_ascii=False))


def leer_json_objeto(ruta: Path) -> dict[str, Any]:
    """Lee un archivo JSON cuyo contenido debe ser un objeto.

    Raises:
        DatoNoEncontrado: si el archivo no existe.
        DatoCorrupto: si no se puede leer, no es JSON o no es un objeto.
    """
    try:
        texto = ruta.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise DatoNoEncontrado(f"No existe el archivo: {ruta}") from exc
    except OSError as exc:
        raise DatoCorrupto(f"No se pudo leer {ruta}: {exc}") from exc
    try:
        datos = json.loads(texto)
    except ValueError as exc:
        raise DatoCorrupto(f"El archivo {ruta} no es un JSON válido: {exc}") from exc
    if not isinstance(datos, dict):
        raise DatoCorrupto(f"El archivo {ruta} no contiene un objeto JSON.")
    return datos
