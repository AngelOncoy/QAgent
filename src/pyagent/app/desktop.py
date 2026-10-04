"""Módulo principal de la aplicación de escritorio con pywebview."""

import os
import sys

import webview

# Al ejecutar desktop.py directamente, src/ no está en el path: se agrega para importar pyagent.
_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from pyagent.app import proyecto_local, recientes


class DesktopAPI:
    """Puente de comunicación entre la interfaz JS y el backend Python."""

    def __init__(self) -> None:
        self.window: webview.Window | None = None

    def set_window(self, window: webview.Window) -> None:
        """Asigna la instancia de la ventana activa."""
        self.window = window

    def select_folder(self) -> str | None:
        """Abre el diálogo nativo del sistema operativo para seleccionar una carpeta.

        Returns:
            str | None: Ruta absoluta de la carpeta seleccionada, o None si se canceló.
        """
        if not self.window:
            return None

        # webview.FOLDER_DIALOG abre el selector de carpetas nativo (Windows/Linux/Mac)
        result = self.window.create_file_dialog(webview.FOLDER_DIALOG)
        if result and len(result) > 0:
            folder_path = result[0]
            print(f"[Python] Carpeta seleccionada: {folder_path}")
            return folder_path
        return None

    def inspeccionar_carpeta(self, ruta: str) -> dict:
        """Valida la carpeta elegida y cuenta sus archivos ``.py`` (HU-01).

        Returns:
            dict: ``ok``, ``nombre``, ``ruta``, ``cantidad_py`` y ``error``.
        """
        return proyecto_local.inspeccionar_carpeta(ruta)

    def abrir_proyecto(self, ruta: str) -> dict:
        """Revalida la carpeta y, si tiene ``.py``, la registra en recientes (HU-01).

        Una carpeta sin ``.py`` nunca se registra.

        Returns:
            dict: El resultado de ``inspeccionar_carpeta``; si no se pudo
            guardar en recientes, ``ok`` es False con el motivo en ``error``.
        """
        proyecto = proyecto_local.inspeccionar_carpeta(ruta)
        if not proyecto["ok"]:
            return proyecto
        try:
            recientes.registrar(proyecto["nombre"], "local", proyecto["ruta"])
        except OSError:
            return {
                **proyecto,
                "ok": False,
                "error": "No se pudo guardar el proyecto en Proyectos recientes "
                f"({recientes.ruta_por_defecto()}).",
            }
        return proyecto

    def start_run(self, folder_path: str, profile: str = "deep") -> dict:
        """Inicia la corrida del sistema sobre el proyecto seleccionado."""
        print(f"[Python] Iniciando corrida en '{folder_path}' con perfil '{profile}'")
        # Emite un evento hacia la interfaz JS
        self.emit_event("log", {"message": f"Corrida iniciada en perfil '{profile}'"})
        return {"status": "started", "folder": folder_path, "profile": profile}

    def estado_sandbox(self) -> dict:
        """Devuelve el estado del sandbox Docker para el indicador de la barra lateral.

        Returns:
            dict: `{"estado": "ok" | "sin_imagen" | "no_iniciado" | "no_instalado", "mensaje": str}`.
        """
        try:
            from pyagent.sandbox.estado import estado_docker
        except ImportError:
            return {
                "estado": "no_instalado",
                "mensaje": "Falta el SDK de Docker para Python: pip install -r requirements.txt",
            }
        return estado_docker()

    def emit_event(self, event_type: str, data: dict) -> None:
        """Envía un evento desde Python hacia la interfaz JavaScript.

        Args:
            event_type: Nombre del evento ('log', 'progress', etc.).
            data: Carga útil con la información del evento.
        """
        if self.window:
            # Invoca la función receptora definida en el window de JavaScript
            import json

            payload = json.dumps({"type": event_type, "data": data})
            self.window.evaluate_js(
                f"window.onPyAgentEvent && window.onPyAgentEvent({payload});"
            )


def main() -> None:
    """Punto de entrada de la aplicación de escritorio."""
    html_path = os.path.join(
        os.path.dirname(__file__),
        "ui",
        "index.html",  # Asegúrate de que coincida con el nombre de tu archivo
    )

    api = DesktopAPI()

    window = webview.create_window(
        title="PyAgent — Autonomous Test Engine",
        url=html_path,
        js_api=api,
        width=1400,
        height=900,
        min_size=(960, 600),
    )

    api.set_window(window)
    webview.start(debug=True)


if __name__ == "__main__":
    main()
