"""#70: las vistas dicen si la prueba se repitió sin IA y por qué requiere corrida nueva."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from qagent.contracts import RUN_LOG, validar
from qagent.storage import escribir_corrida
from qagent.storage.vista_ejecucion import (
    MOTIVOS_REGRESION,
    leer_results,
    vista_ejecucion,
)
from qagent.storage.vista_reporte import vista_reporte
from tests.storage.test_registro import correr, precios  # noqa: F401 (fixture)

REGRESION = Path(__file__).resolve().parents[2] / "src/qagent/orchestrator/regresion.py"


@pytest.fixture
def results(tmp_path, precios):  # noqa: F811
    tracker, resultado = correr(precios, decisiones=("accept",))
    escribir_corrida(tmp_path, resultado, tracker, precios, "reg")
    return leer_results(tmp_path)


def _prueba(results) -> dict:
    return vista_ejecucion(results)["modulos"][0]["pruebas"][0]


def _funcion(results) -> dict:
    return vista_reporte(results, None)["funciones"][0]


def test_una_corrida_normal_no_marca_nada(results) -> None:
    esperado = {
        "reutilizada": False,
        "motivo_regresion": None,
        "texto_motivo_regresion": None,
    }
    for vista in (_prueba(results), _funcion(results)):
        assert {clave: vista[clave] for clave in esperado} == esperado


def test_la_prueba_repetida_sin_ia_se_marca(results) -> None:
    results["objetivos"][0]["reutilizada"] = True

    assert _prueba(results)["reutilizada"] is True
    assert _funcion(results)["reutilizada"] is True


def test_requiere_corrida_nueva_trae_el_motivo_legible(results) -> None:
    objetivo = results["objetivos"][0]
    objetivo["decision"] = "requiere_corrida_nueva"
    objetivo["motivo_regresion"] = "huella_distinta"

    for vista in (_prueba(results), _funcion(results)):
        assert vista["estado"] == "requiere_corrida_nueva"
        assert vista["reutilizada"] is False
        assert vista["motivo_regresion"] == "huella_distinta"
        assert (
            vista["texto_motivo_regresion"]
            == "cambió el código de la función o su prueba"
        )


def test_un_motivo_desconocido_se_muestra_tal_cual(results) -> None:
    results["objetivos"][0]["motivo_regresion"] = "otro_motivo"

    assert _prueba(results)["texto_motivo_regresion"] == "otro_motivo"


def test_cada_motivo_de_la_regresion_tiene_texto() -> None:
    codigo = REGRESION.read_text(encoding="utf-8")
    motivos = set(re.findall(r'motivo(?:_regresion"\])? = "(\w+)"', codigo))

    assert motivos == set(MOTIVOS_REGRESION)


def test_corrida_anterior_sin_los_campos_se_ve_igual(results) -> None:
    for objetivo in results["objetivos"]:
        del objetivo["reutilizada"], objetivo["motivo_regresion"]
    validar(RUN_LOG, results)

    for vista in (_prueba(results), _funcion(results)):
        assert vista["reutilizada"] is False
        assert vista["motivo_regresion"] is None
        assert vista["texto_motivo_regresion"] is None
