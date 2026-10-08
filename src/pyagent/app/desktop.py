"""Módulo principal de la aplicación de escritorio con pywebview."""

from pathlib import Path

import webview

from pyagent.proyectos import proyecto_local, recientes

# Interfaz web (HTML/CSS/JS), separada del backend: <raíz del repo>/frontend/
FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend"


class DesktopAPI:
    """Puente de comunicación entre la interfaz JS y el backend Python."""

    def __init__(self) -> None:
        self._window: webview.Window | None = None

    def set_window(self, window: webview.Window) -> None:
        """Asigna la instancia de la ventana activa."""
        self._window = window

    def select_folder(self) -> str | None:
        """Abre el diálogo nativo del sistema operativo para seleccionar una carpeta.

        Returns:
            str | None: Ruta absoluta de la carpeta seleccionada, o None si se canceló.
        """
        if not self._window:
            return None

        # webview.FOLDER_DIALOG abre el selector de carpetas nativo (Windows/Linux/Mac)
        result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        if result and len(result) > 0:
            folder_path = result[0]
            print(f"[Python] Carpeta seleccionada: {folder_path}")
            return folder_path
        return None

    def destino_clonado(self, url: str) -> dict:
        """Valida la URL y propone la carpeta destino del clonado (HU-02).

        Returns:
            dict: ``{"ok": bool, "destino": str, "formato": str}``.
        """
        from pyagent.proyectos import clonador

        if not clonador.validar_url(url):
            return {"ok": False, "destino": "", "formato": clonador.FORMATO_URL}
        destino = str(clonador.destino_por_defecto(url))
        return {"ok": True, "destino": destino, "formato": clonador.FORMATO_URL}

    def clonar_repositorio(
        self, url: str, rama: str, destino: str, superficial: bool = True
    ) -> dict:
        """Inicia ``git clone`` en un hilo para no bloquear la interfaz (HU-02).

        El avance llega a la interfaz con eventos ``clonado_avance`` y el final con
        ``clonado_fin`` (el resultado de ``clonador.clonar``).

        Returns:
            dict: ``{"iniciado": True}``.
        """
        import threading
        from dataclasses import asdict

        from pyagent.proyectos import clonador

        def avanzar(porcentaje: int | None, linea: str) -> None:
            self.emit_event(
                "clonado_avance", {"porcentaje": porcentaje, "linea": linea}
            )

        def trabajo() -> None:
            resultado = clonador.clonar(
                url, rama, destino, superficial, al_avanzar=avanzar
            )
            self.emit_event("clonado_fin", asdict(resultado))

        threading.Thread(target=trabajo, name="clonado-git", daemon=True).start()
        return {"iniciado": True}

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

    def listar_recientes(self) -> list[dict]:
        """Hasta 10 proyectos recientes para la Bienvenida (HU-03)."""
        return recientes.listar()

    def abrir_reciente(self, ruta: str) -> dict:
        """Reabre un proyecto reciente y devuelve los datos para la Vista previa (HU-03).

        Returns:
            dict: Lo mismo que ``inspeccionar_carpeta`` más ``origen`` y ``url``; si la
            carpeta ya no existe, ``ok`` es False y ``motivo`` es ``"no_encontrada"``.
        """
        try:
            abierto = recientes.abrir(ruta)
        except OSError:
            return {
                "ok": False,
                "motivo": "error",
                "error": "No se pudo actualizar Proyectos recientes.",
            }
        if not abierto["ok"]:
            return abierto
        reciente = abierto["proyecto"]
        proyecto = proyecto_local.inspeccionar_carpeta(reciente["ruta"])
        return {**proyecto, "origen": reciente["origen"], "url": reciente["url"]}

    def quitar_reciente(self, ruta: str) -> bool:
        """Quita un proyecto de la lista de recientes sin borrar su carpeta (HU-03)."""
        try:
            return recientes.quitar(ruta)
        except OSError:
            return False

    def obtener_vista_previa(self, ruta: str) -> dict:
        """Obtiene la vista previa del proyecto analizado por AST (HU-04).

        Devuelve los módulos priorizados (primero los que tienen más funciones
        con ramas), los errores de sintaxis y el resumen de métricas e
        inconsistencias según el JSON de EN-02.
        """
        from pyagent.proyectos import vista_previa

        return vista_previa.generar_vista_previa(ruta)

    def analizar_proyecto(self, ruta: str) -> dict:
        """Alias de obtener_vista_previa para la interfaz JavaScript (HU-04)."""
        return self.obtener_vista_previa(ruta)

    def verificar_entorno(self) -> dict:
        """Verifica config.toml, claves de .env, Docker y Git (EN-06).

        Se vuelve a leer todo en cada llamada, así que el usuario puede corregir el
        `.env` y pulsar Reintentar sin reiniciar la aplicación. Nunca devuelve claves.

        Returns:
            dict: `listo`, `mensaje`, `problemas` y `comprobaciones` (ver
            `pyagent.config.verificar_entorno`).
        """
        from pyagent.config import verificar_entorno

        return verificar_entorno()

    def start_run(self, folder_path: str, profile: str = "deep") -> dict:
        """Inicia la corrida del sistema sobre el proyecto seleccionado.

        Primero verifica que Docker responde (HU-13) y luego que el entorno completo
        esté listo: config.toml, claves de .env, Docker y Git (EN-06). Con la IA
        simulada (PYAGENT_FAKE_LLM=1, en el sistema o en el .env) Docker es opcional:
        no se ejecuta nada en el sandbox, así que no se exige.

        Returns:
            dict: ``{"status": "started", ...}``; si Docker no está disponible,
            ``{"status": "docker_no_disponible", "mensaje": str}``; si falta otra cosa
            del entorno, ``{"status": "blocked", "motivo": str, "problemas": list}``.
        """
        from pyagent.config import modo_simulado
        from pyagent.sandbox import DockerNoDisponible, verificar_docker

        if not modo_simulado():
            try:
                verificar_docker()
            except DockerNoDisponible as exc:
                return {"status": "docker_no_disponible", "mensaje": str(exc)}

        entorno = self.verificar_entorno()
        if not entorno["listo"]:
            return {
                "status": "blocked",
                "motivo": entorno["mensaje"],
                "problemas": entorno["problemas"],
            }

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
        if self._window:
            # Invoca la función receptora definida en el window de JavaScript
            import json

            payload = json.dumps({"type": event_type, "data": data})
            self._window.evaluate_js(
                f"window.onPyAgentEvent && window.onPyAgentEvent({payload});"
            )


def _registrar_estado_configuracion() -> None:
    """Lee config.toml y .env al iniciar y deja en consola un resumen sin claves (EN-06)."""
    from pyagent.config import (
        aplicar_simulacion_desde_env,
        cargar_configuracion,
        instalar_filtro_logs,
    )

    # PYAGENT_FAKE_LLM=1 en el .env también activa la IA simulada para todo el programa.
    aplicar_simulacion_desde_env()
    carga = cargar_configuracion()
    instalar_filtro_logs(carga.claves)
    if carga.simulado:
        print(
            "[Python] IA simulada activa (PYAGENT_FAKE_LLM=1): 0 tokens, no se usan claves."
        )
    if carga.ok:
        print("[Python] Configuración cargada: config.toml y claves en orden.")
    else:
        print("[Python] Configuración incompleta: no se podrán iniciar corridas.")
        for aviso in carga.avisos:
            print(f"[Python]   - {aviso}")


def main() -> None:
    """Punto de entrada de la aplicación de escritorio."""
    _registrar_estado_configuracion()
    # Se carga como file:// y no como ruta: con una ruta, pywebview sirve la carpeta con un servidor
    # HTTP interno cuya cola admite 5 conexiones, y al abrir la ventana (decenas de CSS, JS y fuentes
    # a la vez) rechaza algunas peticiones al azar y la interfaz queda sin estilos o sin scripts.
    url = (FRONTEND_DIR / "index.html").as_uri()

    api = DesktopAPI()

    window = webview.create_window(
        title="QAgent — Autonomous Test Engine",
        url=url,
        js_api=api,
        width=1400,
        height=900,
        min_size=(960, 600),
    )

    api.set_window(window)
    webview.start(debug=True)


if __name__ == "__main__":
    main()
