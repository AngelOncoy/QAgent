"""Pedidos del banco de integración interna.

``total_del_pedido`` tiene un defecto sembrado que solo se ve al combinar funciones
(ver ``README.md``): una prueba unitaria que simula ``aplicar_descuento`` no lo detecta.
"""

from __future__ import annotations

from precios import aplicar_descuento, con_impuesto, sello_de_hora


def total_del_pedido(precio: float, descuento: float, cantidad: int) -> float:
    """Total del pedido: el precio con descuento, por la cantidad.

    Args:
        precio: precio unitario, mayor o igual que 0.
        descuento: descuento como fracción (0.2 significa 20 %).
        cantidad: unidades, mayor que 0.

    Returns:
        ``precio * (1 - descuento) * cantidad``. Con 100.0, 0.2 y 2 devuelve 160.0.
    """
    # DEFECTO SEMBRADO: aplicar_descuento espera un porcentaje (0-100) y aquí se le
    # pasa una fracción (0-1). Cada función es correcta por separado.
    return aplicar_descuento(precio, descuento) * cantidad


def total_con_impuesto(precio: float, tasa: float, cantidad: int) -> float:
    """Total con impuesto: el precio con impuesto, por la cantidad.

    Args:
        precio: precio unitario, mayor o igual que 0.
        tasa: impuesto como fracción (0.18 significa 18 %).
        cantidad: unidades, mayor que 0.

    Returns:
        ``precio * (1 + tasa) * cantidad``. Con 100.0, 0.1 y 2 devuelve 220.0.
    """
    return con_impuesto(precio, tasa) * cantidad


def recibo(precio: float, cantidad: int) -> dict:
    """Recibo del pedido con su sello de hora.

    Args:
        precio: precio unitario.
        cantidad: unidades.

    Returns:
        Diccionario con ``total`` (precio por cantidad) y ``sello`` (la hora).
    """
    return {"total": precio * cantidad, "sello": sello_de_hora()}
