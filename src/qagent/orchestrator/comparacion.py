"""Clasificación determinista de comparaciones entre corridas (#193).

No ejecuta pruebas ni código del usuario. #194 consumirá esta API después de correr la
misma prueba guardada; #195 presentará los registros persistidos.
"""

from __future__ import annotations


def clasificar_comparacion(
    *,
    decision_anterior: str,
    decision_posterior: str,
    firma_origen: str | None,
    firma_verificacion: str | None,
    huella_prueba_origen: str | None,
    huella_prueba_verificacion: str | None,
    estado_anterior_confiable: bool = True,
    estado_posterior_confiable: bool = True,
) -> tuple[str, str | None]:
    """Devuelve el estado de comparación y, si aplica, su motivo.

    Solo emite un estado concluyente cuando se ejecutó exactamente la misma prueba,
    la firma no cambió y ambos veredictos son confiables. Cualquier duda se conserva
    como ``no_comparable`` en vez de inferir una corrección falsa.
    """
    if not estado_anterior_confiable:
        return "no_comparable", "El resultado de origen no es confiable."
    if not estado_posterior_confiable:
        return "no_comparable", "La verificación no terminó con un resultado confiable."
    if not huella_prueba_origen or not huella_prueba_verificacion:
        return "no_comparable", "Falta la identidad verificable de la prueba original."
    if huella_prueba_origen != huella_prueba_verificacion:
        return "no_comparable", "La verificación no utilizó la misma prueba original."
    if not firma_origen or not firma_verificacion:
        return "no_comparable", "Falta la firma del contrato de origen o verificación."
    if firma_origen != firma_verificacion:
        return "no_comparable", "La firma del objetivo cambió."

    estados = {
        ("bug_detectado", "accept"): "corregido",
        ("bug_detectado", "bug_detectado"): "sigue_fallando",
        ("accept", "bug_detectado"): "regresion",
    }
    resultado = estados.get((decision_anterior, decision_posterior))
    if resultado is None:
        return (
            "no_comparable",
            "La combinación de veredictos no demuestra una corrección ni una regresión.",
        )
    return resultado, None
