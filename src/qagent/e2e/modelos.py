"""Modelos pequeños y límites explícitos del humo E2E."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RutaWeb:
    """Ruta descubierta o declarada sin inventar parámetros."""

    path: str
    source: str
    route_type: str = "page"
    eligible: bool = True
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Representación JSON estable."""
        return {
            "path": self.path,
            "source": self.source,
            "route_type": self.route_type,
            "eligible": self.eligible,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ConfiguracionE2E:
    """Límites del flujo, reemplazables por parámetros confiables de la app."""

    port: int = 4173
    max_routes: int = 25
    startup_timeout_s: int = 30
    route_timeout_s: int = 10
    total_timeout_s: int = 120
    settle_ms: int = 250
    cpus: float = 2.0
    memory: str = "2g"

    def validate(self) -> None:
        """Rechaza límites absurdos antes de construir o ejecutar un contenedor."""
        if not 1024 <= self.port <= 65535:
            raise ValueError("El puerto E2E debe estar entre 1024 y 65535.")
        if not 1 <= self.max_routes <= 100:
            raise ValueError("El máximo de rutas debe estar entre 1 y 100.")
        if not 1 <= self.startup_timeout_s <= 300:
            raise ValueError("El timeout de arranque debe estar entre 1 y 300 s.")
        if not 1 <= self.route_timeout_s <= 120:
            raise ValueError("El timeout por ruta debe estar entre 1 y 120 s.")
        if not 1 <= self.total_timeout_s <= 900:
            raise ValueError("El timeout total debe estar entre 1 y 900 s.")
        if not 0 <= self.settle_ms <= 5000:
            raise ValueError(
                "La espera de estabilización debe estar entre 0 y 5000 ms."
            )
        if not 0.25 <= self.cpus <= 8:
            raise ValueError("El límite de CPU E2E debe estar entre 0.25 y 8.")
        match = re.fullmatch(r"(\d+)([mg])", self.memory.lower())
        if not match:
            raise ValueError(
                "La memoria E2E debe usar el formato de Docker, por ejemplo 2g."
            )
        megabytes = int(match.group(1)) * (1024 if match.group(2) == "g" else 1)
        if not 256 <= megabytes <= 8192:
            raise ValueError("La memoria E2E debe estar entre 256m y 8g.")
