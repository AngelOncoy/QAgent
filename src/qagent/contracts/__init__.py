"""Validación de los contratos JSON entre agentes (EN-01).

Los schemas viven junto a este módulo (`qagent/contracts/`, se instalan con el paquete). El orquestador valida cada
mensaje con `validar()` antes de pasarlo al siguiente agente.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

DIR_CONTRATOS = Path(__file__).resolve().parent

PLANNER = "planner_contract.v2"
GENERATED_TEST = "generated_test"
REVIEW_RESULT = "review_result"
RUN_LOG = "run_log"
DETALLE = "detalle"
CONTRATOS = (PLANNER, GENERATED_TEST, REVIEW_RESULT, RUN_LOG, DETALLE)


#: Categorías de un caso de prueba (#76), del contrato del Planner.
CATEGORIAS = ("normal", "limite", "error")


def es_caso_de_error(caso: dict[str, Any]) -> bool:
    """Si el caso espera un error: una excepción o, en un endpoint, un 4xx/5xx."""
    if "excepcion" in caso:
        return True
    esperado = caso.get("valor_esperado")
    estado = esperado.get("status_code") if isinstance(esperado, dict) else None
    return isinstance(estado, int) and estado >= 400


def categoria_de(caso: dict[str, Any]) -> str:
    """Categoría de un caso (#76); si no la trae (specs anteriores), la infiere.

    Se infiere `error` si el caso espera una excepción o un 4xx/5xx y `normal` en los
    demás casos: un caso límite no se puede distinguir sin que lo declare el Planner.
    """
    categoria = caso.get("categoria")
    if categoria in CATEGORIAS:
        return categoria
    return "error" if es_caso_de_error(caso) else "normal"


def contar_categorias(casos: Any) -> dict[str, int]:
    """Casos por categoría, con las tres claves aunque alguna sea 0."""
    conteo = dict.fromkeys(CATEGORIAS, 0)
    for caso in casos if isinstance(casos, list) else []:
        if isinstance(caso, dict):
            conteo[categoria_de(caso)] += 1
    return conteo


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
