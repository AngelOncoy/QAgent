"""Rutas relativas de pruebas dentro de una carpeta temporal controlada (#184)."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

_RESERVADO_WINDOWS = re.compile(
    r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", re.IGNORECASE
)


def ruta_de_prueba(carpeta: Path, archivo: str) -> Path:
    """Valida una ruta portable, sin escapes ni enlaces, y devuelve su destino.

    No crea ni ejecuta el archivo. Rechaza rutas absolutas, componentes punto,
    separadores Windows, unidades, flujos alternativos y dispositivos reservados.
    La creación posterior ocurre únicamente dentro de la carpeta aislada.
    """
    if (
        not isinstance(archivo, str)
        or len(archivo) > 512
        or not re.fullmatch(
            r"[A-Za-z0-9_$][A-Za-z0-9_.$-]*(?:/[A-Za-z0-9_$][A-Za-z0-9_.$-]*)*", archivo
        )
    ):
        raise ValueError("El archivo de prueba debe ser una ruta relativa segura.")
    partes = PurePosixPath(archivo).parts
    if any(p.endswith(".") or _RESERVADO_WINDOWS.fullmatch(p) for p in partes):
        raise ValueError("La ruta de prueba contiene un nombre reservado o ambiguo.")
    raiz = carpeta.resolve()
    destino = carpeta.joinpath(*partes)
    actual = carpeta
    for parte in partes:
        actual = actual / parte
        if actual.is_symlink():
            raise ValueError("La ruta de prueba no admite enlaces simbólicos.")
    if not destino.resolve().is_relative_to(raiz):
        raise ValueError("El archivo de prueba sale de su carpeta aislada.")
    return destino
