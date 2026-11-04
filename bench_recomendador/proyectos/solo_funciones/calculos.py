"""Cálculos de una tienda: precios, descuentos y clasificación de pedidos."""


def calcular_descuento(precio: float, porcentaje: float) -> float:
    """Aplica un porcentaje de descuento al precio.

    Args:
        precio: precio original, mayor o igual que 0.
        porcentaje: descuento entre 0 y 100.

    Returns:
        El precio final con el descuento aplicado.

    Raises:
        ValueError: si el porcentaje está fuera de 0 a 100.
    """
    if not 0 <= porcentaje <= 100:
        raise ValueError("porcentaje fuera de rango")
    return precio * (1 - porcentaje / 100)


def clasificar_pedido(total: float) -> str:
    """Devuelve 'pequeño' si el total es menor que 50, 'mediano' hasta 200 y 'grande' después."""
    if total < 50:
        return "pequeño"
    if total <= 200:
        return "mediano"
    return "grande"


def sumar_iva(precio: float, tasa: float = 0.21) -> float:
    """Suma el IVA al precio. La tasa por defecto es 0.21."""
    return precio * (1 + tasa)


def etiqueta(nombre, cantidad):
    return f"{nombre} x{cantidad}"
