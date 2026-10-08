"""Eventos de la corrida para el Monitor en vivo (HU-09)."""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

Suscriptor = Callable[["Evento"], None]


def _ahora() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass(frozen=True)
class Evento:
    """Un paso de la corrida.

    Atributos:
        agente: "orquestador", "planner", "generator" o "reviewer".
        archivo: módulo del proyecto que se está procesando.
        funcion: objetivo (función o endpoint), o None si aún no hay uno.
        mensaje: texto legible para el Monitor.
        estado: estado de la máquina en el momento del evento.
        tipo: "transicion", "agente", "veredicto", "fallo" o "fin".
        hora: fecha y hora ISO 8601 con zona horaria.
        datos: detalle opcional; el veredicto de un objetivo trae `decision` e
            `intento`, y si quedó estancado también `max_intentos`, `motivo` y
            `etiqueta` (HU-14).
    """

    agente: str
    archivo: str | None
    funcion: str | None
    mensaje: str
    estado: str
    tipo: str = "agente"
    hora: str = field(default_factory=_ahora)
    datos: dict[str, Any] | None = None

    def a_dict(self) -> dict[str, Any]:
        """Versión serializable a JSON (para la interfaz o el log)."""
        return asdict(self)


class BusEventos:
    """Reparte los eventos a sus suscriptores y guarda el historial.

    Un suscriptor que lanza una excepción no detiene la corrida.
    """

    def __init__(self) -> None:
        self._suscriptores: list[Suscriptor] = []
        self.historial: list[Evento] = []

    def suscribir(self, suscriptor: Suscriptor) -> None:
        """Registra una función que recibirá cada `Evento`."""
        self._suscriptores.append(suscriptor)

    def emitir(self, evento: Evento) -> None:
        """Guarda el evento y lo envía a todos los suscriptores."""
        self.historial.append(evento)
        for suscriptor in list(self._suscriptores):
            # El Monitor nunca debe tumbar la corrida.
            with contextlib.suppress(Exception):
                suscriptor(evento)
