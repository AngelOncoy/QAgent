"""Mapa de llamadas con alias, imports relativos y de paquetes (TA-16)."""
import funciones
import funciones as fn
from funciones import simple as sumar, ramas
from paquete import sub
from paquete.sub import util as utilidades
import paquete.sub.util


def calcular_total(n: int) -> int:
    """Total."""
    return sumar(n, 1) + fn.simple(1, 2) + funciones.con_tipos(1) + ramas(n) + validar()


def validar():
    return sub.util.ayuda(1) + utilidades.ayuda(2) + paquete.sub.util.ayuda(3) + _interna() + calcular_total(0)


def _interna():
    return (sumar)(1, 2)


def recursiva(n):
    return recursiva(n - 1) if n else 0
