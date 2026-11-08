"""Precios del banco de integración interna: funciones puras y una con efecto."""

from __future__ import annotations

import time


def aplicar_descuento(precio: float, porcentaje: float) -> float:
    """Devuelve el precio con el descuento aplicado.

    Args:
        precio: precio base, mayor o igual que 0.
        porcentaje: descuento entre 0 y 100 (20 significa 20 %).

    Returns:
        El precio menos ese porcentaje.

    Raises:
        ValueError: si el porcentaje no está entre 0 y 100.
    """
    if not 0 <= porcentaje <= 100:
        raise ValueError("El porcentaje debe estar entre 0 y 100")
    return precio * (1 - porcentaje / 100)


def con_impuesto(precio: float, tasa: float) -> float:
    """Suma el impuesto al precio.

    Args:
        precio: precio sin impuesto.
        tasa: impuesto como fracción (0.18 significa 18 %).

    Returns:
        El precio más ``precio * tasa``.
    """
    return precio * (1 + tasa)


def sello_de_hora() -> float:
    """Segundos desde la época: depende del reloj (función con efecto)."""
    return time.time()
