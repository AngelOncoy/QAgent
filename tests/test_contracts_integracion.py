"""``planner_contract.v3`` de integración interna (#245, ADR-014).

El objetivo es la raíz de una cadena de funciones de Python; las funciones internas
se ejecutan de verdad y el valor esperado sigue saliendo de la firma y la
documentación de la raíz.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from qagent import contracts
from qagent.contracts import DIR_CONTRATOS, PLANNER_V3, errores, es_valido


def _integracion() -> dict[str, Any]:
    ruta = DIR_CONTRATOS / "ejemplos" / "planner_contract.v3.integracion.json"
    return json.loads(ruta.read_text(encoding="utf-8"))


def test_ejemplo_de_integracion_es_valido() -> None:
    assert errores(PLANNER_V3, _integracion()) == []


def test_integracion_es_un_tipo_recomendable() -> None:
    assert "integracion" in contracts.TIPOS_PRUEBA_RECOMENDABLES


@pytest.mark.parametrize(
    "cambios",
    [
        {"lenguaje": "java", "framework_pruebas": "junit5"},
        {"lenguaje": "typescript", "framework_pruebas": "vitest"},
        {"critical": True},
        {"cadena": ["solo_la_raiz"]},
        {"cadena": ["total_del_pedido", "total_del_pedido"]},
        {"cadena": ["total_del_pedido", "no es un nombre"]},
        {"objetivo": "Clase.metodo"},
        {"objetivo": "total_del_pedido"},
        {"manejador": "total_del_pedido"},
        {"framework_app": "fastapi"},
    ],
)
def test_integracion_incompatible(cambios: dict[str, Any]) -> None:
    dato = _integracion()
    dato.update(cambios)
    assert not es_valido(PLANNER_V3, dato)


def test_integracion_exige_la_cadena() -> None:
    dato = _integracion()
    del dato["cadena"]
    assert not es_valido(PLANNER_V3, dato)


@pytest.mark.parametrize("tipo", ["funcion", "endpoint"])
def test_cadena_solo_en_integracion(tipo: str) -> None:
    dato = _integracion()
    dato["tipo"] = tipo
    assert not es_valido(PLANNER_V3, dato)


def test_el_valor_esperado_no_sale_de_ejecutar() -> None:
    dato = _integracion()
    dato["casos"][0]["origen"] = "ejecucion"
    assert not es_valido(PLANNER_V3, dato)
