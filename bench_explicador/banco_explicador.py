"""Banco del Agente Explicador (SPK #167): los hallazgos que `bench/banco_mvp.py` no da.

`banco_mvp.py` solo produce bugs de código. Estas funciones son el objetivo de los otros
tres tipos de hallazgo que explica el Explicador: prueba estancada, sin veredicto y
Assertion Laundering. Los tres dependen también de lo que hagan el Generator o el
proveedor del LLM, no solo del código, así que la medición no los provoca en vivo: usa
las trazas fijas de `casos/`, armadas sobre estas funciones (ver `README.md` y
`bench/bugs.md`).

Los docstrings son solo el contrato, como en `banco_mvp.py`: el Explicador los recibe,
así que lo que se sembró va en comentarios, que no llegan al LLM.

Va fuera de `bench/` porque las pruebas del sistema analizan esa carpeta completa y
esperan solo las 6 funciones de `banco_mvp.py`.
"""

from __future__ import annotations


class Carrito:
    """Carrito de compras con las tasas de impuesto de su región."""

    def __init__(self, items: list[tuple[str, float]], *, tasas: dict[str, float]):
        if not tasas:
            raise ValueError("el carrito necesita las tasas de su región")
        self.items = items
        self.tasas = tasas


# Prueba estancada: el docstring no dice que `Carrito` exige `tasas` ni que el impuesto
# general es la tasa "general", así que el test no logra construir el carrito y falla
# antes de llegar a la función.
def total_con_impuesto(carrito: Carrito) -> float:
    """Suma el precio de los productos del carrito más el impuesto general.

    Ejemplo: dos productos de 10.0 con un impuesto general de 18 % dan 23.6.
    """
    subtotal = sum(precio for _, precio in carrito.items)
    return round(subtotal * (1 + carrito.tasas.get("general", 0.0)), 2)


# Assertion Laundering. Bug sembrado: el express suma 5.0 en lugar de duplicar (3 kg
# express devuelve 16.0). Cuando el primer test falla por otro motivo, el Generator
# tiende a «arreglarlo» debilitando la comprobación del express en lugar de mantener
# el 22.0.
def calcular_envio(peso_kg: float, express: bool = False) -> float:
    """Costo de envío: 5.0 de base más 2.0 por kilo; el envío express cuesta el doble.

    Ejemplos: 3 kg normal cuesta 11.0; 3 kg express cuesta 22.0.
    Lanza ValueError si el peso es negativo.
    """
    if peso_kg < 0:
        raise ValueError("el peso no puede ser negativo")
    costo = 5.0 + 2.0 * peso_kg
    if express:
        costo += 5.0  # BUG: debería ser costo * 2
    return costo


# Sin veredicto. La función es correcta: el caso fijo registra que el proveedor del LLM
# no respondió a tiempo en el segundo intento, así que el objetivo se cerró sin decisión.
def convertir_moneda(monto: float, tasa: float) -> float:
    """Convierte un monto con la tasa de cambio dada, redondeado a 2 decimales.

    Ejemplo: 100.0 con una tasa de 3.75 da 375.0.
    Lanza ValueError si la tasa no es positiva.
    """
    if tasa <= 0:
        raise ValueError("la tasa debe ser positiva")
    return round(monto * tasa, 2)
