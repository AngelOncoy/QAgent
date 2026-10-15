"""El Reporte entrega los casos de pytest y el entorno de la corrida (EN-17)."""

from __future__ import annotations

import copy
import json

from qagent import contracts
from qagent.storage.vista_reporte import vista_reporte

EJEMPLOS = contracts.DIR_CONTRATOS / "ejemplos"
RESULTS = json.loads((EJEMPLOS / "run_log.results.json").read_text(encoding="utf-8"))
DETALLE = json.loads((EJEMPLOS / "detalle.json").read_text(encoding="utf-8"))


def _detalle_para(results: dict) -> dict:
    """El detalle de ejemplo apuntando a la primera función de `results`."""
    detalle = copy.deepcopy(DETALLE)
    objetivo = results["objetivos"][0]
    detalle["funciones"][0]["modulo"] = objetivo["modulo"]
    detalle["funciones"][0]["funcion"] = objetivo["funcion"]
    return detalle


def test_la_funcion_trae_sus_intentos_con_los_casos() -> None:
    vista = vista_reporte(RESULTS, _detalle_para(RESULTS))

    funcion = vista["funciones"][0]
    [intento] = funcion["intentos"]
    assert intento["decision"] == "bug_detectado"
    assert intento["feedback"].startswith("assert 12 == 8")
    assert funcion["ejecucion"] is intento["ejecucion"]
    caso = funcion["ejecucion"]["casos"][0]
    assert (caso["archivo"], caso["linea"]) == ("tests/test_generado.py", 4)
    assert (caso["obtenido"], caso["esperado"]) == ("12", "8")


def test_el_reporte_incluye_entorno_y_totales() -> None:
    vista = vista_reporte(RESULTS, _detalle_para(RESULTS))

    assert vista["ejecucion_disponible"] is True
    assert vista["entorno"]["python"] == "3.11.9"
    assert vista["entorno"]["limites"]["timeout_s"] == 60
    assert vista["totales_casos"]["fallaron"] == 1


def test_una_corrida_anterior_al_informe_detallado_no_rompe_la_vista() -> None:
    antiguo = _detalle_para(RESULTS)
    for campo in ("entorno", "totales_casos"):
        del antiguo[campo]
    for intento in antiguo["funciones"][0]["intentos"]:
        for campo in ("feedback", "hash_error", "cobertura", "ejecucion"):
            intento.pop(campo, None)

    vista = vista_reporte(RESULTS, antiguo)

    funcion = vista["funciones"][0]
    assert vista["ejecucion_disponible"] is False
    assert vista["entorno"] is None
    assert funcion["ejecucion"] is None
    assert funcion["intentos"][0]["ejecucion"] is None


def test_sin_detalle_los_intentos_quedan_vacios() -> None:
    vista = vista_reporte(RESULTS, None)

    assert vista["funciones"][0]["intentos"] == []
    assert vista["funciones"][0]["ejecucion"] is None
    assert vista["ejecucion_disponible"] is False
