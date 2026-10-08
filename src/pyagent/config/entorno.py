"""Verificación del entorno al abrir un proyecto (EN-06).

Reúne en un solo resultado lo que necesita la interfaz: configuración y claves
(`carga`), Docker con su imagen base (`sandbox.estado`) y Git. Si algo falla, indica el
motivo y no se permite iniciar corridas.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pyagent.config.carga import (
    RUTA_CONFIG,
    RUTA_ENV,
    ResultadoCarga,
    cargar_configuracion,
)

MENSAJE_LISTO = "Entorno listo"
MENSAJE_IA_SIMULADA = (
    "IA simulada activa (PYAGENT_FAKE_LLM=1): respuestas grabadas, 0 tokens y US$ 0. "
    "No se usan las claves de .env."
)
TIMEOUT_GIT_S = 5
MENSAJE_GIT_AUSENTE = (
    "Git no está instalado o no está en el PATH. Instálalo desde https://git-scm.com "
    "y reinicia la aplicación."
)
MENSAJE_GIT_ERROR = (
    "Git está instalado pero no responde. Ejecuta 'git --version' en una terminal."
)


def estado_git() -> dict[str, str]:
    """Comprueba que `git` exista y responda, sin lanzar excepciones.

    Returns:
        `{"estado": "ok" | "no_instalado" | "error", "mensaje": str}`.
    """
    if shutil.which("git") is None:
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


def _estado_docker() -> dict[str, str]:
    try:
        from pyagent.sandbox.estado import estado_docker
    except ImportError:
        return {
            "estado": "no_instalado",
            "mensaje": "Falta el SDK de Docker para Python: pip install -r requirements.txt",
        }
    return estado_docker()


def verificar_entorno(
    ruta_config: str | Path = RUTA_CONFIG,
    ruta_env: str | Path = RUTA_ENV,
    simulado: bool | None = None,
    docker: Callable[[], dict[str, str]] = _estado_docker,
    git: Callable[[], dict[str, str]] = estado_git,
    carga: ResultadoCarga | None = None,
) -> dict[str, Any]:
    """Verifica configuración, claves, Docker y Git. Nunca incluye valores de claves.

    Args:
        ruta_config: ruta de `config.toml`.
        ruta_env: ruta de `.env`.
        simulado: True si la IA es simulada y no hacen falta claves (None = según
            `PYAGENT_FAKE_LLM`).
        docker: función que devuelve `{"estado", "mensaje"}` de Docker (inyectable).
        git: función que devuelve `{"estado", "mensaje"}` de Git (inyectable).
        carga: resultado ya cargado; si es None se lee de disco.

    Returns:
        Diccionario con `listo` (bool), `simulado` (IA simulada de EN-11),
        `mensaje` ("Entorno listo" o el primer motivo),
        `problemas` (todos los motivos) y `comprobaciones` (lista de
        `{"id", "ok", "mensaje"}` para config, claves, docker y git).
    """
    carga = carga or cargar_configuracion(ruta_config, ruta_env, simulado)
    comprobaciones = [
        *_comprobar_configuracion(carga),
        _comprobar("docker", docker()),
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
