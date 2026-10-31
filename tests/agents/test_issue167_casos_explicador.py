"""Casos fijos del banco del Explicador (SPK #167): los que lee la medición con un LLM real.

Solo lee `bench_explicador/casos/`; no llama a ningún LLM ni ejecuta código.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from qagent import contracts
from qagent.agents.explicador import (
    _RUTA_ABSOLUTA,
    BUG,
    ESTANCADA,
    LAUNDERING,
    SIN_VEREDICTO,
    entrada_ia,
    explicar_corrida,
    tipo_de_hallazgo,
)
from qagent.analysis import analizar_proyecto

BANCO = Path(__file__).resolve().parents[2] / "bench_explicador"
CASOS = BANCO / "casos"
NUEVOS = ("total_con_impuesto", "calcular_envio", "convertir_moneda")


@pytest.fixture(scope="module")
def corrida() -> tuple[dict[str, Any], dict[str, Any]]:
    results = json.loads((CASOS / "results.json").read_text(encoding="utf-8"))
    detalle = json.loads((CASOS / "detalle.json").read_text(encoding="utf-8"))
    return results, detalle


def _hallazgos(results: dict[str, Any]) -> dict[str, str]:
    return {
        o["funcion"]: tipo_de_hallazgo(o)
        for o in results["objetivos"]
        if tipo_de_hallazgo(o) is not None
    }


def _textos(dato: Any):
    if isinstance(dato, str):
        yield dato
    elif isinstance(dato, dict):
        for valor in dato.values():
            yield from _textos(valor)
    elif isinstance(dato, list):
        for valor in dato:
            yield from _textos(valor)


def test_el_banco_cubre_los_cuatro_tipos_de_hallazgo(corrida) -> None:
    results, _ = corrida

    assert _hallazgos(results) == {
        "calcular_descuento": BUG,
        "clasificar_edad": BUG,
        "buscar_elemento_mayor": BUG,
        "total_con_impuesto": ESTANCADA,
        "calcular_envio": LAUNDERING,
        "convertir_moneda": SIN_VEREDICTO,
    }


def test_detalle_cumple_su_contrato(corrida) -> None:
    _, detalle = corrida

    contracts.validar(contracts.DETALLE, detalle)


@pytest.mark.parametrize("funcion", NUEVOS)
def test_los_casos_nuevos_traen_mas_de_un_intento(corrida, funcion) -> None:
    results, detalle = corrida
    objetivo = next(o for o in results["objetivos"] if o["funcion"] == funcion)
    detalle_funcion = next(f for f in detalle["funciones"] if f["funcion"] == funcion)

    assert objetivo["metricas"]["iteraciones"] >= 2
    traza = entrada_ia(objetivo, detalle_funcion)["traza"]
    assert len(traza) == len(detalle_funcion["intentos"]) >= 1
    assert all(paso["feedback"] for paso in traza)


def test_el_laundering_lo_detecto_el_reviewer_en_cada_intento_debilitado(
    corrida,
) -> None:
    _, detalle = corrida
    envio = next(f for f in detalle["funciones"] if f["funcion"] == "calcular_envio")

    marcados = [i["intento"] for i in envio["intentos"] if i["laundering_detectado"]]
    assert marcados == [2, 3]
    assert "ASSERTION LAUNDERING" in envio["intentos"][1]["feedback"]


def test_las_plantillas_explican_todos_los_hallazgos_sin_descartes(corrida) -> None:
    results, detalle = corrida

    resultado = explicar_corrida(results, detalle)

    assert resultado.descartadas == []
    contracts.validar_explicaciones(resultado.datos, results_confiables=results)
    assert {e["objetivo"] for e in resultado.datos["explicaciones"]} == set(
        _hallazgos(results)
    )


def test_la_entrada_del_llm_no_lleva_rutas_absolutas(corrida) -> None:
    """La traza del ImportError trae `/work/proyecto/...` a propósito."""
    results, detalle = corrida
    funciones = {f["funcion"]: f for f in detalle["funciones"]}
    assert "/work/proyecto/" in json.dumps(funciones["calcular_envio"])

    for objetivo in results["objetivos"]:
        if tipo_de_hallazgo(objetivo) is None:
            continue
        entrada = entrada_ia(objetivo, funciones[objetivo["funcion"]])
        for texto in _textos(entrada):
            assert not _RUTA_ABSOLUTA.search(texto), (objetivo["funcion"], texto)


def test_los_casos_no_traen_datos_de_la_maquina_donde_se_armaron() -> None:
    for archivo in CASOS.glob("*.json"):
        texto = archivo.read_text(encoding="utf-8")
        assert "C:\\\\" not in texto and "C:/" not in texto, archivo.name
        assert "Users" not in texto and "AppData" not in texto, archivo.name


def test_las_funciones_de_los_casos_existen_en_el_banco() -> None:
    modulos = analizar_proyecto(BANCO)["modulos"]
    modulo = next(m for m in modulos if m["ruta"] == "banco_explicador.py")
    funciones = {f["nombre"]: f for f in modulo["funciones"]}

    for nombre in NUEVOS:
        assert funciones[nombre]["docstring"], nombre


@pytest.mark.parametrize("banco", [BANCO, BANCO.parent / "bench"])
def test_los_docstrings_no_le_dicen_al_llm_que_se_sembro(banco) -> None:
    """El Explicador recibe el docstring: si dijera dónde está el bug, la medición
    no valdría."""
    pistas = re.compile(r"bug|sembrad|hallazgo|laundering|estancad", re.IGNORECASE)
    modulos = analizar_proyecto(banco)["modulos"]
    for modulo in (m for m in modulos if m["ruta"].startswith("banco_")):
        for funcion in modulo["funciones"]:
            docstring = funcion.get("docstring") or ""
            assert not pistas.search(docstring), (modulo["ruta"], funcion["nombre"])
