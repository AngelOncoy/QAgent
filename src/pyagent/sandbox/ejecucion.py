"""Paso 2 del sandbox (sin red): ejecución aislada sobre una copia del proyecto."""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import docker
from docker.errors import APIError, ImageNotFound
from docker.types import Mount
from requests.exceptions import RequestException

from pyagent.sandbox.cliente import obtener_cliente
from pyagent.sandbox.modelos import (
    LIMITES_POR_DEFECTO,
    ErrorSandbox,
    ImagenNoEncontrada,
    LimitesSandbox,
    ResultadoSandbox,
)

EXCLUIDOS_DE_LA_COPIA = (
    ".git",
    ".venv",
    "venv",
    ".pyagent",
    "__pycache__",
    "node_modules",
    ".env",
    ".env.*",
)

DIR_PROYECTO = "/work/proyecto"
DIR_TESTS = "/work/tests"
DIR_SALIDA = "/out"
PIDS_MAXIMOS = 128
TMP_TAMANO = "64m"
CODIGO_SIGKILL = 137

AlTerminar = Callable[[Path, Path], None]


def copiar_proyecto(ruta_proyecto: str | Path, destino: str | Path) -> Path:
    """Copia el proyecto a `destino` sin carpetas pesadas ni secretos.

    Excluye `.git`, entornos virtuales, `.pyagent`, cachés, `node_modules` y archivos `.env`.
    Los enlaces simbólicos se copian como enlaces, sin seguirlos.

    Args:
        ruta_proyecto: carpeta raíz del proyecto original (no se modifica).
        destino: carpeta que no debe existir; se crea con la copia.

    Returns:
        Ruta absoluta de la copia.
    """
    origen = Path(ruta_proyecto).resolve()
    if not origen.is_dir():
        raise ErrorSandbox(f"La carpeta del proyecto no existe: {origen}")
    destino = Path(destino)
    shutil.copytree(
        origen, destino, symlinks=True, ignore=shutil.ignore_patterns(*EXCLUIDOS_DE_LA_COPIA)
    )
    return destino.resolve()


def ejecutar_en_sandbox(
    imagen: str,
    comando: list[str],
    ruta_proyecto: str | Path,
    ruta_tests: str | Path,
    limites: LimitesSandbox = LIMITES_POR_DEFECTO,
    entorno: dict[str, str] | None = None,
    al_terminar: AlTerminar | None = None,
    cliente: docker.DockerClient | None = None,
) -> ResultadoSandbox:
    """Ejecuta un comando en un contenedor efímero, sin red y con límites de recursos.

    El proyecto se copia a una carpeta temporal y se monta en `/work/proyecto` (con
    escritura, sobre la copia); los tests se montan en `/work/tests` en solo lectura y
    `/out` es una carpeta temporal con escritura. El contenedor se elimina y las carpetas
    temporales se borran siempre, incluso si hay error.

    Args:
        imagen: etiqueta de la imagen devuelta por `preparar_imagen`.
        comando: comando a ejecutar, como lista de argumentos.
        ruta_proyecto: carpeta raíz del proyecto original.
        ruta_tests: carpeta con los tests a montar.
        limites: CPU, memoria y timeout del contenedor.
        entorno: variables de entorno extra; nunca se heredan las del host.
        al_terminar: función opcional que recibe (copia del proyecto, carpeta /out)
            antes de la limpieza, para leer resultados adicionales.
        cliente: cliente Docker; si es None se crea uno con `obtener_cliente()`.

    Returns:
        Resultado con código de salida, stdout, stderr y coverage.json si se generó.

    Raises:
        ImagenNoEncontrada: si la imagen no existe.
        ErrorSandbox: si Docker no puede crear el contenedor.
    """
    cliente = cliente or obtener_cliente()
    tests = Path(ruta_tests).resolve()
    if not tests.is_dir():
        raise ErrorSandbox(f"La carpeta de tests no existe: {tests}")

    temporal = Path(tempfile.mkdtemp(prefix="pyagent-sandbox-")).resolve()
    contenedor = None
    try:
        copia = copiar_proyecto(ruta_proyecto, temporal / "proyecto")
        salida = temporal / "out"
        salida.mkdir()
        salida.chmod(0o777)  # el usuario del contenedor (uid 1000) debe poder escribir

        variables = {"PYTHONPATH": DIR_PROYECTO, "HOME": "/tmp", **(entorno or {})}
        inicio = time.monotonic()
        contenedor = _crear_contenedor(
            cliente, imagen, comando, copia, tests, salida, limites, variables
        )
        exit_code, timed_out = _esperar(contenedor, limites.timeout_s)
        duracion = time.monotonic() - inicio

        contenedor.reload()
        oom = bool(contenedor.attrs.get("State", {}).get("OOMKilled"))
        resultado = ResultadoSandbox(
            exit_code=exit_code,
            stdout=_leer_logs(contenedor, stdout=True),
            stderr=_leer_logs(contenedor, stdout=False),
            coverage=_leer_coverage(salida / "coverage.json"),
            timed_out=timed_out,
            oom_killed=oom or (exit_code == CODIGO_SIGKILL and not timed_out),
            duracion_s=round(duracion, 3),
        )
        if al_terminar is not None:
            al_terminar(copia, salida)
        return resultado
    finally:
        if contenedor is not None:
            _eliminar(contenedor)
        shutil.rmtree(temporal, ignore_errors=True)


def _crear_contenedor(
    cliente: docker.DockerClient,
    imagen: str,
    comando: list[str],
    copia: Path,
    tests: Path,
    salida: Path,
    limites: LimitesSandbox,
    variables: dict[str, str],
) -> Any:
    """Arranca el contenedor en modo detach con todas las restricciones del sandbox."""
    montajes = [
        Mount(DIR_PROYECTO, str(copia), type="bind"),
        Mount(DIR_TESTS, str(tests), type="bind", read_only=True),
        Mount(DIR_SALIDA, str(salida), type="bind"),
    ]
    try:
        return cliente.containers.run(
            imagen,
            comando,
            detach=True,
            working_dir=DIR_PROYECTO,
            environment=variables,
            mounts=montajes,
            network_mode="none",
            nano_cpus=int(limites.cpus * 1_000_000_000),
            mem_limit=limites.memoria,
            memswap_limit=limites.memoria,
            pids_limit=PIDS_MAXIMOS,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges"],
            read_only=True,
            tmpfs={"/tmp": f"rw,size={TMP_TAMANO}"},
            labels={"pyagent": "sandbox"},
        )
    except ImageNotFound as exc:
        raise ImagenNoEncontrada(
            f"No existe la imagen '{imagen}'. Prepárala con preparar_imagen()."
        ) from exc
    except APIError as exc:
        raise ErrorSandbox(f"Docker no pudo crear el contenedor: {exc.explanation}") from exc


def _esperar(contenedor: Any, timeout_s: int) -> tuple[int, bool]:
    """Espera a que el contenedor termine; si excede el timeout lo mata.

    Returns:
        Tupla (código de salida, se excedió el timeout).
    """
    try:
        estado = contenedor.wait(timeout=timeout_s)
        return int(estado.get("StatusCode", -1)), False
    except RequestException:
        try:
            contenedor.kill()
            estado = contenedor.wait(timeout=10)
            return int(estado.get("StatusCode", CODIGO_SIGKILL)), True
        except (APIError, RequestException):
            return CODIGO_SIGKILL, True


def _leer_logs(contenedor: Any, stdout: bool) -> str:
    """Lee stdout o stderr del contenedor como texto."""
    datos = contenedor.logs(stdout=stdout, stderr=not stdout)
    return datos.decode("utf-8", errors="replace")


def _leer_coverage(archivo: Path) -> dict[str, Any] | None:
    """Carga coverage.json si existe y es válido."""
    if not archivo.is_file():
        return None
    try:
        return json.loads(archivo.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _eliminar(contenedor: Any) -> None:
    """Elimina el contenedor aunque siga corriendo (equivalente a --rm)."""
    try:
        contenedor.remove(force=True)
    except APIError:
        pass
