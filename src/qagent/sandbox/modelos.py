"""Tipos de datos y errores del sandbox Docker (EN-03)."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Any

REPOSITORIO = "qagent-sandbox"
IMAGEN_BASE = f"{REPOSITORIO}:base"
#: Prefijo de etiquetas base de Python versionadas (ej. `qagent-sandbox:base-py3.12`, ADR-013).
PREFIJO_BASE_PYTHON = f"{REPOSITORIO}:base-py"
VERSION_PYTHON_DEFECTO = "3.11"


def etiqueta_base_python(
    version: str, version_por_defecto: str = VERSION_PYTHON_DEFECTO
) -> str:
    """Etiqueta de la imagen base de Python según la versión solicitada (ADR-013).

    La versión por defecto conserva `qagent-sandbox:base` para no romper lo que ya
    existe. Las demás versiones usan `qagent-sandbox:base-py<versión>`.
    """
    version_limpia = str(version).strip()
    if version_limpia == version_por_defecto:
        return IMAGEN_BASE
    return f"{PREFIJO_BASE_PYTHON}{version_limpia}"


def version_de_imagen_base(
    imagen: str, version_por_defecto: str = VERSION_PYTHON_DEFECTO
) -> str | None:
    """Extrae la versión de Python de una imagen base (ej. 'qagent-sandbox:base-py3.12' -> '3.12')."""
    if imagen == IMAGEN_BASE:
        return version_por_defecto
    if imagen.startswith(PREFIJO_BASE_PYTHON):
        return imagen[len(PREFIJO_BASE_PYTHON) :]
    return None


def es_imagen_base_python(imagen: str) -> bool:
    """Indica si una etiqueta corresponde a una imagen base de Python (por defecto o versionada)."""
    return imagen == IMAGEN_BASE or imagen.startswith(PREFIJO_BASE_PYTHON)


#: Imagen de JavaScript y TypeScript: Node LTS, Vitest, coverage-v8 y Stryker (#169).
IMAGEN_NODE = f"{REPOSITORIO}:node"
#: Imagen de Java: JDK, Maven, Gradle, JUnit 5, JaCoCo y PIT (#169).
IMAGEN_JAVA = f"{REPOSITORIO}:java"
#: Navegador aislado para humo E2E; solo se aprovisiona al pedir ese flujo (#186).
IMAGEN_NAVEGADOR = f"{REPOSITORIO}:navegador"
#: Etiqueta Docker de los contenedores del sandbox (para encontrarlos y limpiarlos).
ETIQUETA_CONTENEDOR = {"qagent": "sandbox"}
#: Label de toda construcción de imagen de QAgent (#267). Docker la copia a los contenedores
#: y capas intermedios del build: así se reconocen los que una construcción cortada deja a
#: medias, sin tocar lo que sea del usuario. Distinta de `ETIQUETA_CONTENEDOR` para que la
#: limpieza trate aparte (y con más cuidado) lo que aún puede estar construyéndose.
ETIQUETA_CONSTRUCCION = {"qagent": "construccion"}

MENSAJE_NO_INSTALADO = "Docker no está instalado. Instala Docker Desktop para ejecutar las pruebas en el sandbox."
MENSAJE_NO_INICIADO = "Docker Desktop no está iniciado. Ábrelo, espera a que termine de arrancar y vuelve a intentar."
# HU-13 (criterio 3): texto exacto que ve el usuario si intenta iniciar una corrida sin Docker.
MENSAJE_DOCKER_CERRADO = "Docker no está abierto: inícialo y vuelve a intentar"


def clasificar_docker_caido() -> tuple[str, str]:
    """Clasifica por qué Docker no responde, según si su ejecutable existe en el sistema.

    Returns:
        Tupla (estado, mensaje) con estado "no_instalado" o "no_iniciado".
    """
    if shutil.which("docker") is None:
        return "no_instalado", MENSAJE_NO_INSTALADO
    return "no_iniciado", MENSAJE_NO_INICIADO


@dataclass(frozen=True)
class LimitesSandbox:
    """Límites de recursos de un contenedor del sandbox.

    Atributos:
        cpus: número de CPU disponibles para el contenedor. Antes de crearlo se
            recorta a los CPU que tiene Docker (`NCPU`).
        memoria: memoria máxima en formato Docker (ej. "3g"); también es el tope de swap.
        timeout_s: segundos máximos de ejecución antes de matar el contenedor.

    Los valores por defecto se pueden cambiar en `[sandbox]` de config.toml; cada
    lenguaje puede fijar su memoria y su tiempo en `[sandbox.<lenguaje>]` (#169).
    """

    cpus: float = 4.0
    memoria: str = "3g"
    timeout_s: int = 120


LIMITES_POR_DEFECTO = LimitesSandbox()


@dataclass
class ResultadoSandbox:
    """Resultado de una ejecución dentro del sandbox.

    Atributos:
        exit_code: código de salida del proceso del contenedor.
        stdout: salida estándar.
        stderr: salida de error.
        coverage: contenido de coverage.json, o None si no se generó.
        timed_out: True si se excedió el timeout y se mató el contenedor.
        oom_killed: True si el contenedor terminó por falta de memoria.
        duracion_s: duración de la ejecución en segundos.
        junit_xml: contenido de junit.xml (un registro por caso), o None si no se generó.
        comando: el comando que de verdad se ejecutó, para el informe (EN-17).
        limites: los límites que de verdad se aplicaron (con los CPU ya recortados a
            los de Docker), o None si no se llegó a crear el contenedor.
    """

    exit_code: int
    stdout: str
    stderr: str
    coverage: dict[str, Any] | None = None
    timed_out: bool = False
    oom_killed: bool = False
    duracion_s: float = 0.0
    junit_xml: str | None = None
    comando: list[str] | None = None
    limites: LimitesSandbox | None = None


class ErrorSandbox(Exception):
    """Error base del sandbox; su mensaje se puede mostrar al usuario."""


class ErrorPreparacionSandbox(ErrorSandbox):
    """Un preparador de lenguaje no pudo disponer la copia o las pruebas del sandbox."""


class DockerNoDisponible(ErrorSandbox):
    """Docker no está instalado o Docker Desktop no está iniciado."""


class ImagenNoEncontrada(ErrorSandbox):
    """La imagen base del sandbox no existe."""


class EspacioInsuficiente(ErrorSandbox):
    """Queda poco espacio libre en el disco de Docker para construir o descargar una imagen (#267).

    Su mensaje está en lenguaje simple: cuánto falta y qué hacer.
    """


class ConstruccionCancelada(ErrorSandbox):
    """El usuario canceló la corrida mientras se construía una imagen (#148).

    La lanza quien escucha el avance; deja de leerse el log de `docker build` y se
    cierra la conexión con Docker.
    """


class ErrorConstruccionImagen(ErrorSandbox):
    """Falló la construcción de una imagen (por ejemplo, pip install).

    Atributos:
        log: salida completa de la construcción, para diagnóstico.
    """

    def __init__(self, mensaje: str, log: str = "") -> None:
        super().__init__(mensaje)
        self.log = log
