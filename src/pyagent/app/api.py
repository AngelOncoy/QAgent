"""Puente entre la interfaz (JavaScript) y la lógica de la aplicación.

Una instancia de ``Api`` se expone con ``js_api``. Cada método público devuelve
diccionarios simples serializables a JSON. Los atributos son privados para que
pywebview no los exponga a JavaScript.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from pyagent.app import recent
from pyagent.app.project_loader import MSG_SIN_PY, FolderError, ProjectInfo, inspect_folder

logger = logging.getLogger(__name__)

FolderPicker = Callable[[], "str | None"]


def _native_folder_picker() -> str | None:
    """Abre el diálogo nativo de carpetas y devuelve la ruta elegida o ``None``."""
    import webview  # import diferido: la lógica y los tests no dependen de pywebview

    window = webview.active_window() or webview.windows[0]
    result = window.create_file_dialog(webview.FileDialog.FOLDER)
    if not result:
        return None
    return result[0] if isinstance(result, (list, tuple)) else str(result)


def _project_dict(info: ProjectInfo) -> dict[str, object]:
    """Convierte el resumen del proyecto en la respuesta para la interfaz."""
    return {
        "ok": info.has_python,
        "error": None if info.has_python else MSG_SIN_PY,
        **info.to_dict(),
    }


class Api:
    """Métodos que la interfaz puede llamar vía ``window.pywebview.api``."""

    def __init__(
        self,
        recent_path: Path | None = None,
        folder_picker: FolderPicker | None = None,
    ) -> None:
        self._recent_path = recent_path or recent.DEFAULT_PATH
        self._folder_picker = folder_picker or _native_folder_picker

    def pick_folder(self) -> dict[str, object]:
        """Abre el diálogo de carpetas. Devuelve ``{"ruta": ...}`` o ``{"cancelado": True}``."""
        ruta = self._folder_picker()
        if not ruta:
            return {"cancelado": True}
        return {"cancelado": False, "ruta": ruta}

    def inspect_folder(self, path: str) -> dict[str, object]:
        """Inspecciona la carpeta sin guardar nada. ``ok`` es falso si no hay .py o hay error."""
        try:
            return _project_dict(inspect_folder(path))
        except FolderError as exc:
            return {"ok": False, "error": str(exc), "ruta": path}

    def open_project(self, path: str) -> dict[str, object]:
        """Revalida la carpeta y, si tiene .py, la guarda en recientes.

        Una carpeta sin .py nunca se escribe en ``recientes.json``.
        """
        result = self.inspect_folder(path)
        if not result["ok"]:
            return result
        info = ProjectInfo(
            nombre=result["nombre"],
            ruta=result["ruta"],
            py_count=result["py_count"],
            has_requirements=result["has_requirements"],
        )
        try:
            recent.add_recent(info, self._recent_path)
        except OSError as exc:
            logger.warning("No se pudo guardar %s: %s", self._recent_path, exc)
            result["aviso"] = "No se pudo guardar el proyecto en la lista de recientes."
        return result

    def list_recent(self) -> list[dict]:
        """Devuelve los proyectos recientes, del más reciente al más antiguo."""
        return recent.load_recent(self._recent_path)

    def remove_recent(self, path: str) -> list[dict]:
        """Quita un proyecto de recientes y devuelve la lista actualizada."""
        try:
            return recent.remove_recent(path, self._recent_path)
        except OSError as exc:
            logger.warning("No se pudo actualizar %s: %s", self._recent_path, exc)
            return recent.load_recent(self._recent_path)
