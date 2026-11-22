"""Mediciones locales de una corrida; no decide flujo ni interpreta resultados."""

from __future__ import annotations

import copy
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

_ACTUAL: ContextVar[RegistroRecursos | None] = ContextVar(
    "qagent_recursos", default=None
)


class RegistroRecursos:
    """Contadores observados, separados de recursos que no se han medido."""

    def __init__(self, cancelado: Callable[[], bool] | None = None) -> None:
        self._lock = threading.RLock()
        self._cancelado = cancelado
        self._cerrado = False
        self._cerrando = False
        self._contenedores: dict[str, Any] = {}
        self._inicio = time.monotonic()
        self._contadores: dict[str, int] = {}
        self._duraciones: dict[str, float] = {}
        self._datos: dict[str, Any] = {}

    def cancelado(self) -> bool:
        """El cierre también detiene trabajo tardío perteneciente a esta corrida."""
        return (
            self._cerrando
            or self._cerrado
            or bool(self._cancelado and self._cancelado())
        )

    def anotar_contenedor(self, contenedor: Any) -> None:
        """Posee solo contenedores creados dentro de esta sesión, nunca globales."""
        with self._lock:
            if not self._cerrando and not self._cerrado:
                self._contenedores[contenedor.id] = contenedor
                self.registrar("contenedores_creados")
                return
        # Una creación que termina después del cierre no puede dejar trabajo huérfano.
        contenedor.remove(force=True)
        raise RuntimeError("La corrida terminó durante la creación del contenedor.")

    def retirar_contenedor(self, contenedor: Any) -> None:
        """Registra la eliminación una sola vez, incluso al coincidir con el cierre."""
        with self._lock:
            if self._contenedores.pop(contenedor.id, None) is not None:
                self.registrar("contenedores_eliminados")

    def registrar(self, nombre: str, cantidad: int = 1, segundos: float = 0) -> None:
        """Acumula una observación; un trabajador tardío no cambia el cierre."""
        with self._lock:
            if not self._cerrado:
                self._contadores[nombre] = self._contadores.get(nombre, 0) + cantidad
                self._duraciones[nombre] = self._duraciones.get(nombre, 0) + segundos

    def fijar(self, nombre: str, valor: Any) -> None:
        """Guarda metadatos medidos sin referencias mutables del llamador."""
        with self._lock:
            if not self._cerrado:
                self._datos[nombre] = copy.deepcopy(valor)

    def cerrar(self) -> None:
        """Congela el registro; no mantiene fuentes ni objetos del parser."""
        with self._lock:
            self._cerrando = True
            propios = list(self._contenedores.values())
        for contenedor in propios:
            try:
                contenedor.remove(force=True)
                self.retirar_contenedor(contenedor)
            except Exception as error:  # noqa: BLE001 — el cierre conserva el fallo, no lo oculta
                if getattr(error, "status_code", None) == 404:
                    self.retirar_contenedor(contenedor)
                else:
                    self.registrar("contenedores_limpieza_fallida")
        with self._lock:
            self._datos["contenedores_propios_pendientes_al_cierre"] = len(
                self._contenedores
            )
            self._datos["duracion_observacion_s"] = round(
                time.monotonic() - self._inicio, 6
            )
            self._cerrado = True

    def resumen(self) -> dict[str, Any]:
        """JSON local; None significa no medido, nunca cero ni aprobación."""
        with self._lock:
            return {
                "version": "1",
                "cerrado": self._cerrado,
                "contadores": dict(self._contadores),
                "duraciones_s": {k: round(v, 6) for k, v in self._duraciones.items()},
                "datos": copy.deepcopy(self._datos),
                "no_medidos": {
                    "rss_host_bytes": None,
                    "pico_memoria_docker_bytes": None,
                    "cpu_docker_s": None,
                    "tiempo_descarga_red_s": None,
                },
            }


def recursos_actuales() -> RegistroRecursos | None:
    """Registro de esta corrida o None fuera de una sesión explícita."""
    return _ACTUAL.get()


@contextmanager
def medir(nombre: str) -> Iterator[None]:
    """Mide intentos y tiempo de una operación, conservando sus excepciones."""
    registro = recursos_actuales()
    inicio = time.monotonic()
    try:
        yield
    except BaseException:
        if registro:
            registro.registrar(nombre + "_fallidos")
        raise
    finally:
        if registro:
            registro.registrar(nombre, segundos=time.monotonic() - inicio)


@contextmanager
def sesion_recursos(
    cancelado: Callable[[], bool] | None = None,
) -> Iterator[RegistroRecursos]:
    """Aísla mediciones de corridas concurrentes y restaura el contexto anterior."""
    registro = RegistroRecursos(cancelado)
    token = _ACTUAL.set(registro)
    try:
        yield registro
    finally:
        registro.cerrar()
        _ACTUAL.reset(token)
