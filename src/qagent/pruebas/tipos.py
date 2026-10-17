"""Modelo escalar de los tipos de prueba del Sprint 1.

La estrategia describe *que clase de comprobacion* se ejecuta. No debe confundirse
con el tipo de objetivo de los contratos (``funcion`` o ``endpoint``), con el perfil
de ejecucion ni con la seleccion AST.
"""

from __future__ import annotations

from typing import Any

UNITARIA = "unitaria"
LIMITES = "limites"
HUMO = "humo"
REGRESION = "regresion"

ESTRATEGIAS_PRUEBA = (UNITARIA, LIMITES, HUMO, REGRESION)
ESTRATEGIA_POR_DEFECTO = UNITARIA


class EstrategiaInvalida(ValueError):
    """La estrategia no es un valor escalar admitido en el Sprint 1."""


def validar_estrategia(valor: Any) -> str:
    """Valida y devuelve una estrategia escalar.

    Las listas se rechazan expresamente: la seleccion multiple pertenece al Sprint 2.
    """
    if not isinstance(valor, str) or valor not in ESTRATEGIAS_PRUEBA:
        opciones = ", ".join(ESTRATEGIAS_PRUEBA)
        raise EstrategiaInvalida(
            f"Estrategia de prueba no valida: {valor!r}. Opciones: {opciones}."
        )
    return valor


def estrategia_historica(estrategia: Any = None, *, perfil: str | None = None) -> str:
    """Resuelve el valor nuevo o traduce perfiles historicos cuando esta ausente.

    ``reg`` y ``humo`` solo se interpretan aqui para leer llamadas y registros
    anteriores. Una estrategia explicita siempre tiene prioridad y se valida.
    """
    if estrategia is not None:
        return validar_estrategia(estrategia)
    if perfil == "reg":
        return REGRESION
    if perfil == "humo":
        return HUMO
    return ESTRATEGIA_POR_DEFECTO
