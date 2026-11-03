"""Modelo común de reglas arquitectónicas, independiente del lenguaje."""

from __future__ import annotations

import copy
from typing import Any

from qagent import contracts

REGLA_UNIVERSAL: dict[str, Any] = {
    "id": "universal-sin-ciclos",
    "tipo": "ciclos_importacion",
    "nombre": "No deben existir ciclos de importación",
    "origen": "universal",
    "confirmada": True,
}


def validar_documento(documento: dict[str, Any]) -> dict[str, Any]:
    """Valida el contrato y que no existan identificadores duplicados."""
    contracts.validar_versionado(contracts.FAMILIA_ARCHITECTURE_RULES, documento)
    ids = [regla["id"] for regla in documento["reglas"]]
    if len(ids) != len(set(ids)):
        raise contracts.ContratoInvalido(
            contracts.ARCHITECTURE_RULES_V1,
            ["reglas: los identificadores deben ser únicos"],
        )
    return documento


def reglas_para_proyecto(documento: dict[str, Any] | None = None) -> dict[str, Any]:
    """Agrega la regla universal sin modificar el documento persistido.

    Un archivo inexistente equivale a no tener reglas personalizadas. Una copia evita
    que quien llama pueda alterar accidentalmente las reglas guardadas.
    """
    personalizadas = copy.deepcopy(documento or {"version": "1", "reglas": []})
    validar_documento(personalizadas)
    reglas = [
        regla
        for regla in personalizadas["reglas"]
        if regla["id"] != REGLA_UNIVERSAL["id"]
    ]
    completo = {"version": "1", "reglas": [copy.deepcopy(REGLA_UNIVERSAL), *reglas]}
    return validar_documento(completo)


def reglas_ejecutables(documento: dict[str, Any]) -> list[dict[str, Any]]:
    """Devuelve solo reglas autorizadas: universales, de usuario y IA confirmadas."""
    validar_documento(documento)
    return [
        copy.deepcopy(regla)
        for regla in documento["reglas"]
        if regla["origen"] != "ia" or regla["confirmada"]
    ]


def resultado_no_ejecutado(regla: dict[str, Any], herramienta: str) -> dict[str, Any]:
    """Resultado explícito de una sugerencia que todavía no fue confirmada."""
    return {
        "id": regla["id"],
        "nombre": regla["nombre"],
        "tipo": regla["tipo"],
        "origen": regla["origen"],
        "estado": "no_ejecutada",
        "herramienta": herramienta,
        "hallazgos": [],
        "motivo_sin_veredicto": "La sugerencia requiere confirmación del usuario.",
    }
