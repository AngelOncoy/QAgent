"""Assertion Laundering en pruebas Vitest entre intentos, sin IA (EP-11a, parte 2).

Compara las aserciones ``expect`` de la prueba de referencia (la que ya cumplía el
oráculo) con las de la reparación. Es laundering si la reparación:

* elimina una aserción;
* cambia su valor esperado;
* la debilita: ``toEqual``/``toBe`` por ``toBeDefined``/``toBeTruthy``, o
  ``toThrow(RangeError)`` por ``toThrow()``;
* le agrega ``.not``;
* la envuelve en un ``try/catch`` que se traga el error, la omite (``it.skip``,
  ``it.todo``, ``it.fails``, ``xit``) o la reemplaza por un ``expect`` sobre un
  literal.

Reordenar aserciones, cambiar el formato, los comentarios, el título de la prueba o
usar una variable ``const`` intermedia no es laundering. Como en Python y Java, el
análisis es estático (tree-sitter) y corre antes de ejecutar (ADR-010, 4.2).
"""

from __future__ import annotations

from dataclasses import dataclass

from qagent.lenguajes.javascript_aserciones import (
    EXCEPCION,
    IGUALDAD,
    AsercionVitest,
    analizar_vitest,
)


@dataclass(frozen=True)
class ResultadoComparacionVitest:
    """Diferencias encontradas; cumple ``ComparacionAserciones`` (``es_laundering`` y ``resumen``)."""

    es_laundering: bool
    aserciones_contrato: tuple[AsercionVitest, ...]
    aserciones_sintetizadas: tuple[AsercionVitest, ...]
    diferencias: tuple[str, ...]
    resumen: str


def comparar_vitest(
    original: str, reparado: str, lenguaje: str
) -> ResultadoComparacionVitest:
    """Detecta si ``reparado`` debilitó las aserciones de ``original``.

    Raises:
        SyntaxError: si alguna de las dos pruebas no se puede parsear.
        ValueError: si alguna es demasiado grande para el guardrail.
    """
    antes = analizar_vitest(original, lenguaje)
    despues = analizar_vitest(reparado, lenguaje)
    diferencias = list(despues.evasiones)
    disponibles = list(despues.aserciones)
    for asercion in antes.aserciones:
        conservada = _buscar(asercion, disponibles, _conserva)
        if conservada is not None:
            disponibles.remove(conservada)
            continue
        candidata = _buscar(asercion, disponibles, _mismo_sujeto)
        if candidata is None:
            diferencias.append(
                f"Aserción eliminada (línea original {asercion.linea}): {asercion.texto}"
            )
            continue
        disponibles.remove(candidata)
        diferencias.append(_motivo(asercion, candidata))
    if antes.aserciones and not despues.aserciones:
        diferencias.append("La reparación no conserva ninguna aserción expect.")
    diferencias = list(dict.fromkeys(diferencias))
    resumen = (
        "Assertion Laundering detectado:\n" + "\n".join(f"- {d}" for d in diferencias)
        if diferencias
        else "Sin Assertion Laundering: se conservaron las aserciones y sus valores esperados."
    )
    return ResultadoComparacionVitest(
        es_laundering=bool(diferencias),
        aserciones_contrato=tuple(antes.aserciones),
        aserciones_sintetizadas=tuple(despues.aserciones),
        diferencias=tuple(diferencias),
        resumen=resumen,
    )


def _buscar(
    asercion: AsercionVitest, disponibles: list[AsercionVitest], criterio
) -> AsercionVitest | None:
    """Primera que cumple ``criterio``, prefiriendo la misma prueba."""
    candidatas = [n for n in disponibles if criterio(asercion, n)]
    return next(
        (n for n in candidatas if n.prueba == asercion.prueba),
        candidatas[0] if candidatas else None,
    )


def _mismo_sujeto(original: AsercionVitest, nueva: AsercionVitest) -> bool:
    return original.sujeto == nueva.sujeto


def _conserva(original: AsercionVitest, nueva: AsercionVitest) -> bool:
    """Mismo sujeto, modificadores y esperado; el matcher no pierde rigor."""
    if (
        original.sujeto != nueva.sujeto
        or original.negada != nueva.negada
        or original.modificadores != nueva.modificadores
        or original.esperado != nueva.esperado
    ):
        return False
    if original.matcher == nueva.matcher:
        return True
    if original.negada:  # con .not, cambiar el matcher cambia el significado
        return False
    mismo_grupo = (
        original.matcher in IGUALDAD
        and nueva.matcher in IGUALDAD
        or original.matcher in EXCEPCION
        and nueva.matcher in EXCEPCION
    )
    return mismo_grupo and nueva.rigor >= original.rigor


def _motivo(original: AsercionVitest, nueva: AsercionVitest) -> str:
    """Explica cómo cambió una aserción con el mismo sujeto."""
    detalle = f"(línea {nueva.linea}): «{original.texto}» -> «{nueva.texto}»"
    if nueva.negada and not original.negada:
        return f"Se agregó .not a la aserción {detalle}"
    if original.negada and not nueva.negada:
        return f"Se quitó .not de la aserción {detalle}"
    if nueva.rigor < original.rigor and nueva.matcher != original.matcher:
        return f"Aserción debilitada de {original.matcher} a {nueva.matcher} {detalle}"
    if nueva.esperado is None:
        return f"Se quitó el valor esperado {detalle}"
    if original.esperado != nueva.esperado:
        return f"Valor esperado cambiado {detalle}"
    if original.modificadores != nueva.modificadores:
        return f"Modificador cambiado {detalle}"
    return f"Aserción modificada de {original.matcher} a {nueva.matcher} {detalle}"
