"""Módulo principal de la aplicación de escritorio con pywebview."""

import logging
import sys
import threading
from pathlib import Path
from typing import Any

import webview

from qagent.almacenamiento import AlmacenProyecto, recientes
from qagent.app import bitacora
from qagent.app.monitor_eventos import a_evento_bitacora, a_fila_monitor
from qagent.proyectos import proyecto_local
from qagent.storage.registro import PERFILES_REGRESION

# Interfaz web (HTML/CSS/JS), separada del backend e instalada con el paquete: qagent/frontend/
FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"


class DesktopAPI:
    """Puente de comunicación entre la interfaz JS y el backend Python."""

    def __init__(self) -> None:
        self._window: webview.Window | None = None
        self._corrida: threading.Thread | None = None  # corrida real en curso

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
            bitacora.registro.info("Carpeta seleccionada: %s", folder_path)
            return folder_path
        return None

    def destino_clonado(self, url: str) -> dict:
        """Valida la URL y propone la carpeta destino del clonado (HU-02).

        Returns:
            dict: ``{"ok": bool, "destino": str, "formato": str}``.
        """
        from qagent.proyectos import clonador

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

        from qagent.proyectos import clonador

        def avanzar(porcentaje: int | None, linea: str) -> None:
            self.emit_event(
                "clonado_avance", {"porcentaje": porcentaje, "linea": linea}
            )

        def trabajo() -> None:
            resultado = clonador.clonar(
                url, rama, destino, superficial, al_avanzar=avanzar
            )
            if resultado.ok and any(Path(resultado.destino).iterdir()):
                import shutil

                inspeccion = proyecto_local.inspeccionar_carpeta(resultado.destino)
                if not inspeccion["ok"]:
                    shutil.rmtree(resultado.destino, ignore_errors=True)
                    self.emit_event(
                        "clonado_fin",
                        {
                            "ok": False,
                            "destino": resultado.destino,
                            "tipo_error": "incompatibilidad_lenguaje",
                            "error": (
                                "No es posible cargar/abrir el proyecto por incompatibilidad de lenguaje: "
                                "QAgent solo admite proyectos en Python 3.10+."
                            ),
                        },
                    )
                    return
            datos = asdict(resultado)
            if resultado.ok:
                nombre = Path(resultado.destino).name or clonador.nombre_repositorio(
                    url
                )
                try:
                    recientes.registrar(nombre, "git", resultado.destino, url=url)
                except OSError as exc:
                    bitacora.registro.warning(
                        "El repositorio se clonó, pero no se pudo registrar en recientes: %s",
                        exc,
                    )
                    datos["advertencia"] = (
                        "El repositorio se clonó correctamente, pero no se pudo guardar "
                        "en Proyectos recientes."
                    )
                _preparar_almacen(resultado.destino)
            self.emit_event("clonado_fin", datos)

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
        _preparar_almacen(proyecto["ruta"])
        almacen = AlmacenProyecto(proyecto["ruta"])
        tiene_pruebas = almacen.tiene_pruebas_aprobadas()
        tiene_corridas = len(almacen.listar_runs()) > 0
        return {
            **proyecto,
            "tiene_pruebas": tiene_pruebas,
            "tiene_corridas": tiene_corridas,
            "ya_cargo_prueba": tiene_corridas or tiene_pruebas,
        }

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
        tiene_pruebas = False
        tiene_corridas = False
        if proyecto["ok"]:
            _preparar_almacen(proyecto["ruta"])
            almacen = AlmacenProyecto(proyecto["ruta"])
            tiene_pruebas = almacen.tiene_pruebas_aprobadas()
            tiene_corridas = len(almacen.listar_runs()) > 0 or bool(
                reciente.get("ultima_corrida")
            )
        return {
            **proyecto,
            "origen": reciente["origen"],
            "url": reciente["url"],
            "ultima_corrida": reciente.get("ultima_corrida"),
            "tiene_pruebas": tiene_pruebas,
            "tiene_corridas": tiene_corridas,
            "ya_cargo_prueba": tiene_corridas or tiene_pruebas,
        }

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
        from qagent.proyectos import vista_previa

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
            `qagent.config.verificar_entorno`).
        """
        from qagent.config import carga as config_carga
        from qagent.config import verificar_entorno

        return verificar_entorno(
            config_carga.RUTA_CONFIG,
            config_carga.RUTA_ENV,
            ruta_local=config_carga.RUTA_CONFIG_LOCAL,
        )

    def listar_proveedores(self) -> list[dict]:
        """Proveedores y modelos del catálogo para el formulario «Agregar API» (HU-30)."""
        from qagent.config.roles import listar_proveedores

        return listar_proveedores()

    def obtener_version(self) -> str:
        """Versión instalada de QAgent (la de `qagent --version`), para la interfaz."""
        from qagent import __version__

        return __version__

    def obtener_roles(self) -> list[dict]:
        """Proveedor, modelo y clave enmascarada de cada agente (HU-30)."""
        from qagent.config import carga as config_carga
        from qagent.config.roles import leer_roles

        return leer_roles(
            config_carga.RUTA_CONFIG,
            config_carga.RUTA_ENV,
            config_carga.RUTA_CONFIG_LOCAL,
        )

    def guardar_api_rol(
        self, agente: str, proveedor: str, modelo: str, clave: str | None = None
    ) -> dict:
        """Prueba la conexión y, si responde, guarda la API del agente (HU-30).

        La clave va solo a `.env`, en la variable propia del agente; el
        `config.local.toml` del usuario (`~/.qagent/`) recibe proveedor y modelo. El proveedor puede repetirse entre agentes, la clave
        no. Si la prueba falla no se guarda nada. La respuesta nunca incluye la clave.

        Returns:
            dict: ``{"ok", "mensaje", "detalle"?, "roles"}``.
        """
        from qagent.config import carga as config_carga
        from qagent.config.roles import configurar_rol

        resultado = configurar_rol(
            agente,
            proveedor,
            modelo,
            clave,
            ruta_config=config_carga.RUTA_CONFIG,
            ruta_env=config_carga.RUTA_ENV,
            ruta_local=config_carga.RUTA_CONFIG_LOCAL,
        )
        if resultado["ok"]:
            if clave:
                _ocultar_claves_en_bitacora()
            bitacora.registro.info(
                "API del %s guardada: %s / %s", agente, proveedor, modelo
            )
            if resultado.get("aviso"):
                bitacora.registro.warning("  %s", resultado["aviso"])
        else:
            bitacora.registro.warning(
                "API del %s no guardada (%s / %s): %s",
                agente,
                proveedor,
                modelo,
                resultado["mensaje"],
            )
        return {**resultado, "roles": self.obtener_roles()}

    def eliminar_api_rol(self, agente: str) -> dict:
        """Deja al agente «Sin configurar» en esta computadora y quita su clave (HU-30).

        Returns:
            dict: ``{"ok", "mensaje", "roles"}``.
        """
        from qagent.config import carga as config_carga
        from qagent.config.roles import eliminar_rol

        resultado = eliminar_rol(
            agente,
            ruta_config=config_carga.RUTA_CONFIG,
            ruta_env=config_carga.RUTA_ENV,
            ruta_local=config_carga.RUTA_CONFIG_LOCAL,
        )
        if resultado["ok"]:
            bitacora.registro.info("API del %s eliminada: sin configurar.", agente)
        return {**resultado, "roles": self.obtener_roles()}

    def obtener_limites(self) -> dict:
        """Límites de verificación vigentes para la pantalla Configuración.

        Returns:
            dict: ver `qagent.config.limites.leer_limites`.
        """
        from qagent.config.limites import leer_limites

        return leer_limites()

    def guardar_limites(self, max_intentos: int) -> dict:
        """Guarda los intentos por función en el `config.local.toml` del usuario.

        El tiempo máximo por prueba no se guarda: `[sandbox]` lo define solo el equipo.

        Returns:
            dict: ``{"ok", "mensaje", "limites"}``.
        """
        from qagent.config.limites import guardar_max_intentos, leer_limites

        resultado = guardar_max_intentos(max_intentos)
        if resultado["ok"]:
            bitacora.registro.info("Intentos por función: %s", max_intentos)
        return {**resultado, "limites": leer_limites()}

    def obtener_tema(self) -> dict:
        """Tema visual vigente (oscuro o claro) para la interfaz de escritorio."""
        from qagent.config.apariencia import leer_tema

        return {"ok": True, "tema": leer_tema()}

    def guardar_tema(self, tema: str) -> dict:
        """Guarda la preferencia de tema (oscuro o claro) en `config.local.toml`."""
        from qagent.config.apariencia import guardar_tema

        resultado = guardar_tema(tema)
        if resultado["ok"]:
            bitacora.registro.info("Tema de la interfaz: %s", tema)
        return resultado

    def obtener_ejecucion(self, ruta: str, run_id: str | None = None) -> dict:
        """Datos de la vista Ejecución de una corrida (HU-18).

        Todo sale de `.qagent/runs/<run_id>/results.json` (por defecto, la corrida más
        reciente con resultados): indicadores comparados con las metas, filtros por
        estado y pruebas agrupadas por módulo.

        Returns:
            dict: ``{"ok": True, ...}`` con lo que arma `vista_ejecucion()`, o
            ``{"ok": False, "motivo": str}`` si no hay resultados que mostrar.
        """
        from qagent.storage.vista_ejecucion import (
            ResultadosNoDisponibles,
            leer_results,
            vista_ejecucion,
        )

        try:
            return {"ok": True, **vista_ejecucion(leer_results(ruta, run_id))}
        except ResultadosNoDisponibles as error:
            return {"ok": False, "motivo": str(error)}

    def obtener_reporte(self, ruta: str, run_id: str | None = None) -> dict:
        """Datos del Reporte de auditoría de una corrida (HU-21).

        Las cifras y los controles salen de `results.json`; el contrato, el test y la
        traza de cada función, de `detalle.json` (misma carpeta de la corrida).

        Returns:
            dict: ``{"ok": True, ...}`` con lo que arma `vista_reporte()`, o
            ``{"ok": False, "motivo": str}`` si no hay resultados que mostrar.
        """
        from qagent.storage.vista_ejecucion import (
            ResultadosNoDisponibles,
            leer_results,
        )
        from qagent.storage.vista_reporte import leer_detalle, vista_reporte

        try:
            results = leer_results(ruta, run_id)
        except ResultadosNoDisponibles as error:
            return {"ok": False, "motivo": str(error)}
        detalle = leer_detalle(ruta, results["run_id"])
        return {"ok": True, **vista_reporte(results, detalle)}

    def carpeta_corrida(self, ruta: str, run_id: str | None = None) -> str:
        """Devuelve la carpeta por defecto `<proyecto>/.qagent/runs/<run_id>/` para exportar."""
        from qagent.storage.corrida_demo import CORRIDA_DEMO_ID
        from qagent.storage.exportar_informe import carpeta_por_defecto

        raiz = _resolver_ruta_proyecto(ruta, run_id)
        carpeta = carpeta_por_defecto(raiz, run_id or CORRIDA_DEMO_ID)
        return str(carpeta) + "\\"

    def abrir_carpeta_corrida(self, ruta: str, run_id: str | None = None) -> dict:
        """Abre la carpeta `.qagent/runs/<run_id>/` en el explorador de archivos."""
        from qagent.storage.corrida_demo import CORRIDA_DEMO_ID, asegurar_corrida_demo
        from qagent.storage.exportar_informe import carpeta_por_defecto

        raiz = _resolver_ruta_proyecto(ruta, run_id)
        id_efectivo = run_id or CORRIDA_DEMO_ID
        try:
            if id_efectivo == CORRIDA_DEMO_ID:
                carpeta = asegurar_corrida_demo(raiz, id_efectivo)
            else:
                carpeta = carpeta_por_defecto(raiz, id_efectivo)
                carpeta.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            return {"ok": False, "motivo": str(error)}

        if self._window is not None:
            _mostrar_en_explorador(carpeta, seleccionar_archivo=False)
        return {"ok": True, "carpeta": str(carpeta)}

    def exportar_informe(
        self,
        ruta: str,
        run_id: str | None = None,
        formato: str = "pdf",
        opciones: dict | None = None,
        carpeta_destino: str | None = None,
    ) -> dict:
        """Exporta el informe de la corrida como evidencia en PDF, Markdown o JSON (HU-22).

        Por defecto se guarda en `<proyecto>/.qagent/runs/<run_id>/` como
        `informe_<run_id>.pdf` o `.md`, o `results_<run_id>.json`; si se indica
        `carpeta_destino`, se escribe en esa carpeta.

        Returns:
            dict: ``{"ok": True, "run_id", "formato", "nombre", "ruta", "carpeta",
            "opciones"}``, o ``{"ok": False, "motivo": str}`` si no se pudo exportar.
        """
        from qagent.storage.exportar_informe import FormatoInvalido, exportar_informe
        from qagent.storage.vista_ejecucion import ResultadosNoDisponibles

        raiz = _resolver_ruta_proyecto(ruta, run_id)
        try:
            resultado = exportar_informe(
                raiz,
                run_id=run_id,
                formato=formato,
                opciones=opciones,
                carpeta_destino=carpeta_destino,
            )
        except (ResultadosNoDisponibles, FormatoInvalido, OSError) as error:
            return {"ok": False, "motivo": str(error)}

        if self._window is not None and resultado.get("ok"):
            _mostrar_en_explorador(Path(resultado["ruta"]), seleccionar_archivo=True)
        return resultado

    def obtener_historial(self, ruta: str) -> dict:
        """Corridas y specs persistidas del proyecto para la pantalla Historial."""
        from qagent.almacenamiento.historial import construir_historial

        return {"ok": True, **construir_historial(ruta)}

    def tiene_pruebas_aprobadas(self, ruta: str) -> bool:
        """Habilita Regresion solo si hay pruebas aprobadas persistidas."""
        return AlmacenProyecto(ruta).tiene_pruebas_aprobadas()

    def pruebas_repetibles(self, ruta: str) -> list[dict[str, str]]:
        """Funciones y endpoints con prueba guardada que hoy se puede repetir (#70)."""
        from qagent.orchestrator.regresion import objetivos_repetibles

        try:
            return objetivos_repetibles(ruta)
        except OSError as error:
            bitacora.registro.warning("No se leyeron las pruebas guardadas: %s", error)
            return []

    def descargar_specs_zip(self, ruta: str, modulo: str | None = None) -> dict:
        """Crea un ZIP y abre el diálogo nativo para elegir dónde guardarlo."""
        from qagent.almacenamiento import ErrorAlmacen

        try:
            nombre, contenido = AlmacenProyecto(ruta).crear_zip_specs(modulo)
        except ErrorAlmacen as error:
            return {"ok": False, "motivo": str(error)}
        return self._guardar_zip(nombre, contenido)

    def descargar_pruebas_zip(self, ruta: str) -> dict:
        """Crea un ZIP con las pruebas guardadas y abre el diálogo para guardarlo."""
        from qagent.almacenamiento import ErrorAlmacen

        try:
            nombre, contenido = AlmacenProyecto(ruta).crear_zip_pruebas()
        except ErrorAlmacen as error:
            return {"ok": False, "motivo": str(error)}
        return self._guardar_zip(nombre, contenido)

    def _guardar_zip(self, nombre: str, contenido: bytes) -> dict:
        """Pide dónde guardar un ZIP con el diálogo nativo y lo escribe."""
        if self._window is None:
            return {"ok": False, "motivo": "La ventana de QAgent no está disponible."}

        seleccion = self._window.create_file_dialog(
            webview.SAVE_DIALOG,
            save_filename=nombre,
            file_types=("Archivos ZIP (*.zip)",),
        )
        if not seleccion:
            return {"ok": False, "cancelado": True}

        destino = Path(seleccion[0])
        if destino.suffix.lower() != ".zip":
            destino = destino.with_suffix(".zip")
        try:
            destino.write_bytes(contenido)
        except OSError as error:
            return {"ok": False, "motivo": f"No se pudo guardar el ZIP: {error}"}
        return {
            "ok": True,
            "nombre": destino.name,
            "ruta": str(destino),
        }

    def start_run(
        self,
        folder_path: str,
        profile: str = "deep",
        seleccion: list[dict[str, Any]] | None = None,
    ) -> dict:
        """Inicia la corrida del sistema sobre el proyecto seleccionado.

        Primero verifica que Docker responde (HU-13) y luego que el entorno completo
        esté listo: config.toml, claves de .env, Docker y Git (EN-06). Con la IA
        simulada (QAGENT_FAKE_LLM=1, en el sistema o en el .env) Docker es opcional.

        Si todo está listo, la corrida real (análisis → Planner → Generator → Reviewer
        en Docker → log.json/results.json) corre en un hilo y envía a la interfaz los
        eventos `corrida_evento` (una fila del Monitor) y, al terminar, `corrida_fin`
        (resumen). Con la IA simulada y sin Docker listo no hay dónde ejecutar las
        pruebas: la corrida queda en modo demostración y la pantalla usa sus datos de
        ejemplo.

        Returns:
            dict: ``{"status": "started", ..., "run_id", "modo"}`` con ``modo`` igual
            a ``"real"`` o ``"demostracion"`` (``run_id`` es None si el proyecto no
            tiene ``.qagent/``); si Docker no está disponible,
            ``{"status": "docker_no_disponible", "mensaje": str}``; si falta otra cosa
            del entorno, ``{"status": "blocked", "motivo": str, "problemas": list}``;
            si ya hay una corrida en curso, ``{"status": "en_curso", "mensaje": str}``.
            Una selección que no coincida con el AST devuelve
            ``{"status": "seleccion_invalida", "mensaje": str}``.
        """
        from qagent.analysis import analizar_proyecto
        from qagent.config import modo_simulado
        from qagent.proyectos.seleccion import filtrar_modulos
        from qagent.sandbox import DockerNoDisponible, verificar_docker

        if seleccion is not None:
            try:
                filtrar_modulos(analizar_proyecto(folder_path)["modulos"], seleccion)
            except (OSError, ValueError) as exc:
                return {"status": "seleccion_invalida", "mensaje": str(exc)}

        simulado = modo_simulado()
        es_regresion = profile in PERFILES_REGRESION  # reg y reg_deep (#70): sin IA
        if es_regresion or not simulado:
            try:
                verificar_docker()
            except DockerNoDisponible as exc:
                bitacora.registro.warning("Corrida no iniciada: %s", exc)
                return {"status": "docker_no_disponible", "mensaje": str(exc)}

        if es_regresion:
            from qagent.config import carga as config_carga
            from qagent.config import verificar_entorno

            entorno = verificar_entorno(
                config_carga.RUTA_CONFIG,
                config_carga.RUTA_ENV,
                simulado=True,
                ruta_local=config_carga.RUTA_CONFIG_LOCAL,
            )
        else:
            entorno = self.verificar_entorno()
        if not entorno["listo"]:
            bitacora.registro.warning("Corrida no iniciada: %s", entorno["mensaje"])
            return {
                "status": "blocked",
                "motivo": entorno["mensaje"],
                "problemas": entorno["problemas"],
            }

        if self._corrida is not None and self._corrida.is_alive():
            return {
                "status": "en_curso",
                "mensaje": "Ya hay una corrida en curso: espera a que termine.",
            }

        modo = (
            "real"
            if es_regresion or not simulado or self._sandbox_listo()
            else "demostracion"
        )
        bitacora.registro.info(
            "Corrida iniciada en '%s' con perfil '%s' (%s)",
            folder_path,
            profile,
            "IA simulada" if simulado else "IA real",
        )
        if modo == "demostracion":
            bitacora.registro.info(
                "Docker no está listo: la pantalla muestra la demostración y no se "
                "ejecuta el pipeline."
            )
        run_id = _registrar_run(folder_path, usa_docker=modo == "real")
        # Emite un evento hacia la interfaz JS
        self.emit_event("log", {"message": f"Corrida iniciada en perfil '{profile}'"})
        if modo == "real":
            self._lanzar_corrida(folder_path, profile, run_id, simulado, seleccion)
        return {
            "status": "started",
            "folder": folder_path,
            "profile": profile,
            "run_id": run_id,
            "modo": modo,
        }

    def _sandbox_listo(self) -> bool:
        """True si Docker responde y la imagen base existe (se pueden ejecutar pruebas)."""
        try:
            from qagent.sandbox.estado import estado_docker
        except ImportError:
            return False
        return estado_docker()["estado"] == "ok"

    def _lanzar_corrida(
        self,
        ruta: str,
        perfil: str,
        run_id: str | None,
        simulado: bool,
        seleccion: list[dict[str, Any]] | None,
    ) -> None:
        """Ejecuta la corrida en un hilo para no congelar la ventana."""
        self._corrida = threading.Thread(
            target=self._correr,
            args=(ruta, perfil, run_id, simulado, seleccion),
            name="qagent-corrida",
            daemon=True,
        )
        self._corrida.start()

    def _correr(
        self,
        ruta: str,
        perfil: str,
        run_id: str | None,
        simulado: bool,
        seleccion: list[dict[str, Any]] | None = None,
    ) -> None:
        """Cuerpo del hilo: lee la configuración, corre el pipeline y avisa el final."""
        from qagent.config import carga as config_carga
        from qagent.config import cargar_configuracion
        from qagent.orchestrator.corrida import ResumenCorrida, ejecutar_corrida

        carga = cargar_configuracion(
            simulado=simulado, ruta_local=config_carga.RUTA_CONFIG_LOCAL
        )
        if carga.config is None:
            resumen = ResumenCorrida(
                run_id=run_id,
                estado="fallo_controlado",
                motivo="config.toml no es válido: " + "; ".join(carga.avisos),
                total_funciones=0,
            )
        else:
            opciones_corrida: dict[str, Any] = {
                "simulado": simulado,
                "al_evento": self._reenviar_evento,
                "run_id": run_id,
            }
            if seleccion is not None:
                opciones_corrida["seleccion"] = seleccion
            resumen = ejecutar_corrida(
                ruta,
                perfil,
                carga.config,
                carga.claves,
                **opciones_corrida,
            )
        nivel = logging.INFO if resumen.estado == "fin" else logging.WARNING
        bitacora.registro.log(
            nivel,
            "Corrida %s terminada (%s): %d aceptadas, %d bugs, %d estancadas, "
            "%d tokens, US$ %.4f%s",
            resumen.run_id or "sin registro",
            resumen.estado,
            resumen.aceptadas,
            resumen.bugs_detectados,
            resumen.estancadas,
            resumen.tokens,
            resumen.costo_usd,
            f" · {resumen.motivo}" if resumen.motivo else "",
        )
        if ruta:
            try:
                recientes.registrar_corrida(ruta)
            except OSError as exc:
                bitacora.registro.warning(
                    "No se pudo registrar la última corrida en recientes: %s", exc
                )
        self.emit_event("corrida_fin", resumen.a_dict())

    def _reenviar_evento(self, evento: dict) -> None:
        """Un evento del orquestador -> fila del Monitor y línea de la consola."""
        fila = a_fila_monitor(evento)
        if fila is None:
            return
        bitacora.registrar_evento(a_evento_bitacora(fila))
        self.emit_event("corrida_evento", fila)

    def estado_sandbox(self) -> dict:
        """Devuelve el estado del sandbox Docker para el indicador de la barra lateral.

        Returns:
            dict: `{"estado": "ok" | "sin_imagen" | "no_iniciado" | "no_instalado",
            "mensaje": str, "simulado": bool}`. `simulado` indica que la IA es simulada
            (QAGENT_FAKE_LLM=1): ahí no se ejecuta nada en el sandbox y Docker es
            opcional, así que la interfaz no debe presentar su ausencia como un fallo.
        """
        from qagent.config import modo_simulado

        try:
            from qagent.sandbox.estado import estado_docker
        except ImportError:
            estado = {
                "estado": "no_instalado",
                "mensaje": "Falta el SDK de Docker para Python: pip install -r requirements.txt",
            }
        else:
            estado = estado_docker()
        return {**estado, "simulado": modo_simulado()}

    def registrar_evento(self, evento: dict) -> None:
        """Imprime en la consola de Python un paso de la corrida, con hora.

        La pantalla lo llama con cada evento del Monitor, de modo que la corrida se pueda
        seguir desde la terminal donde se abrió la aplicación. Nunca muestra claves.

        Args:
            evento: `{"tipo", "agente", "archivo", "funcion", "mensaje", "progreso"}`
                (todos opcionales; ver `qagent.app.bitacora.registrar_evento`).
        """
        bitacora.registrar_evento(evento)

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
                f"window.onQAgentEvent && window.onQAgentEvent({payload});"
            )


def _resolver_ruta_proyecto(ruta: str, run_id: str | None = None) -> Path:
    """Devuelve la carpeta real del proyecto; en modo demo, `~/.qagent/demo/` si la ruta no existe."""
    from qagent.storage.corrida_demo import CORRIDA_DEMO_ID

    candidata = Path(ruta) if ruta else Path()
    try:
        if ruta and candidata.is_dir():
            return candidata
    except OSError:
        pass
    if run_id == CORRIDA_DEMO_ID or not ruta:
        from qagent.usuario import carpeta_usuario

        # Nunca la carpeta del programa: instalado puede ser de solo lectura (TA-06).
        return carpeta_usuario() / "demo"
    return candidata


def _mostrar_en_explorador(objetivo: Path, seleccionar_archivo: bool = True) -> None:
    """Abre el explorador del sistema mostrando el archivo o carpeta exportada."""
    import os
    import subprocess
    import sys

    try:
        ruta_resuelta = objetivo.resolve()
        if sys.platform == "win32":
            if seleccionar_archivo and ruta_resuelta.is_file():
                subprocess.Popen(
                    ["explorer.exe", f"/select,{ruta_resuelta}"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            elif hasattr(os, "startfile"):
                os.startfile(
                    str(
                        ruta_resuelta
                        if ruta_resuelta.is_dir()
                        else ruta_resuelta.parent
                    )
                )
        elif sys.platform == "darwin":
            cmd = (
                ["open", "-R", str(ruta_resuelta)]
                if seleccionar_archivo
                else ["open", str(ruta_resuelta)]
            )
            subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except OSError as exc:
        bitacora.registro.warning("No se pudo abrir el explorador: %s", exc)


def _preparar_almacen(ruta: str) -> None:
    """Crea `.qagent/` en el proyecto abierto (EN-07) sin impedir que se abra.

    Si la carpeta es de solo lectura, el proyecto se abre igual y queda un aviso.
    """
    try:
        AlmacenProyecto(ruta).inicializar()
    except OSError as exc:
        bitacora.registro.warning("No se pudo crear .qagent/ en '%s': %s", ruta, exc)


def _registrar_run(ruta: str, usa_docker: bool) -> str | None:
    """Crea `.qagent/runs/<run_id>/run.json` de la corrida que empieza (EN-07).

    Solo en proyectos abiertos (con `.qagent/` ya creado al abrirlos). Un fallo al
    escribir no impide la corrida: queda un aviso y se devuelve None. `usa_docker` es
    False en modo demostración: ahí no se ejecuta nada en el sandbox.
    """
    from qagent.almacenamiento import ErrorAlmacen
    from qagent.sandbox.modelos import IMAGEN_BASE

    almacen = AlmacenProyecto(ruta)
    if not almacen.existe():
        return None
    try:
        run = almacen.crear_run(
            tipos_prueba=["funcion"], imagen_docker=IMAGEN_BASE if usa_docker else None
        )
    except (OSError, ErrorAlmacen) as exc:
        bitacora.registro.warning(
            "No se pudo registrar la corrida en '%s': %s", ruta, exc
        )
        return None
    bitacora.registro.info("Corrida registrada: %s", almacen.carpeta_run(run["run_id"]))
    return run["run_id"]


def _ocultar_claves_en_bitacora() -> None:
    """Vuelve a leer `.env` para que la bitácora oculte también una clave recién guardada."""
    from qagent.config import Claves, leer_env
    from qagent.config import carga as config_carga

    try:
        claves = Claves(leer_env(config_carga.RUTA_ENV))
    except (OSError, UnicodeDecodeError):
        return
    bitacora.configurar_registro(claves)


def _registrar_estado_configuracion() -> None:
    """Lee config.toml y .env al iniciar y deja en consola un resumen sin claves (EN-06)."""
    from qagent.config import (
        aplicar_simulacion_desde_env,
        cargar_configuracion,
        instalar_filtro_logs,
    )

    # QAGENT_FAKE_LLM=1 en el .env también activa la IA simulada para todo el programa.
    aplicar_simulacion_desde_env()
    from qagent.config import carga as config_carga

    carga = cargar_configuracion(ruta_local=config_carga.RUTA_CONFIG_LOCAL)
    instalar_filtro_logs(carga.claves)
    bitacora.configurar_registro(carga.claves)  # bitácora de la corrida en la consola
    if carga.simulado:
        bitacora.registro.info(
            "IA simulada activa (QAGENT_FAKE_LLM=1): 0 tokens, no se usan claves."
        )
    if carga.ok:
        bitacora.registro.info("Configuración cargada: config.toml y claves en orden.")
    else:
        bitacora.registro.warning(
            "Configuración incompleta: no se podrán iniciar corridas."
        )
        for aviso in carga.avisos:
            bitacora.registro.warning("  - %s", aviso)


def ejecutar(argv: list[str] | None = None) -> None:
    """Comando `qagent` (y `python -m qagent`): atiende `--version` y abre la app."""
    import argparse

    from qagent import __version__

    parser = argparse.ArgumentParser(
        prog="qagent", description="Abre la aplicación de escritorio de QAgent."
    )
    parser.add_argument("--version", action="version", version=f"QAgent {__version__}")
    parser.parse_args(argv)
    main()


def main() -> None:
    """Abre la aplicación de escritorio."""
    from qagent.config.carga import migrar_desde_repositorio

    # Orden importante: ~/.pyagent/ solo se renombra si ~/.qagent/ aún no existe, y
    # mover el .env la crearía. La configuración se lee después de las dos migraciones.
    if recientes.migrar_carpeta_anterior():
        bitacora.registro.info(
            "Se migró ~/.pyagent/ a ~/.qagent/ (proyectos recientes)."
        )
    for nombre in migrar_desde_repositorio():
        bitacora.registro.info(
            "Se movió %s de la carpeta del código a ~/.qagent/.", nombre
        )
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
    # Herramientas de desarrollo solo al programar, nunca en el ejecutable (TA-06).
    webview.start(debug=not getattr(sys, "frozen", False))


if __name__ == "__main__":
    main()
