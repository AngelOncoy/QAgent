"""Banco sin docstrings (#275, ADR-015): ninguna función está documentada ni tiene tipos.

Cada defecto sembrado solo se puede ver con el contexto del proyecto: el cuerpo, quien
llama a la función o un test existente dicen qué debería hacer.
"""


def aplicar_descuento(precio, porcentaje):
    # BUG 1: devuelve el monto del descuento, no el precio final.
    return precio * (porcentaje / 100)


def es_mayor_de_edad(edad):
    # BUG 2: con 18 años ya es mayor de edad (uso.py y su test lo asumen).
    return edad > 18


def doble(valor):
    # Control sin defecto: la prueba inferida debe pasar.
    return valor * 2
