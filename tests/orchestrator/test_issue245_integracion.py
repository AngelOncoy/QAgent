"""Integración interna en la selección y el plan del orquestador (#245, ADR-014)."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from qagent import contracts
from qagent.lenguajes.python import PythonAdapter
from qagent.orchestrator.orquestador import Orquestador, contrato_de_integracion
from qagent.proyectos.seleccion import SeleccionInvalida, filtrar_modulos


@pytest.fixture
def modulos(tmp_path: Path) -> list[dict[str, Any]]:
    (tmp_path / "a.py").write_text(
        "from b import precio\n\ndef total(p):\n    '''Total.'''\n    return precio(p)\n",
        encoding="utf-8",
    )
    (tmp_path / "b.py").write_text("def precio(p):\n    return p\n", encoding="utf-8")
    return PythonAdapter().analizar(tmp_path)["modulos"]


def _base() -> dict[str, Any]:
    return {
        "version": "3",
        "lenguaje": "python",
        "framework_pruebas": "pytest",
        "modulo": "a.py",
        "huella": "f" * 64,
        "tipo": "funcion",
        "objetivo": "total",
        "firma": "(p) -> int",
        "critical": False,
        "llama_a": ["b.py::precio"],
        "casos": [
            {
                "id": "c1",
                "entrada": {"p": 1},
                "valor_esperado": 1,
                "origen": "docstring",
            }
        ],
    }


def test_el_analisis_ofrece_la_cadena(modulos: list[dict[str, Any]]) -> None:
    a = next(m for m in modulos if m["ruta"] == "a.py")
    assert a["integraciones"][0]["objetivo"] == "integracion_total"
    assert a["integraciones"][0]["cadena"] == ["total", "precio"]
    assert "integraciones" not in next(m for m in modulos if m["ruta"] == "b.py")


def test_sin_seleccion_la_integracion_no_se_activa_sola(
    modulos: list[dict[str, Any]],
) -> None:
    assert all("integraciones" not in m for m in filtrar_modulos(modulos, None))


def test_elegir_solo_la_integracion_deja_la_raiz_como_solo_integracion(
    modulos: list[dict[str, Any]],
) -> None:
    filtrado = filtrar_modulos(modulos, [{"ruta": "a.py", "integraciones": ["total"]}])
    assert filtrado[0]["funciones"][0]["solo_integracion"] is True
    assert filtrado[0]["integraciones"][0]["nombre"] == "total"


def test_integracion_inexistente_es_seleccion_invalida(
    modulos: list[dict[str, Any]],
) -> None:
    with pytest.raises(SeleccionInvalida):
        filtrar_modulos(modulos, [{"ruta": "a.py", "integraciones": ["nada"]}])


def test_el_contrato_derivado_es_valido(modulos: list[dict[str, Any]]) -> None:
    info = next(m for m in modulos if m["ruta"] == "a.py")["integraciones"][0]
    contrato = contrato_de_integracion(_base(), info)
    assert contracts.errores(contracts.PLANNER_V3, contrato) == []
    assert contrato["objetivo"] == "integracion_total"
    assert contrato["critical"] is False
    assert contrato["casos"] == _base()["casos"]


def _orquestador() -> Orquestador:
    orquestador = Orquestador.__new__(Orquestador)
    orquestador._motivos_omision = {}
    orquestador._emitir = lambda *a, **k: None  # type: ignore[method-assign]
    return orquestador


def test_se_deriva_de_la_unitaria_y_la_solo_integracion_no_corre(
    modulos: list[dict[str, Any]],
) -> None:
    filtrado = filtrar_modulos(modulos, [{"ruta": "a.py", "integraciones": ["total"]}])
    plan = _orquestador()._derivar_integraciones(filtrado[0], [copy.deepcopy(_base())])
    assert [(c["tipo"], c["objetivo"]) for c in plan] == [
        ("integracion", "integracion_total")
    ]


def test_sin_contrato_unitario_la_integracion_se_omite_con_motivo(
    modulos: list[dict[str, Any]],
) -> None:
    filtrado = filtrar_modulos(modulos, [{"ruta": "a.py", "integraciones": ["total"]}])
    orquestador = _orquestador()
    assert orquestador._derivar_integraciones(filtrado[0], []) == []
    assert "integracion_total" in orquestador._motivos_omision
