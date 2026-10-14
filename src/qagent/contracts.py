"""Validación de los contratos JSON entre agentes (EN-01).

Los schemas viven en `contracts/` (raíz del repositorio). El orquestador valida cada
mensaje con `validar()` antes de pasarlo al siguiente agente.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

DIR_CONTRATOS = Path(__file__).resolve().parents[2] / "contracts"

PLANNER = "planner_contract.v2"
GENERATED_TEST = "generated_test"
REVIEW_RESULT = "review_result"
RUN_LOG = "run_log"
CONTRATOS = (PLANNER, GENERATED_TEST, REVIEW_RESULT, RUN_LOG)


class ContratoInvalido(ValueError):
    """Un mensaje no cumple su contrato.

    Atributos:
        contrato: nombre del contrato (ej. "review_result").
        errores: lista de errores legibles con la forma "ruta: motivo".
    """

    def __init__(self, contrato: str, errores: list[str]) -> None:
        self.contrato = contrato
        self.errores = errores
        detalle = "; ".join(errores)
        super().__init__(f"El mensaje no cumple el contrato '{contrato}': {detalle}")


def ruta_schema(nombre: str) -> Path:
    """Devuelve la ruta del archivo `<nombre>.schema.json`.

    Raises:
        KeyError: si el contrato no existe.
    """
    if nombre not in CONTRATOS:
        raise KeyError(
            f"Contrato desconocido: {nombre}. Opciones: {', '.join(CONTRATOS)}"
        )
    return DIR_CONTRATOS / f"{nombre}.schema.json"


@cache
def cargar_schema(nombre: str) -> dict[str, Any]:
    """Carga (una sola vez) el JSON Schema de un contrato."""
    return json.loads(ruta_schema(nombre).read_text(encoding="utf-8"))


@cache
def _validador(nombre: str) -> Draft202012Validator:
    return Draft202012Validator(cargar_schema(nombre))


def errores(nombre: str, dato: Any) -> list[str]:
    """Lista los errores de `dato` frente al contrato; vacía si es válido."""
    encontrados = sorted(
        _validador(nombre).iter_errors(dato), key=lambda e: list(e.path)
    )
    return [_formatear(e.path, e.message) for e in encontrados]


def validar(nombre: str, dato: Any) -> Any:
    """Valida `dato` contra el contrato y lo devuelve sin cambios.

    Raises:
        ContratoInvalido: con todos los errores encontrados.
    """
    lista = errores(nombre, dato)
    if lista:
        raise ContratoInvalido(nombre, lista)
    return dato


def es_valido(nombre: str, dato: Any) -> bool:
    """Indica si `dato` cumple el contrato."""
    return not errores(nombre, dato)


def _formatear(ruta: Any, mensaje: str) -> str:
    texto = "/".join(str(p) for p in ruta) or "(raíz)"
    return f"{texto}: {mensaje}"
