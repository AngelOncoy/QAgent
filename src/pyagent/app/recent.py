"""Lista de proyectos recientes guardada en ``~/.pyagent/recientes.json``."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from pyagent.app.project_loader import ProjectInfo

logger = logging.getLogger(__name__)

DEFAULT_PATH: Path = Path.home() / ".pyagent" / "recientes.json"
MAX_RECENT = 10

_KEYS = ("nombre", "ruta", "py_count", "has_requirements", "ultimo_uso")


def _key(ruta: str) -> str:
    """Clave de comparación de rutas (sin distinguir mayúsculas en Windows)."""
    return os.path.normcase(os.path.abspath(ruta))


def _is_valid(entry: object) -> bool:
    """Indica si una entrada del archivo tiene la forma esperada."""
    return (
        isinstance(entry, dict)
        and all(k in entry for k in _KEYS)
        and isinstance(entry["ruta"], str)
    )


def load_recent(path: Path = DEFAULT_PATH) -> list[dict]:
    """Lee los proyectos recientes, del más reciente al más antiguo.

    Si el archivo no existe devuelve una lista vacía. Si está corrupto, registra
    un aviso y también devuelve una lista vacía (el archivo se reescribe al
    guardar el siguiente proyecto).
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.warning("recientes.json ilegible (%s); se reinicia la lista: %s", path, exc)
        return []
    if not isinstance(data, list):
        logger.warning("recientes.json con formato inesperado (%s); se reinicia la lista", path)
        return []
    valid = [entry for entry in data if _is_valid(entry)]
    if len(valid) != len(data):
        logger.warning("Se descartaron %d entradas inválidas de %s", len(data) - len(valid), path)
    return valid[:MAX_RECENT]


def _write_atomic(entries: list[dict], path: Path) -> None:
    """Escribe la lista en UTF-8 usando un temporal y ``os.replace``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".recientes-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(entries, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def add_recent(
    info: ProjectInfo, path: Path = DEFAULT_PATH, now: datetime | None = None
) -> list[dict]:
    """Agrega o actualiza un proyecto y lo deja en el primer lugar.

    Solo acepta proyectos con al menos un archivo .py. Mantiene como máximo
    ``MAX_RECENT`` entradas, sin duplicados por ruta. Devuelve la lista guardada.
    """
    if not info.has_python:
        raise ValueError("Solo se guardan proyectos con archivos .py")
    moment = now or datetime.now(timezone.utc)
    entry = {**info.to_dict(), "ultimo_uso": moment.isoformat(timespec="seconds")}
    key = _key(info.ruta)
    others = [e for e in load_recent(path) if _key(e["ruta"]) != key]
    entries = [entry, *others][:MAX_RECENT]
    _write_atomic(entries, path)
    return entries


def remove_recent(ruta: str, path: Path = DEFAULT_PATH) -> list[dict]:
    """Quita un proyecto de la lista (si está) y devuelve la lista guardada."""
    key = _key(ruta)
    current = load_recent(path)
    entries = [e for e in current if _key(e["ruta"]) != key]
    if len(entries) != len(current):
        _write_atomic(entries, path)
    return entries
