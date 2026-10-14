"""Carpeta de datos de la persona que usa QAgent: `~/.qagent/` (TA-06).

Todo lo que es del usuario y no del programa vive aquí: sus claves (`.env`), su
configuración de modelos (`config.local.toml`), los proyectos recientes y la corrida de
demostración. La carpeta del programa puede ser de solo lectura y se reemplaza al
actualizar, así que nunca se escribe en ella.

Este módulo no importa nada de `qagent`, para que cualquier parte pueda usarlo.
"""

from __future__ import annotations

from pathlib import Path

NOMBRE_CARPETA = ".qagent"


def carpeta_usuario() -> Path:
    """`~/.qagent/` del usuario actual (puede no existir todavía)."""
    return Path.home() / NOMBRE_CARPETA
