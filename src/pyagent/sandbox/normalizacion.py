"""Normalización y hash del error de un intento (HU-14, Regla 2 de arquitectura.md).

El Reviewer calcula `hash_error` con estas funciones sobre la salida de pytest que
devuelve el sandbox; el orquestador solo compara hashes consecutivos. Viven en
`sandbox` porque normalizan su salida y porque los agentes no se importan entre sí.

Dos errores que solo difieren en rutas, números de línea, direcciones de memoria o
duraciones son "el mismo error" y producen el mismo hash.
"""

from __future__ import annotations

import hashlib
import re

# El orden importa: primero se reemplazan las rutas (pueden contener ":12:" o
# números) y después los números de línea, direcciones y tiempos.
_PATRONES: tuple[tuple[re.Pattern[str], str], ...] = (
    # Rutas Windows: C:\Users\...\x.py, C:/tmp/x.py, \\servidor\carpeta\x.py
    (
        re.compile(r"(?:(?<![A-Za-z])[A-Za-z]:|\\\\[^\\/\s]+)[\\/][^\s:\"'(),]*"),
        "<ruta>",
    ),
    # Rutas absolutas Unix: /tmp/pytest-of-x/test_0/x.py, /app/src/x.py
    (re.compile(r"(?<![\w.<>])/(?:[^\s:\"'(),/]+/)*[^\s:\"'(),/]+"), "<ruta>"),
    # Direcciones de memoria: 0x7f3a2c1b9d60
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), "<mem>"),
    # Números de línea: 'line 42', 'línea 42', 'x.py:42:' y 'x.py:42'
    (re.compile(r"\b(l[ií]nea|line)\s+\d+", re.IGNORECASE), r"\1 <n>"),
    (re.compile(r":\d+(?::\d+)?(?=[:\s]|$)", re.MULTILINE), ":<n>"),
    # Duraciones: 'in 0.12s', '1.5 seconds', '123ms', '0:00:01.20'
    (
        re.compile(
            r"\b\d+(?:\.\d+)?\s*(?:ms|s|sec|secs|seconds?|segundos?|min|minutes?)\b",
            re.IGNORECASE,
        ),
        "<t>",
    ),
    (re.compile(r"\b\d+:\d{2}:\d{2}(?:\.\d+)?\b"), "<t>"),
)
_ESPACIOS = re.compile(r"[ \t]+")


def normalizar_error(texto: str) -> str:
    """Quita del error lo que cambia entre ejecuciones sin cambiar la causa.

    Reemplaza rutas absolutas y temporales (Windows y Linux), números de línea,
    direcciones de memoria y duraciones por marcadores fijos, y compacta espacios.

    Args:
        texto: salida de error de pytest (traceback o mensaje).

    Returns:
        El texto normalizado, estable entre ejecuciones del mismo error.
    """
    normalizado = texto.replace("\r\n", "\n")
    for patron, reemplazo in _PATRONES:
        normalizado = patron.sub(reemplazo, normalizado)
    lineas = (_ESPACIOS.sub(" ", linea).strip() for linea in normalizado.split("\n"))
    return "\n".join(linea for linea in lineas if linea)


def hash_error(texto: str) -> str:
    """SHA-256 (64 hex) del error normalizado; es el `hash_error` de review_result."""
    return hashlib.sha256(normalizar_error(texto).encode("utf-8")).hexdigest()
