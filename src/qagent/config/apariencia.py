"""Tema de la interfaz (oscuro o claro) guardado en el config.local.toml del usuario."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from qagent.almacenamiento.disco import escribir_texto_atomico
from qagent.config import carga as config_carga
from qagent.config.roles import ENCABEZADO_LOCAL

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

#: Temas permitidos por la interfaz y el sistema de tokens.
TEMAS_VALIDOS = ("oscuro", "claro")
TEMA_POR_DEFECTO = "oscuro"

_CABECERA = re.compile(r"^\s*\[")
_SECCION_APARIENCIA = re.compile(r"^\s*\[\s*apariencia\s*\]\s*(#.*)?$")


def leer_tema(ruta_local: str | Path | None = None) -> str:
    """Lee el tema guardado en `config.local.toml`, o devuelve el tema por defecto ('oscuro')."""
    ruta_local = Path(ruta_local) if ruta_local else config_carga.RUTA_CONFIG_LOCAL
    if not ruta_local.exists():
        return TEMA_POR_DEFECTO
    try:
        datos = tomllib.loads(ruta_local.read_text(encoding="utf-8"))
        tema = datos.get("apariencia", {}).get("tema")
        if tema in TEMAS_VALIDOS:
            return str(tema)
    except (OSError, tomllib.TOMLDecodeError):
        return TEMA_POR_DEFECTO
    return TEMA_POR_DEFECTO


def guardar_tema(
    tema: str,
    ruta_local: str | Path | None = None,
) -> dict[str, Any]:
    """Guarda el tema elegido en `[apariencia]` del `config.local.toml`.

    Args:
        tema: 'oscuro' o 'claro'.
        ruta_local: `config.local.toml` del usuario (se crea si falta).

    Returns:
        dict: ``{"ok", "mensaje", "tema"}``.
    """
    if tema not in TEMAS_VALIDOS:
        return {
            "ok": False,
            "mensaje": f"El tema debe ser uno de: {', '.join(TEMAS_VALIDOS)}.",
            "tema": TEMA_POR_DEFECTO,
        }
    ruta_local = Path(ruta_local) if ruta_local else config_carga.RUTA_CONFIG_LOCAL
    texto = (
        ruta_local.read_text(encoding="utf-8")
        if ruta_local.exists()
        else ENCABEZADO_LOCAL
    )
    nuevo = reemplazar_seccion_apariencia(texto, tema)
    try:
        tomllib.loads(nuevo)
    except tomllib.TOMLDecodeError:
        return {
            "ok": False,
            "mensaje": "Tu configuración local tiene un error de formato; no se guardó nada.",
            "tema": TEMA_POR_DEFECTO,
        }
    try:
        ruta_local.parent.mkdir(parents=True, exist_ok=True)
        escribir_texto_atomico(ruta_local, nuevo)
    except OSError:
        return {
            "ok": False,
            "mensaje": "No se pudo guardar la configuración de apariencia.",
            "tema": TEMA_POR_DEFECTO,
        }
    return {
        "ok": True,
        "mensaje": f"Apariencia guardada: tema {tema}.",
        "tema": tema,
    }


def reemplazar_seccion_apariencia(texto: str, tema: str) -> str:
    """Reemplaza (o agrega al final) la sección `[apariencia]`; el resto no cambia."""
    filas = texto.splitlines()
    bloque = [
        "[apariencia]",
        "# Elegido desde la aplicación (Configuración).",
        f'tema = "{tema}"',
    ]
    inicio: int | None = None
    fin: int | None = None
    for i, fila in enumerate(filas):
        if inicio is None:
            if _SECCION_APARIENCIA.match(fila):
                inicio = i
        elif _CABECERA.match(fila):
            fin = i
            break
    if inicio is None:
        cuerpo = texto.rstrip()
        adicion = "\n" + "\n".join(bloque) + "\n"
        return (cuerpo + "\n" if cuerpo else "") + adicion.lstrip("\n")
    if fin is None:
        fin = len(filas)
    return "\n".join(filas[:inicio] + bloque + filas[fin:]) + "\n"
