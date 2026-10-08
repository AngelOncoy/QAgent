"""Bitácora de la corrida en la consola de Python (HU-09: seguir la corrida en vivo).

Cada paso de la corrida se imprime con hora en la terminal donde se abrió la aplicación::

    14:32:05 INFO    [Planner Agent] services/pricing.py :: calculate_discount() — Spec vigente… (0/9)
    14:32:07 WARNING [Reviewer / Sandbox Guard] services/inventory.py :: reserve_stock_atomic() — Aserciones…

Usa el módulo estándar `logging` (y no `print`) para que pase por el filtro de claves de
EN-06: las claves de `.env` nunca llegan a la consola.
"""

from __future__ import annotations

import html
import logging
import re
import sys
from typing import IO, Any

from pyagent.config.carga import Claves, FiltroSecretos

NOMBRE = "qagent"
FORMATO = "%(asctime)s %(levelname)-7s %(message)s"
FORMATO_HORA = "%H:%M:%S"
LARGO_MAXIMO = 300

# Tipos de evento del Monitor que merecen atención (aparecen resaltados en la pantalla).
TIPOS_DE_ALERTA = frozenset({"guard", "watch", "oracle", "stuck"})

registro = logging.getLogger(NOMBRE)

_ETIQUETAS_HTML = re.compile(r"<[^>]+>")
_ESPACIOS = re.compile(r"\s+")


def configurar_registro(
    claves: Claves | None = None, flujo: IO[str] | None = None
) -> logging.Logger:
    """Imprime la bitácora en la consola, con hora y sin claves.

    Se puede llamar varias veces: reemplaza el handler anterior en lugar de duplicarlo.

    Args:
        claves: claves de `.env` que deben ocultarse si aparecen en un mensaje.
        flujo: dónde escribir (por defecto la salida estándar).
    """
    flujo = flujo if flujo is not None else sys.stdout
    # Una consola de Windows antigua no admite todos los caracteres (→, ✓…): se sustituyen
    # en lugar de romper el mensaje.
    reconfigurar = getattr(flujo, "reconfigure", None)
    if callable(reconfigurar):
        try:
            reconfigurar(errors="replace")
        except (OSError, ValueError):
            pass

    for anterior in [
        h for h in registro.handlers if getattr(h, "_de_la_bitacora", False)
    ]:
        registro.removeHandler(anterior)

    handler = logging.StreamHandler(flujo)
    handler.setFormatter(logging.Formatter(FORMATO, FORMATO_HORA))
    handler.addFilter(FiltroSecretos(claves if claves is not None else Claves()))
    handler._de_la_bitacora = True  # type: ignore[attr-defined]
    registro.addHandler(handler)
    registro.setLevel(logging.INFO)
    registro.propagate = (
        False  # el handler propio ya imprime: no duplicar por el logger raíz
    )
    return registro


def limpiar_texto(texto: Any, maximo: int = LARGO_MAXIMO) -> str:
    """Deja un texto de la pantalla listo para una línea de consola.

    Quita las etiquetas HTML y las entidades, junta los saltos de línea y los espacios, y lo
    recorta: así un mensaje de la interfaz no puede partir ni falsear líneas de la bitácora.
    """
    limpio = html.unescape(
        _ETIQUETAS_HTML.sub("", str(texto if texto is not None else ""))
    )
    limpio = _ESPACIOS.sub(" ", limpio).strip()
    return limpio if len(limpio) <= maximo else limpio[: maximo - 1].rstrip() + "…"


def registrar_evento(evento: dict[str, Any]) -> str:
    """Registra un paso de la corrida que llegó desde la pantalla y devuelve la línea.

    Args:
        evento: `{"tipo", "agente", "archivo", "funcion", "mensaje", "progreso"}`; todos
            opcionales. Los tipos de alerta (`TIPOS_DE_ALERTA`) se registran como WARNING.

    Returns:
        El texto registrado (útil para pruebas).
    """
    if not isinstance(evento, dict):
        evento = {}
    agente = limpiar_texto(evento.get("agente") or evento.get("tipo") or "corrida", 60)
    donde = " :: ".join(
        parte
        for parte in (
            limpiar_texto(evento.get("archivo"), 120),
            limpiar_texto(evento.get("funcion"), 120),
        )
        if parte
    )
    mensaje = limpiar_texto(evento.get("mensaje"))
    progreso = limpiar_texto(evento.get("progreso"), 20)

    linea = f"[{agente}]"
    if donde:
        linea += f" {donde}"
    if mensaje:
        # el guion separa el lugar (archivo :: función) del mensaje; sin lugar no hay nada que separar
        linea += f" — {mensaje}" if donde else f" {mensaje}"
    if progreso:
        linea += f" ({progreso})"

    nivel = logging.WARNING if evento.get("tipo") in TIPOS_DE_ALERTA else logging.INFO
    registro.log(nivel, "%s", linea)
    return linea
