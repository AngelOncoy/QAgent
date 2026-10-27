"""Validación de los contratos JSON entre agentes (EN-01).

Los schemas viven junto a este módulo (`qagent/contracts/`, se instalan con el paquete). El orquestador valida cada
mensaje con `validar()` antes de pasarlo al siguiente agente.
"""

from __future__ import annotations

import copy
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
#: EN-17: versiones con lenguaje y framework. `PLANNER` y `GENERATED_TEST` siguen
#: siendo las que produce y guarda el flujo de Python.
PLANNER_V3 = "planner_contract.v3"
GENERATED_TEST_V2 = "generated_test.v2"
ORACLE_V1 = "oracle.v1"
EXPLANATION_V1 = "explanation.v1"
CONTRATOS = (
    PLANNER,
    GENERATED_TEST,
    REVIEW_RESULT,
    RUN_LOG,
    DETALLE,
    PLANNER_V3,
    GENERATED_TEST_V2,
    ORACLE_V1,
    EXPLANATION_V1,
)

#: Familias de contratos versionados: valor del campo `version` -> contrato.
FAMILIA_PLANNER = "planner_contract"
FAMILIA_GENERATED_TEST = "generated_test"
FAMILIA_ORACLE = "oracle"
FAMILIA_EXPLANATION = "explanation"
VERSIONES: dict[str, dict[str, str]] = {
    FAMILIA_PLANNER: {"2": PLANNER, "3": PLANNER_V3},
    FAMILIA_GENERATED_TEST: {"1": GENERATED_TEST, "2": GENERATED_TEST_V2},
    FAMILIA_ORACLE: {"1": ORACLE_V1},
    FAMILIA_EXPLANATION: {"1": EXPLANATION_V1},
}

#: Lenguajes que pueden aparecer en un contrato (EN-17) y sus frameworks válidos.
#: Debe coincidir con los `enum` de los schemas v3 / v2 (lo verifica una prueba).
FRAMEWORKS_PRUEBAS: dict[str, tuple[str, ...]] = {
    "python": ("pytest",),
    "javascript": ("jest", "vitest"),
    "typescript": ("jest", "vitest"),
    "java": ("junit5",),
}
FRAMEWORKS_APP: dict[str, tuple[str, ...]] = {
    "python": ("fastapi",),
    "javascript": ("express",),
    "typescript": ("express",),
    "java": ("spring",),
}
LENGUAJES = tuple(FRAMEWORKS_PRUEBAS)


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


# --- Contratos versionados (EN-17) ---------------------------------------------


def contrato_de_version(familia: str, dato: Any) -> str:
    """Nombre del contrato que corresponde al campo `version` de `dato`.

    Raises:
        KeyError: si la familia no existe.
        ContratoInvalido: si `dato` no es un objeto o su versión no se conoce.
    """
    versiones = VERSIONES[familia]
    version = dato.get("version") if isinstance(dato, dict) else None
    if version not in versiones:
        conocidas = ", ".join(versiones)
        raise ContratoInvalido(
            familia, [f"version: {version!r} no es una versión conocida ({conocidas})"]
        )
    return versiones[version]


def validar_versionado(familia: str, dato: Any) -> Any:
    """Valida `dato` con el schema de su versión y lo devuelve sin cambios.

    Acepta tanto los contratos antiguos (planner v2, generated_test v1) como los
    nuevos con lenguaje y framework, sin convertirlos.

    Raises:
        ContratoInvalido: si la versión no existe o el dato no cumple su schema.
    """
    return validar(contrato_de_version(familia, dato), dato)


def normalizar_planner(dato: dict[str, Any]) -> dict[str, Any]:
    """Devuelve `dato` como `planner_contract.v3`, sin modificar el original.

    Un v2 es siempre Python con pytest (y FastAPI si es un endpoint): se le agregan
    esos campos y no se pierde ningún otro. Un v3 se devuelve validado y copiado.

    Raises:
        ContratoInvalido: si `dato` no cumple su versión.
    """
    validar_versionado(FAMILIA_PLANNER, dato)
    nuevo = copy.deepcopy(dato)
    if nuevo["version"] == "2":
        nuevo.update(version="3", lenguaje="python", framework_pruebas="pytest")
        if nuevo["tipo"] == "endpoint":
            nuevo["framework_app"] = "fastapi"
    return validar(PLANNER_V3, nuevo)


def normalizar_generated_test(dato: dict[str, Any]) -> dict[str, Any]:
    """Devuelve `dato` como `generated_test.v2` (un v1 es Python con pytest).

    Raises:
        ContratoInvalido: si `dato` no cumple su versión.
    """
    validar_versionado(FAMILIA_GENERATED_TEST, dato)
    nuevo = copy.deepcopy(dato)
    if nuevo["version"] == "1":
        nuevo.update(version="2", lenguaje="python", framework_pruebas="pytest")
    return validar(GENERATED_TEST_V2, nuevo)


def _formatear(ruta: Any, mensaje: str) -> str:
    texto = "/".join(str(p) for p in ruta) or "(raíz)"
    return f"{texto}: {mensaje}"


# Validaciones que necesitan contrastar el contrato con registros confiables.
# Se importan al final para que el módulo auxiliar pueda reutilizar las constantes y
# ContratoInvalido sin crear una dependencia circular durante la inicialización.
from qagent.contracts.validacion_semantica import (
    validar_explicacion as validar_explicacion,
)
from qagent.contracts.validacion_semantica import (
    validar_oraculo_js_ts as validar_oraculo_js_ts,
)
