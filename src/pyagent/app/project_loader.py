"""Inspección de una carpeta local de proyecto.

Solo lee el sistema de archivos: nunca importa ni ejecuta el código del usuario.
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

IGNORED_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        "node_modules",
        ".pyagent",
        "site-packages",
        ".pytest_cache",
        ".ruff_cache",
    }
)

MSG_SIN_PY = "Esta carpeta no contiene archivos .py"


class FolderError(Exception):
    """La carpeta no se puede usar como proyecto (no existe, no es carpeta o sin permiso)."""


@dataclass(frozen=True)
class ProjectInfo:
    """Resumen de una carpeta de proyecto."""

    nombre: str
    ruta: str
    py_count: int
    has_requirements: bool

    @property
    def has_python(self) -> bool:
        """Indica si la carpeta tiene al menos un archivo .py."""
        return self.py_count > 0

    def to_dict(self) -> dict[str, object]:
        """Devuelve el resumen como diccionario simple."""
        return asdict(self)


def normalize_path(path: str | os.PathLike[str]) -> Path:
    """Devuelve la ruta absoluta de ``path`` sin exigir que exista."""
    return Path(path).expanduser().resolve()


def _is_link(entry: os.DirEntry[str]) -> bool:
    """Indica si la entrada es un enlace simbólico o una unión (junction) de Windows."""
    if entry.is_symlink():
        return True
    is_junction = getattr(entry, "is_junction", None)  # Python 3.12+
    return bool(is_junction and is_junction())


def count_py_files(root: Path) -> int:
    """Cuenta los archivos .py bajo ``root`` de forma recursiva.

    Ignora las carpetas de ``IGNORED_DIRS`` y no sigue enlaces simbólicos.
    Las subcarpetas sin permiso de lectura se omiten con un aviso en el log.
    """
    total = 0
    pending = [root]
    while pending:
        current = pending.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if _is_link(entry):
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            if entry.name not in IGNORED_DIRS:
                                pending.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False) and entry.name.endswith(".py"):
                            total += 1
                    except OSError as exc:
                        logger.warning("No se pudo leer %s: %s", entry.path, exc)
        except OSError as exc:
            if current == root:
                raise
            logger.warning("Se omite la carpeta %s: %s", current, exc)
    return total


def inspect_folder(path: str | os.PathLike[str]) -> ProjectInfo:
    """Inspecciona una carpeta y devuelve su resumen.

    Lanza ``FolderError`` con un mensaje en español si la carpeta no existe,
    no es una carpeta o no se puede leer.
    """
    root = normalize_path(path)
    if not root.exists():
        raise FolderError(f"La carpeta no existe: {root}")
    if not root.is_dir():
        raise FolderError(f"La ruta no es una carpeta: {root}")
    try:
        py_count = count_py_files(root)
    except PermissionError as exc:
        raise FolderError(f"No tienes permiso de lectura sobre la carpeta: {root}") from exc
    except OSError as exc:
        raise FolderError(f"No se pudo leer la carpeta {root}: {exc.strerror or exc}") from exc
    return ProjectInfo(
        nombre=root.name or str(root),
        ruta=str(root),
        py_count=py_count,
        has_requirements=(root / "requirements.txt").is_file(),
    )
