"""Utilidades de tiempo para la corrida (#115).

Las duraciones se miden siempre con un reloj monotónico (`time.monotonic`) y solo se
persisten sus diferencias en segundos. Las marcas de inicio y fin se guardan como
fechas UTC ISO 8601 para el historial; nunca se guarda el valor crudo del reloj.
"""

from __future__ import annotations

from datetime import datetime, timezone

#: Claves de las etapas medidas en una corrida.
ETAPAS = ("planner", "generator", "reviewer", "sandbox", "pytest")


def ahora_utc() -> datetime:
    """Momento actual en UTC (con zona horaria)."""
    return datetime.now(timezone.utc)


def iso_utc(momento: datetime | None = None) -> str:
    """Fecha UTC en ISO 8601 con milisegundos y sufijo ``Z``."""
    momento = momento or ahora_utc()
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    momento = momento.astimezone(timezone.utc)
    return momento.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def segundos(desde: float, hasta: float) -> float:
    """Diferencia entre dos lecturas del reloj monotónico, redondeada a milisegundos."""
    return round(max(0.0, hasta - desde), 3)


def etapas_vacias() -> dict[str, float]:
    """Contadores de las etapas en cero."""
    return {etapa: 0.0 for etapa in ETAPAS}


def sumar_etapa(etapas: dict[str, float], etapa: str, duracion_s: float) -> None:
    """Acumula una duración en una etapa (sin contar dos veces)."""
    etapas[etapa] = round(etapas.get(etapa, 0.0) + max(0.0, duracion_s), 3)
