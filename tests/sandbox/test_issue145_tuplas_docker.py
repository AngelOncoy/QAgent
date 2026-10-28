"""Integración real en Docker para la regresión de tuplas de la issue #145."""

from __future__ import annotations

from pathlib import Path

import pytest

from qagent.agents.reviewer import ReviewerAgent
from qagent.llm import TokenTracker
from qagent.llm.fake import generar_test_desde_contrato


@pytest.mark.docker
def test_funcion_documentada_con_tupla_aprueba_en_primer_intento(
    imagen_base: str,
) -> None:
    """El código del proyecto solo se ejecuta dentro del sandbox Docker."""
    proyecto = Path(__file__).parents[1] / "fixtures" / "issue145_tuplas"
    contrato = {
        "version": "2",
        "modulo": "dimensiones.py",
        "huella": "a" * 64,
        "tipo": "funcion",
        "objetivo": "alto_y_ancho",
        "firma": "(alto: int, ancho: int) -> tuple[int, int]",
        "critical": False,
        "llama_a": [],
        "casos": [
            {
                "id": "dimensiones",
                "entrada": {"alto": 4, "ancho": 3},
                "valor_esperado": [4, 3],
                "tipo_valor_esperado": "tuple",
                "origen": "docstring",
            }
        ],
    }
    codigo = generar_test_desde_contrato(contrato)
    generado = {
        "version": "1",
        "objetivo": "alto_y_ancho",
        "intento": 1,
        "codigo": codigo,
        "casos_cubiertos": ["dimensiones"],
    }

    revision = ReviewerAgent(TokenTracker(), proyecto, imagen_base).revisar(
        contrato, generado, None
    )

    assert "== (4, 3)" in codigo
    assert revision["estado_sandbox"] == "ok"
    assert revision["decision"] == "accept"
    assert revision["laundering_detectado"] is False
    assert revision["intento"] == 1
    assert revision["ejecucion"]["casos"][0]["resultado"] == "paso"
