"""Límites de verificación que el usuario puede ver y ajustar desde Configuración.

- **Intentos por función** (`[reintentos] max_intentos`): se pueden fijar en el
  `config.local.toml` del usuario, que se superpone al `config.toml` del equipo. Van de
  1 a 3, el tope de los contratos entre agentes.
- **Tiempo máximo por prueba** (`[sandbox] timeout_s`): solo se lee. `[sandbox]` es una
  sección del equipo (`SECCIONES_SOLO_EQUIPO`, EN-03) y `config.local.toml` no la cambia.

Igual que `roles.py`, se edita el texto del archivo local sección por sección (el resto
no se toca), se comprueba que el resultado sea TOML válido antes de escribir y se
escribe de forma atómica.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from qagent.almacenamiento.disco import escribir_texto_atomico
from qagent.config import carga as config_carga
from qagent.config.carga import superponer_config
from qagent.config.roles import ENCABEZADO_LOCAL
from qagent.sandbox.modelos import LIMITES_POR_DEFECTO

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.10
    import tomli as tomllib

#: Rango de intentos por función que aceptan los contratos (1 a 3).
MIN_INTENTOS = 1
MAX_INTENTOS = 3

_CABECERA = re.compile(r"^\s*\[")
_SECCION_REINTENTOS = re.compile(r"^\s*\[\s*reintentos\s*\]\s*(#.*)?$")


def leer_limites(
    ruta_config: str | Path | None = None,
    ruta_local: str | Path | None = None,
) -> dict[str, Any]:
    """Valores vigentes de los límites, para mostrarlos en Configuración.

    Returns:
        dict: ``{"ok", "max_intentos", "max_intentos_equipo", "intentos_min",
        "intentos_max", "timeout_s", "timeout_editable"}``; con ``ok`` False, ``mensaje``.
    """
    ruta_config = Path(ruta_config) if ruta_config else config_carga.RUTA_CONFIG
    ruta_local = Path(ruta_local) if ruta_local else config_carga.RUTA_CONFIG_LOCAL
    equipo = _leer_toml(ruta_config)
    if equipo is None:
        return {"ok": False, "mensaje": "No se pudo leer la configuración del equipo."}
    local = _leer_toml(ruta_local) if ruta_local.is_file() else {}
    if local is None:
        return {
            "ok": False,
            "mensaje": "Tu configuración local tiene un error de formato.",
        }
    datos = superponer_config(equipo, local)
    sandbox = equipo.get("sandbox", {}) or {}
    return {
        "ok": True,
        "max_intentos": _intentos(datos),
        "max_intentos_equipo": _intentos(equipo),
        "intentos_min": MIN_INTENTOS,
        "intentos_max": MAX_INTENTOS,
        "timeout_s": int(sandbox.get("timeout_s", LIMITES_POR_DEFECTO.timeout_s)),
        "timeout_editable": False,
    }


def guardar_max_intentos(
    valor: Any,
    ruta_local: str | Path | None = None,
) -> dict[str, Any]:
    """Guarda los intentos por función en `[reintentos]` del `config.local.toml`.

    Args:
        valor: entero entre `MIN_INTENTOS` y `MAX_INTENTOS`.
        ruta_local: `config.local.toml` del usuario (se crea si falta).

    Returns:
        dict: ``{"ok", "mensaje"}``. Si el valor no es válido no se escribe nada.
    """
    if isinstance(valor, bool) or not isinstance(valor, int):
        return {"ok": False, "mensaje": "Los intentos deben ser un número entero."}
    if not MIN_INTENTOS <= valor <= MAX_INTENTOS:
        return {
            "ok": False,
            "mensaje": f"Los intentos van de {MIN_INTENTOS} a {MAX_INTENTOS} por función.",
        }
    ruta_local = Path(ruta_local) if ruta_local else config_carga.RUTA_CONFIG_LOCAL
    texto = (
        ruta_local.read_text(encoding="utf-8")
        if ruta_local.exists()
        else ENCABEZADO_LOCAL
    )
    nuevo = reemplazar_seccion_reintentos(texto, valor)
    try:
        tomllib.loads(nuevo)
    except tomllib.TOMLDecodeError:
        return {
            "ok": False,
            "mensaje": "Tu configuración local tiene un error de formato; no se guardó nada.",
        }
    try:
        ruta_local.parent.mkdir(parents=True, exist_ok=True)
        escribir_texto_atomico(ruta_local, nuevo)
    except OSError:
        return {"ok": False, "mensaje": "No se pudo guardar la configuración."}
    return {
        "ok": True,
        "mensaje": f"Guardado: hasta {valor} {'intento' if valor == 1 else 'intentos'} por función.",
    }


def reemplazar_seccion_reintentos(texto: str, valor: int) -> str:
    """Reemplaza (o agrega al final) la sección `[reintentos]`; el resto no cambia."""
    filas = texto.splitlines()
    bloque = [
        "[reintentos]",
        "# Elegido desde la aplicación (Configuración).",
        f"max_intentos = {valor}",
        "",
    ]
    inicio = next(
        (i for i, fila in enumerate(filas) if _SECCION_REINTENTOS.match(fila)), None
    )
    if inicio is None:
        if filas and filas[-1].strip():
            bloque = ["", *bloque]
        filas.extend(bloque)
    else:
        fin = inicio + 1
        while fin < len(filas) and not _CABECERA.match(filas[fin]):
            fin += 1
        filas[inicio:fin] = bloque
    while filas and not filas[-1].strip():
        filas.pop()
    return "\n".join(filas) + "\n"


def _intentos(datos: dict[str, Any]) -> int:
    valor = (datos.get("reintentos") or {}).get("max_intentos", MAX_INTENTOS)
    try:
        return max(MIN_INTENTOS, min(MAX_INTENTOS, int(valor)))
    except (TypeError, ValueError):
        return MAX_INTENTOS


def _leer_toml(ruta: Path) -> dict[str, Any] | None:
    try:
        with open(ruta, "rb") as archivo:
            return tomllib.load(archivo)
    except (OSError, tomllib.TOMLDecodeError):
        return None
