"""Estados de la corrida y transiciones permitidas (EN-04)."""

from __future__ import annotations

from enum import Enum


class Estado(str, Enum):
    """Estados de la máquina de estados del orquestador."""

    PLANIFICAR = "planificar"
    GENERAR = "generar"
    EJECUTAR_REVISAR = "ejecutar_revisar"
    REINTENTAR = "reintentar"
    FIN = "fin"
    FALLO_CONTROLADO = "fallo_controlado"


TERMINALES = frozenset({Estado.FIN, Estado.FALLO_CONTROLADO})

TRANSICIONES: dict[Estado, frozenset[Estado]] = {
    # Un plan vacío (módulo sin funciones públicas) termina directo en FIN.
    Estado.PLANIFICAR: frozenset({Estado.GENERAR, Estado.FIN, Estado.FALLO_CONTROLADO}),
    Estado.GENERAR: frozenset({Estado.EJECUTAR_REVISAR, Estado.FALLO_CONTROLADO}),
    # Tras un veredicto final se pasa al siguiente objetivo del plan (GENERAR) o a FIN.
    Estado.EJECUTAR_REVISAR: frozenset(
        {Estado.REINTENTAR, Estado.GENERAR, Estado.FIN, Estado.FALLO_CONTROLADO}
    ),
    # Un reintento solo repite Generator -> Reviewer; nunca vuelve a PLANIFICAR.
    Estado.REINTENTAR: frozenset({Estado.GENERAR}),
    Estado.FIN: frozenset(),
    Estado.FALLO_CONTROLADO: frozenset(),
}


class TransicionInvalida(RuntimeError):
    """Se intentó una transición que la máquina de estados no permite."""


def validar_transicion(origen: Estado, destino: Estado) -> None:
    """Comprueba que `origen -> destino` esté en la tabla de transiciones.

    Raises:
        TransicionInvalida: si la transición no está permitida.
    """
    if destino not in TRANSICIONES[origen]:
        raise TransicionInvalida(
            f"Transición no permitida: {origen.value} -> {destino.value}"
        )
