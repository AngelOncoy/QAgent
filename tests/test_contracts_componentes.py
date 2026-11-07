"""``planner_contract.v3`` de componentes React (#171, CA2).

El caso de un componente es un render con props y, si hace falta, interacciones; el
resultado esperado se busca por rol o texto y sale de los tipos o del JSDoc.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from qagent.contracts import DIR_CONTRATOS, PLANNER_V3, errores, es_valido


def _react() -> dict[str, Any]:
    ruta = DIR_CONTRATOS / "ejemplos" / "planner_contract.v3.react.json"
    return json.loads(ruta.read_text(encoding="utf-8"))


def test_ejemplo_react_es_valido() -> None:
    assert errores(PLANNER_V3, _react()) == []


def test_javascript_tambien_admite_componentes() -> None:
    dato = _react()
    dato["lenguaje"] = "javascript"
    dato["modulo"] = "src/Boton.jsx"
    assert es_valido(PLANNER_V3, dato)


@pytest.mark.parametrize(
    "cambios",
    [
        {"framework_app": "express"},
        {"lenguaje": "python", "framework_pruebas": "pytest"},
        {"lenguaje": "java", "framework_pruebas": "junit5"},
        {"framework_pruebas": "jest"},
        {"critical": True},
        {"objetivo": "boton"},
        {"manejador": "Boton"},
    ],
)
def test_componente_incompatible(cambios: dict[str, Any]) -> None:
    dato = _react()
    dato.update(cambios)
    assert not es_valido(PLANNER_V3, dato)


def test_componente_exige_framework_app() -> None:
    dato = _react()
    del dato["framework_app"]
    assert not es_valido(PLANNER_V3, dato)


@pytest.mark.parametrize("tipo", ["funcion", "endpoint"])
def test_react_solo_en_componentes(tipo: str) -> None:
    funcion = json.loads(
        (DIR_CONTRATOS / "ejemplos" / "planner_contract.v3.typescript.json").read_text(
            encoding="utf-8"
        )
    )
    funcion["framework_app"] = "react"
    funcion["tipo"] = tipo
    assert not es_valido(PLANNER_V3, funcion)


def _con_caso(**caso: Any) -> dict[str, Any]:
    dato = _react()
    base = copy.deepcopy(dato["casos"][0])
    base.update(caso)
    dato["casos"] = [base]
    return dato


@pytest.mark.parametrize(
    "caso",
    [
        {"excepcion": "TypeError"},
        {"origen": "ejecucion"},
        {"origen": "status_code"},
        {"valor_esperado": {"visible": [{"texto": "Pagar"}]}},
        {"valor_esperado": {"renderiza": False}},
        {"valor_esperado": {"renderiza": True, "visible": [{"selector": ".btn"}]}},
        {
            "valor_esperado": {
                "renderiza": True,
                "visible": [{"texto": "a", "rol": "b"}],
            }
        },
        {
            "valor_esperado": {
                "renderiza": True,
                "visible": [{"texto": "a", "nombre": "b"}],
            }
        },
        {
            "valor_esperado": {
                "renderiza": True,
                "llamadas": [{"prop": "pulsar", "veces": 1}],
            }
        },
        {"entrada": {"etiqueta": "Pagar"}},
        {
            "entrada": {
                "props": {},
                "interacciones": [
                    {"accion": "click", "elemento": {"texto": "x"}, "valor": "y"}
                ],
            }
        },
        {
            "entrada": {
                "props": {},
                "interacciones": [
                    {"accion": "escribir", "elemento": {"rol": "textbox"}}
                ],
            }
        },
        {
            "entrada": {
                "props": {},
                "interacciones": [
                    {"accion": "arrastrar", "elemento": {"rol": "button"}}
                ],
            }
        },
    ],
)
def test_caso_de_componente_invalido(caso: dict[str, Any]) -> None:
    assert not es_valido(PLANNER_V3, _con_caso(**caso))


def test_caso_que_escribe_y_espera_ausencia() -> None:
    dato = _con_caso(
        entrada={
            "props": {"onBuscar": {"$funcion": True}},
            "interacciones": [
                {"accion": "escribir", "elemento": {"rol": "textbox"}, "valor": "pan"},
                {"accion": "enviar", "elemento": {"rol": "form"}},
            ],
        },
        valor_esperado={
            "renderiza": True,
            "ausente": [{"texto": "Sin resultados"}],
            "llamadas": [{"prop": "onBuscar", "veces": 1, "argumentos": ["pan"]}],
        },
    )
    assert errores(PLANNER_V3, dato) == []
