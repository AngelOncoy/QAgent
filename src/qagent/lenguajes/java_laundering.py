"""Comparación determinista de aserciones JUnit entre intentos, sin IA (#184)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from qagent.lenguajes.java_aserciones import AsercionJava, analizar_junit, literal


@dataclass(frozen=True)
class ResultadoComparacionJava:
    """Diferencias estáticas y resumen compatible con ComparacionAserciones."""

    es_laundering: bool
    aserciones_contrato: tuple[AsercionJava, ...]
    aserciones_sintetizadas: tuple[AsercionJava, ...]
    diferencias: tuple[str, ...]
    resumen: str


def comparar_java(original: str, reparado: str) -> ResultadoComparacionJava:
    """Conserva cada aserción y su multiplicidad, sujeto, esperado y tolerancia.

    Permite reordenar aserciones, cambiar mensajes, formato y alias locales
    estables. Si cambia una expresión no demostrable se exige reafirmar el
    contrato; no se infiere equivalencia ejecutando código ni consultando IA.
    """
    antes, despues = analizar_junit(original), analizar_junit(reparado)
    diferencias = list(despues.evasiones)
    disponibles = list(despues.aserciones)
    for asercion in antes.aserciones:
        indice = next(
            (i for i, nueva in enumerate(disponibles) if _conserva(asercion, nueva)),
            None,
        )
        if indice is not None:
            disponibles.pop(indice)
        else:
            diferencias.append(
                f"Aserción eliminada o modificada: {asercion.tipo}, esperado {asercion.esperado}, línea original {asercion.linea}. No se permite cambiar el sujeto o el valor esperado ni aumentar la tolerancia para aprobar."
            )
    if not despues.aserciones:
        diferencias.append("La reparación no conserva aserciones JUnit verificables.")
    diferencias = list(dict.fromkeys(diferencias))
    resumen = (
        ("Assertion Laundering detectado:\n" + "\n".join(diferencias))
        if diferencias
        else "Sin Assertion Laundering: se conservaron las aserciones y sus valores esperados."
    )
    return ResultadoComparacionJava(
        bool(diferencias),
        tuple(antes.aserciones),
        tuple(despues.aserciones),
        tuple(diferencias),
        resumen,
    )


def _conserva(original: AsercionJava, nueva: AsercionJava) -> bool:
    """Mantiene el caso y su esperado; permite reducir una tolerancia existente."""
    if (
        original.tipo != nueva.tipo
        or original.sujeto != nueva.sujeto
        or original.esperado != nueva.esperado
    ):
        return False
    if original.tolerancia == nueva.tolerancia:
        return True
    antes = literal(original.delta, original.alias)
    if isinstance(antes, Decimal) and antes >= 0:
        if nueva.delta is None:
            return True
        despues = literal(nueva.delta, nueva.alias)
        return isinstance(despues, Decimal) and 0 <= despues <= antes
    return False
