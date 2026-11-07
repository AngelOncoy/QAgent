"""Verificación del entorno al abrir un proyecto (EN-06).

Reúne en un solo resultado lo que necesita la interfaz: configuración y claves
(`carga`), Docker con su imagen base (`sandbox.estado`) y Git. Si algo falla, indica el
motivo y no se permite iniciar corridas.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from qagent.config.carga import (
    ResultadoCarga,
    cargar_configuracion,
)

MENSAJE_LISTO = "Entorno listo"
MENSAJE_IA_SIMULADA = (
    "IA simulada activa (QAGENT_FAKE_LLM=1): respuestas grabadas, 0 tokens y US$ 0. "
    "No se usan las claves de .env."
)
MENSAJE_DOCKER_OPCIONAL = (
    "Docker no hace falta con la IA simulada: no se ejecuta nada en el sandbox."
)
TIMEOUT_GIT_S = 5
MENSAJE_GIT_AUSENTE = (
    "Git no está instalado o no está en el PATH. Instálalo desde https://git-scm.com "
    "y pulsa Comprobar de nuevo; si lo instalaste en otra carpeta, reinicia QAgent."
)
#: Carpetas donde el instalador de Git para Windows deja `git.exe` (relativas a cada base).
_BASES_GIT_WINDOWS = (
    "ProgramFiles",
    "ProgramW6432",
    "ProgramFiles(x86)",
    "LOCALAPPDATA",
)
_SUBCARPETAS_GIT = {"LOCALAPPDATA": ("Programs", "Git", "cmd")}
_SUBCARPETA_GIT = ("Git", "cmd")
MENSAJE_GIT_ERROR = (
    "Git está instalado pero no responde. Ejecuta 'git --version' en una terminal."
)


def estado_git() -> dict[str, str]:
    """Comprueba que `git` exista y responda, sin lanzar excepciones.

    Returns:
        `{"estado": "ok" | "no_instalado" | "error", "mensaje": str}`.
    """
    if buscar_git() is None:
        return {"estado": "no_instalado", "mensaje": MENSAJE_GIT_AUSENTE}
    try:
        resultado = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_GIT_S,
            stdin=subprocess.DEVNULL,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return {"estado": "error", "mensaje": MENSAJE_GIT_ERROR}
    if resultado.returncode != 0:
        return {"estado": "error", "mensaje": MENSAJE_GIT_ERROR}
    return {"estado": "ok", "mensaje": resultado.stdout.strip() or "Git disponible."}


def buscar_git(
    entorno: dict[str, str] | None = None,
    path_registro: Callable[[], list[str]] | None = None,
    en_windows: bool | None = None,
) -> str | None:
    """Ruta de `git`, aunque se haya instalado con QAgent abierto (#251).

    Windows no actualiza el `PATH` de un proceso que ya está abierto: si se instala Git
    después de abrir QAgent, `shutil.which` no lo ve. Si no está en el `PATH` heredado,
    se busca en las carpetas del instalador de Git y en el `PATH` actual del registro.
    Si se encuentra ahí, su carpeta se agrega al `PATH` del proceso, para que el clonado
    y las demás llamadas a `git` también lo encuentren.

    Args:
        entorno: variables de entorno (por defecto `os.environ`; se modifica su `PATH`).
        path_registro: carpetas del `PATH` actual del registro (por defecto se leen).
        en_windows: si se busca fuera del `PATH` (por defecto, solo en Windows).
    """
    encontrado = shutil.which("git")
    entorno = os.environ if entorno is None else entorno
    if encontrado is not None:
        return encontrado
    if not (os.name == "nt" if en_windows is None else en_windows):
        return None
    leer_registro = path_registro or _path_del_registro
    for carpeta in [*_carpetas_git(entorno), *leer_registro()]:
        ejecutable = Path(carpeta) / "git.exe"
        if ejecutable.is_file():
            entorno["PATH"] = os.pathsep.join(
                p for p in (str(Path(carpeta)), entorno.get("PATH", "")) if p
            )
            return str(ejecutable)
    return None


def _carpetas_git(entorno: dict[str, str]) -> list[Path]:
    """Carpetas `Git/cmd` del instalador oficial, según las variables del sistema."""
    carpetas = []
    for base in _BASES_GIT_WINDOWS:
        raiz = entorno.get(base)
        if raiz:
            carpetas.append(Path(raiz, *_SUBCARPETAS_GIT.get(base, _SUBCARPETA_GIT)))
    return carpetas


def _path_del_registro() -> list[str]:
    """Carpetas del `PATH` actual de Windows (usuario y sistema), leídas del registro."""
    try:
        import winreg
    except ImportError:  # no es Windows
        return []
    claves = (
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        ),
        (winreg.HKEY_CURRENT_USER, "Environment"),
    )
    carpetas: list[str] = []
    for raiz, ruta in claves:
        try:
            with winreg.OpenKey(raiz, ruta) as clave:
                valor, _tipo = winreg.QueryValueEx(clave, "Path")
        except OSError:
            continue
        carpetas += [
            os.path.expandvars(p) for p in str(valor).split(os.pathsep) if p.strip()
        ]
    return carpetas


def _estado_docker() -> dict[str, str]:
    try:
        from qagent.sandbox.estado import estado_docker
    except ImportError:
        return {
            "estado": "no_instalado",
            "mensaje": "Falta el SDK de Docker para Python: pip install -r requirements.txt",
        }
    return estado_docker()


def verificar_entorno(
    ruta_config: str | Path | None = None,
    ruta_env: str | Path | None = None,
    simulado: bool | None = None,
    docker: Callable[[], dict[str, str]] = _estado_docker,
    git: Callable[[], dict[str, str]] = estado_git,
    carga: ResultadoCarga | None = None,
    ruta_local: str | Path | None = None,
) -> dict[str, Any]:
    """Verifica configuración, claves, Docker y Git. Nunca incluye valores de claves.

    Args:
        ruta_config: ruta de `config.toml`.
        ruta_env: ruta de `.env`.
        simulado: True si la IA es simulada y no hacen falta claves (None = según
            `QAGENT_FAKE_LLM`).
        docker: función que devuelve `{"estado", "mensaje"}` de Docker (inyectable).
        git: función que devuelve `{"estado", "mensaje"}` de Git (inyectable).
        carga: resultado ya cargado; si es None se lee de disco.
        ruta_local: `config.local.toml` opcional (ver `cargar_configuracion`).

    Returns:
        Diccionario con `listo` (bool), `simulado` (IA simulada de EN-11),
        `mensaje` ("Entorno listo" o el primer motivo),
        `problemas` (todos los motivos) y `comprobaciones` (lista de
        `{"id", "ok", "mensaje"}` para config, claves, docker y git).
    """
    carga = carga or cargar_configuracion(ruta_config, ruta_env, simulado, ruta_local)
    comprobaciones = [
        *_comprobar_configuracion(carga),
        _comprobar_docker(docker(), carga.simulado),
        _comprobar("git", git()),
    ]
    problemas = [
        *carga.avisos,
        *(
            c["mensaje"]
            for c in comprobaciones
            if c["id"] in {"docker", "git"} and not c["ok"]
        ),
    ]
    return {
        "listo": not problemas,
        "simulado": carga.simulado,
        "mensaje": _resumen(problemas),
        "problemas": problemas,
        "comprobaciones": comprobaciones,
    }


def _comprobar(identificador: str, estado: dict[str, str]) -> dict[str, Any]:
    return {
        "id": identificador,
        "ok": estado["estado"] == "ok",
        "mensaje": estado["mensaje"],
    }


def _comprobar_docker(estado: dict[str, str], simulado: bool) -> dict[str, Any]:
    """Docker es obligatorio, salvo con la IA simulada: ahí se informa pero no bloquea.

    Si Docker responde pero falta la imagen base, no bloquea: la primera corrida real la
    construye (`orchestrator.corrida._preparar_imagen`). Con el programa instalado no hay
    otro modo de construirla, así que bloquear dejaría al usuario sin salida (TA-06).
    """
    comprobacion = _comprobar("docker", estado)
    if estado["estado"] == "sin_imagen":
        comprobacion["ok"] = True
        comprobacion["pendiente"] = True  # se prepara en la primera corrida
    elif simulado and not comprobacion["ok"]:
        comprobacion["ok"] = True
        comprobacion["opcional"] = True
        comprobacion["mensaje"] = f"{MENSAJE_DOCKER_OPCIONAL} ({estado['mensaje']})"
    return comprobacion


def _comprobar_configuracion(carga: ResultadoCarga) -> list[dict[str, Any]]:
    """Una comprobación para `config.toml` y otra para las claves de `.env`."""
    return [
        {
            "id": "config",
            "ok": not carga.avisos_config,
            "mensaje": " ".join(carga.avisos_config) or "config.toml cargado.",
        },
        {
            "id": "claves",
            "ok": not carga.avisos_claves,
            "mensaje": MENSAJE_IA_SIMULADA
            if carga.simulado
            else " ".join(carga.avisos_claves) or "Claves de IA cargadas desde .env.",
        },
    ]


def _resumen(problemas: list[str]) -> str:
    if not problemas:
        return MENSAJE_LISTO
    extra = f" (y {len(problemas) - 1} problema(s) más)" if len(problemas) > 1 else ""
    return problemas[0] + extra
