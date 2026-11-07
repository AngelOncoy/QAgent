"""Ejecución de Stryker en el sandbox Node sobre copias aisladas (#179).

Ejecuta Stryker dentro de `qagent-sandbox:node` sin red, limitado a las funciones
críticas aprobadas, respetando los límites de tiempo de `[mutacion]` y evitando
sobrescribir configuraciones propias del proyecto.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import docker

from qagent.config.carga import cargar_configuracion
from qagent.lenguajes.javascript_ejecucion import LIMITES_NODE
from qagent.sandbox.ejecucion import copiar_proyecto, ejecutar_en_sandbox
from qagent.sandbox.modelos import IMAGEN_NODE, ErrorSandbox, LimitesSandbox
from qagent.sandbox.mutacion import (
    CONFIG_PROPIA,
    ERROR,
    TIEMPO_AGOTADO,
    MutacionFuncion,
    ResultadoMutacion,
)
from qagent.sandbox.stryker import LIMITE_JSON_STRYKER, interpretar_stryker
from qagent.sandbox.stryker_comando import comando_stryker
from qagent.sandbox.stryker_preparacion import (
    ConfiguracionStrykerPropia,
    preparar_stryker,
)


def ejecutar_stryker(
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
    """Ejecuta Stryker en el sandbox Docker exclusivamente sobre las funciones críticas.

    Args:
        imagen: etiqueta de la imagen Node; None usa IMAGEN_NODE.
        ruta_proyecto: directorio raíz del proyecto (no se modifica).
        ruta_tests: directorio con las pruebas aprobadas a utilizar contra los mutantes.
        modulo: ruta relativa del archivo en el proyecto.
        funciones: nombres de las funciones críticas a mutar.
        limites: límites de recursos asignados; se respeta el tiempo máximo por función.
        cliente: cliente Docker opcional.
        inicios: compatibilidad con la interfaz del orquestador.
        manejadores: no admitidos en esta etapa (endpoints Express).
        al_informe: callback opcional que recibe el JSON del reporte validado.

    Returns:
        ResultadoMutacion por función crítica.
    """
    funciones = list(dict.fromkeys(funciones))
    if not funciones:
        return ResultadoMutacion(modulo, {})

    if manejadores:
        return _fallo(
            modulo, funciones, ERROR, "Stryker no admite aún manejadores de endpoints."
        )

    try:
        carga = cargar_configuracion(simulado=True)
        por_funcion = (
            carga.config.mutacion.tiempo_maximo_por_funcion_s
            if carga.config is not None
            else 120
        )
        limites = limites or (
            carga.config.limites_sandbox("javascript")
            if carga.config is not None
            else LIMITES_NODE
        )
        limites = replace(
            limites,
            timeout_s=min(limites.timeout_s, por_funcion * len(funciones)),
        )

        leido: dict[str, str] = {}

        def leer(_copia: Path, salida: Path) -> None:
            candidatos = [
                _copia / "reports" / "mutation" / "mutation.json",
                salida / "mutation-report.json",
                salida / "stryker" / "mutation-report.json",
                salida / "mutation.json",
            ]
            for archivo in candidatos:
                if (
                    archivo.is_file()
                    and not archivo.is_symlink()
                    and archivo.stat().st_size <= LIMITE_JSON_STRYKER
                ):
                    try:
                        leido["json"] = archivo.read_text(encoding="utf-8")
                        break
                    except OSError:
                        pass

        with tempfile.TemporaryDirectory(prefix="qagent-stryker-") as carpeta:
            copia = copiar_proyecto(ruta_proyecto, Path(carpeta) / "proyecto")
            rangos = preparar_stryker(copia, Path(ruta_tests), modulo, funciones)
            comando = comando_stryker(modulo, funciones, rangos=rangos)

            ejecucion = ejecutar_en_sandbox(
                imagen or IMAGEN_NODE,
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
                f"Stryker agotó el tiempo de mutación ({limites.timeout_s} s).",
            )
        elif ejecucion.oom_killed:
            resultado = _fallo(
                modulo, funciones, ERROR, "Stryker terminó por falta de memoria."
            )
        elif "json" not in leido and ejecucion.exit_code != 0:
            resultado = _fallo(
                modulo,
                funciones,
                ERROR,
                f"Stryker no finalizó correctamente (código {ejecucion.exit_code}).",
            )
        elif "json" not in leido:
            resultado = _fallo(
                modulo,
                funciones,
                ERROR,
                "Stryker no produjo un informe JSON válido.",
            )
        else:
            resultado = interpretar_stryker(leido["json"], modulo, funciones, rangos)
            if al_informe is not None and all(
                f.estado != ERROR for f in resultado.funciones.values()
            ):
                al_informe(leido["json"])

        resultado.duracion_s = ejecucion.duracion_s
        resultado.salida = (ejecucion.stdout + ejecucion.stderr)[-4000:]
        return resultado

    except ConfiguracionStrykerPropia as error:
        return _fallo(modulo, funciones, CONFIG_PROPIA, str(error))
    except (OSError, ValueError, ErrorSandbox) as error:
        return _fallo(modulo, funciones, ERROR, f"No se pudo ejecutar Stryker: {error}")


def _fallo(
    modulo: str, funciones: list[str], estado: str, mensaje: str
) -> ResultadoMutacion:
    """Devuelve un estado sin puntuación para las funciones solicitadas."""
    return ResultadoMutacion(
        modulo=modulo,
        funciones={f: MutacionFuncion(f, estado, mensaje=mensaje) for f in funciones},
    )
