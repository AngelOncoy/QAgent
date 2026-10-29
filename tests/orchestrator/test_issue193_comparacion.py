"""#193: clasificación determinista con resultados de Docker simulados."""

from __future__ import annotations

import pytest

from qagent.orchestrator.comparacion import clasificar_comparacion

HUELLA = "a" * 64
FIRMA = "(x: int) -> int"


def clasificar(**cambios):
    datos = {
        "decision_anterior": "bug_detectado",
        "decision_posterior": "accept",
        "firma_origen": FIRMA,
        "firma_verificacion": FIRMA,
        "huella_prueba_origen": HUELLA,
        "huella_prueba_verificacion": HUELLA,
    }
    datos.update(cambios)
    return clasificar_comparacion(**datos)


@pytest.mark.parametrize(
    ("anterior", "posterior", "esperado"),
    [
        ("bug_detectado", "accept", "corregido"),
        ("bug_detectado", "bug_detectado", "sigue_fallando"),
        ("accept", "bug_detectado", "regresion"),
    ],
)
def test_clasifica_resultados_comparables(anterior, posterior, esperado) -> None:
    resultado, motivo = clasificar(
        decision_anterior=anterior, decision_posterior=posterior
    )

    assert (resultado, motivo) == (esperado, None)


@pytest.mark.parametrize(
    ("cambios", "texto"),
    [
        ({"firma_verificacion": "(x: str) -> int"}, "firma"),
        ({"huella_prueba_verificacion": "b" * 64}, "misma prueba"),
        ({"huella_prueba_verificacion": None}, "identidad"),
        ({"estado_posterior_confiable": False}, "confiable"),
        ({"decision_posterior": "stalled"}, "veredictos"),
    ],
)
def test_duda_o_infraestructura_es_no_comparable(cambios, texto) -> None:
    resultado, motivo = clasificar(**cambios)

    assert resultado == "no_comparable"
    assert texto in motivo
