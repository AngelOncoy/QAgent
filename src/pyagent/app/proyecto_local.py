"""Validación de una carpeta local antes de abrirla como proyecto — HU-01.

Solo lee el sistema de archivos: nunca importa ni ejecuta código del usuario.
Cuenta los ``.py`` con el mismo criterio que el analizador (EN-02), de modo que
nunca se abre un proyecto en el que el analizador no encuentre módulos.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pyagent.analysis.analyzer import listar_archivos_py

SIN_ARCHIVOS_PY = "Esta carpeta no contiene archivos .py"


def _resultado(
    ruta: str, nombre: str, cantidad_py: int = 0, error: str | None = None
) -> dict[str, Any]:
    """Arma el diccionario de respuesta de ``inspeccionar_carpeta``."""
    return {
        "ok": error is None,
        "nombre": nombre,
        "ruta": ruta,
        "cantidad_py": cantidad_py,
        "error": error,
    }


def inspeccionar_carpeta(ruta: str | os.PathLike[str]) -> dict[str, Any]:
    """Indica si una carpeta puede abrirse como proyecto Python.

    Args:
        ruta: Carpeta elegida por el usuario.

    Returns:
        Diccionario con ``ok`` (la carpeta existe y tiene al menos un ``.py``
        analizable), ``nombre`` (nombre de la carpeta), ``ruta`` (absoluta),
        ``cantidad_py`` y ``error`` (mensaje en español o ``None``).
        Nunca lanza excepciones.
    """
    if not str(ruta).strip():
        return _resultado("", "", error="No se indicó ninguna carpeta.")

    carpeta = Path(os.path.abspath(ruta))
    texto = str(carpeta)
    nombre = carpeta.name or texto

    try:
        if not carpeta.exists():
            return _resultado(texto, nombre, error=f"La carpeta no existe: {texto}")
        if not carpeta.is_dir():
            return _resultado(
                texto, nombre, error=f"La ruta no es una carpeta: {texto}"
            )
        # os.walk ignora en silencio los errores de lectura: se comprueba antes
        # que la raíz sea legible para no confundir "sin permisos" con "vacía".
        with os.scandir(carpeta):
            pass
        cantidad = len(listar_archivos_py(carpeta))
    except PermissionError:
        return _resultado(
            texto, nombre, error=f"No hay permisos para leer la carpeta: {texto}"
        )
    except OSError:
        return _resultado(texto, nombre, error=f"No se pudo leer la carpeta: {texto}")

    if cantidad == 0:
        return _resultado(texto, nombre, error=SIN_ARCHIVOS_PY)
    return _resultado(texto, nombre, cantidad_py=cantidad)
