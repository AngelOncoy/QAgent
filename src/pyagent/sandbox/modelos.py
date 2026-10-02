"""Tipos de datos y errores del sandbox Docker (EN-03)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LimitesSandbox:
    """Límites de recursos de un contenedor del sandbox.

    Atributos:
        cpus: número de CPU disponibles para el contenedor.
        memoria: memoria máxima en formato Docker (ej. "256m"); también es el tope de swap.
        timeout_s: segundos máximos de ejecución antes de matar el contenedor.
    """

    cpus: float = 1.0
    memoria: str = "256m"
    timeout_s: int = 60


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
    """

    exit_code: int
    stdout: str
    stderr: str
    coverage: dict[str, Any] | None = None
    timed_out: bool = False
    oom_killed: bool = False
    duracion_s: float = 0.0


class ErrorSandbox(Exception):
    """Error base del sandbox; su mensaje se puede mostrar al usuario."""


class DockerNoDisponible(ErrorSandbox):
    """Docker no está instalado o Docker Desktop no está iniciado."""


class ImagenNoEncontrada(ErrorSandbox):
    """La imagen base del sandbox no existe."""


class ErrorConstruccionImagen(ErrorSandbox):
    """Falló la construcción de una imagen (por ejemplo, pip install).

    Atributos:
        log: salida completa de la construcción, para diagnóstico.
    """

    def __init__(self, mensaje: str, log: str = "") -> None:
        super().__init__(mensaje)
        self.log = log
