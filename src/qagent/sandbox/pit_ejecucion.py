"""Ejecución PIT en el sandbox Java sobre copias, con límites y sin red (#180)."""

from __future__ import annotations

import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import docker

from qagent.config.carga import cargar_configuracion
from qagent.sandbox.ejecucion import copiar_proyecto, ejecutar_en_sandbox
from qagent.sandbox.modelos import IMAGEN_JAVA, ErrorSandbox, LimitesSandbox
from qagent.sandbox.mutacion import (
    CONFIG_PROPIA,
    ERROR,
    TIEMPO_AGOTADO,
    MutacionFuncion,
    ResultadoMutacion,
)
from qagent.sandbox.pit import LIMITE_XML_PIT, interpretar_pit
from qagent.sandbox.pit_comando import comando_pit
from qagent.sandbox.pit_preparacion import ConfiguracionPitPropia, preparar_pit


def ejecutar_pit(
    imagen: str | None,
    ruta_proyecto: str | Path,
    ruta_tests: str | Path,
    modulo: str,
    funciones: list[str],
    limites: LimitesSandbox | None = None,
    cliente: docker.DockerClient | None = None,
    inicios: dict[str, int] | None = None,
    manejadores: list[str] | None = None,
    *,
    al_informe: Callable[[str], None] | None = None,
) -> ResultadoMutacion:
    """Muta métodos seleccionados exclusivamente dentro del sandbox Docker.

    Args:
        imagen: imagen Java preparada con dependencias; None usa la base Java.
        ruta_proyecto: proyecto original que se copia y nunca se modifica.
        ruta_tests: pruebas Java aprobadas utilizadas contra los mutantes.
        modulo: ruta src/main/java/paquete/Clase.java.
        funciones: objetivos Clase.metodo críticos aprobados, validados al preparar.
        limites: límites entregados por el orquestador; sin ellos usa sandbox.java.
            El tiempo nunca supera el presupuesto de mutación por método seleccionado.
        cliente: cliente Docker opcional, sustituible en pruebas.
        inicios: compatibilidad con la interfaz; PIT ya informa líneas absolutas.
        manejadores: no admitidos; la mutación de endpoints Spring requiere otra tarea.
        al_informe: recibe XML validado para guardar evidencias; opcional.

    Returns:
        ResultadoMutacion. Configuración propia, preparación inválida, timeout,
        OOM, salida no cero o XML ausente producen estados sin score. Nunca
        ejecuta Java en el anfitrión. El sandbox común aplica CPU, memoria, red
        deshabilitada, copia del proyecto y limpieza de contenedores.
    """
    funciones = list(dict.fromkeys(funciones))
    if not funciones:
        return ResultadoMutacion(modulo, {})
    if manejadores:
        return _fallo(
            modulo, funciones, ERROR, "PIT no admite aún manejadores de endpoints."
        )
    try:
        carga = cargar_configuracion(simulado=True)
        if carga.config is None:
            raise ValueError("No se pudo cargar la configuración del sandbox Java.")
        por_metodo = carga.config.mutacion.tiempo_maximo_por_funcion_s
        limites = limites or carga.config.limites_sandbox("java")
        limites = replace(
            limites, timeout_s=min(limites.timeout_s, por_metodo * len(funciones))
        )
        comando = comando_pit(modulo, funciones)
        leido: dict[str, str] = {}

        def leer(_copia: Path, salida: Path) -> None:
            """Recoge solo el XML acotado de esta corrida antes de limpiar el sandbox."""
            archivo = salida / "pit" / "mutations.xml"
            if (
                archivo.is_file()
                and not archivo.is_symlink()
                and archivo.resolve().is_relative_to(salida.resolve())
                and archivo.stat().st_size <= LIMITE_XML_PIT
            ):
                leido["xml"] = archivo.read_text(encoding="utf-8")

        with tempfile.TemporaryDirectory(prefix="qagent-pit-") as carpeta:
            copia = copiar_proyecto(ruta_proyecto, Path(carpeta) / "proyecto")
            objetivos = preparar_pit(copia, Path(ruta_tests), modulo, funciones)
            ejecucion = ejecutar_en_sandbox(
                imagen or IMAGEN_JAVA,
                comando.comando,
                copia,
                ruta_tests,
                limites,
                entorno=comando.entorno,
                al_terminar=leer,
                cliente=cliente,
            )
        if ejecucion.timed_out:
            resultado = _fallo(
                modulo,
                funciones,
                TIEMPO_AGOTADO,
                f"PIT agotó el tiempo de mutación ({limites.timeout_s} s).",
            )
        elif ejecucion.oom_killed:
            resultado = _fallo(
                modulo, funciones, ERROR, "PIT terminó por falta de memoria."
            )
        elif ejecucion.exit_code != 0:
            resultado = _fallo(
                modulo,
                funciones,
                ERROR,
                f"PIT no finalizó correctamente (código {ejecucion.exit_code}).",
            )
        elif "xml" not in leido:
            resultado = _fallo(
                modulo,
                funciones,
                ERROR,
                "PIT no produjo un XML válido dentro del límite permitido.",
            )
        else:
            resultado = interpretar_pit(leido["xml"], modulo, objetivos)
            if al_informe is not None and all(
                f.estado != ERROR for f in resultado.funciones.values()
            ):
                al_informe(leido["xml"])
        resultado.duracion_s = ejecucion.duracion_s
        resultado.salida = (ejecucion.stdout + ejecucion.stderr)[-4000:]
        return resultado
    except ConfiguracionPitPropia as error:
        return _fallo(modulo, funciones, CONFIG_PROPIA, str(error))
    except (OSError, ValueError, ET.ParseError, ErrorSandbox) as error:
        return _fallo(modulo, funciones, ERROR, f"No se pudo ejecutar PIT: {error}")


def _fallo(
    modulo: str, funciones: list[str], estado: str, mensaje: str
) -> ResultadoMutacion:
    """Devuelve un estado explícito sin puntuación para todos los métodos pedidos."""
    return ResultadoMutacion(
        modulo, {f: MutacionFuncion(f, estado, mensaje=mensaje) for f in funciones}
    )
