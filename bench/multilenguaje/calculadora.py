"""Módulo de cálculo comercial y clasificación para benchmark multilenguaje.

Este módulo sirve como referencia para evaluar las capacidades de extracción
de parsers estáticos (Python ast, Tree-sitter y parsers nativos).
"""

from __future__ import annotations


def calcular_descuento(precio: float, porcentaje: float) -> float:
    """Calcula el monto final tras aplicar un porcentaje de descuento.

    Args:
        precio: Monto original del producto, debe ser mayor o igual a 0.
        porcentaje: Porcentaje de descuento, valor entre 0 y 100 inclusive.

    Returns:
        float: Precio final con el descuento aplicado.

    Raises:
        ValueError: Si el precio es negativo o el porcentaje no está entre 0 y 100.
    """
    if precio < 0:
        raise ValueError("El precio no puede ser negativo.")
    if not (0 <= porcentaje <= 100):
        raise ValueError("El porcentaje debe estar entre 0 y 100.")

    descuento = precio * (porcentaje / 100.0)
    return precio - descuento


def clasificar_edad(edad: int) -> str:
    """Clasifica a una persona según su rango etario.

    Args:
        edad: Años cumplidos, debe ser mayor o igual a 0.

    Returns:
        str: Categoría ('menor', 'adulto', 'adulto mayor').

    Raises:
        ValueError: Si la edad es menor a 0.
    """
    if edad < 0:
        raise ValueError("La edad no puede ser negativa.")

    if edad < 18:
        return "menor"
    elif edad <= 64:
        return "adulto"
    else:
        return "adulto mayor"


def calcular_estadisticas(numeros: list[float]) -> dict[str, float]:
    """Calcula mínimo, máximo y promedio de una lista de valores numéricos.

    Args:
        numeros: Lista de números, no debe estar vacía.

    Returns:
        dict[str, float]: Diccionario con las claves 'minimo', 'maximo' y 'promedio'.

    Raises:
        ValueError: Si la lista está vacía.
    """
    if not numeros:
        raise ValueError("La lista no puede estar vacía.")

    minimo = numeros[0]
    maximo = numeros[0]
    suma = 0.0

    for n in numeros:
        minimo = min(minimo, n)
        maximo = max(maximo, n)
        suma += n

    promedio = suma / len(numeros)
    return {"minimo": minimo, "maximo": maximo, "promedio": promedio}


class GestorImpuestos:
    """Gestiona cálculos de impuestos y recargos comerciales."""

    def __init__(self, tasa_igv: float = 0.18):
        """Inicializa el gestor con una tasa de impuesto configurada."""
        if tasa_igv < 0:
            raise ValueError("La tasa de IGV no puede ser negativa.")
        self.tasa_igv = tasa_igv

    def aplicar_igv(self, base_imponible: float) -> float:
        """Calcula el importe total incluyendo el IGV."""
        if base_imponible < 0:
            raise ValueError("La base imponible no puede ser negativa.")
        return base_imponible * (1.0 + self.tasa_igv)

    def calcular_total_con_propina(
        self, subtotal: float, porcentaje_propina: float = 10.0
    ) -> float:
        """Calcula el total con IGV y propina voluntaria."""
        con_igv = self.aplicar_igv(subtotal)
        propina = subtotal * (porcentaje_propina / 100.0)
        return con_igv + propina


async def registrar_operacion(tipo: str, monto: float) -> bool:
    """Registra una operación financiera de forma asíncrona."""
    return bool(tipo and monto > 0)
