"""#70: el informe y la ejecución explican la mutación de «Repetir + profundizar»."""

from __future__ import annotations

import pytest

from qagent.storage import escribir_corrida
from qagent.storage.registro import NOMBRES_PERFIL, nombre_perfil
from qagent.storage.vista_ejecucion import leer_results, vista_ejecucion
from qagent.storage.vista_reporte import vista_reporte
from tests.storage.test_registro import correr, precios  # noqa: F401 (fixture)

MUTACION_REUTILIZADA = {
    "estado": "ok",
    "puntuacion": 80.0,
    "detectados": 4,
    "sobrevivientes": [{"mutante": "m.x_f__mutmut_1", "linea": 5, "cambio": "a → b"}],
    "mensaje": None,
    "reutilizada": True,
    "run_origen": "20261017-101500-abcd",
}


@pytest.fixture
def results(tmp_path, precios):  # noqa: F811
    tracker, resultado = correr(precios, decisiones=("accept",))
    escribir_corrida(tmp_path, resultado, tracker, precios, "reg_deep")
    datos = leer_results(tmp_path)
    datos["objetivos"][0]["critical"] = True
    return datos


@pytest.mark.parametrize(
    "perfil, nombre",
    [
        ("humo", "Humo"),
        ("std", "Estándar"),
        ("deep", "Estándar + profundizar"),
        ("reg", "Repetir pruebas guardadas"),
        ("reg_deep", "Repetir pruebas guardadas + profundizar"),
        ("rapido", "rapido"),
        (None, "—"),
    ],
)
def test_nombre_de_cada_perfil(perfil, nombre) -> None:
    assert nombre_perfil(perfil) == nombre


def test_los_nombres_son_los_de_la_configuracion() -> None:
    assert set(NOMBRES_PERFIL) == {"humo", "std", "deep", "reg", "reg_deep"}


def test_el_informe_nombra_el_perfil_y_marca_el_resultado_reutilizado(results) -> None:
    objetivo = results["objetivos"][0]
    objetivo["metricas"]["mutation_score"] = 80.0
    objetivo["mutacion"] = MUTACION_REUTILIZADA

    v = vista_reporte(results, None)

    assert v["perfil_nombre"] == "Repetir pruebas guardadas + profundizar"
    mutation = v["funciones"][0]["controles"][4]
    assert mutation["estado"] == "ok"
    assert "1 mutante(s) sobreviviente(s)" in mutation["nota"]
    assert "reutilizado de la corrida 20261017-101500-abcd" in mutation["nota"]


def test_requiere_corrida_nueva_explica_por_que_no_se_muto(results) -> None:
    objetivo = results["objetivos"][0]
    objetivo["decision"] = "requiere_corrida_nueva"
    objetivo["motivo_regresion"] = "huella_distinta"

    [funcion] = vista_reporte(results, None)["funciones"]

    mutation = funcion["controles"][4]
    assert mutation["estado"] == "no_aplica"
    assert mutation["nota"].startswith("Requiere corrida nueva")


def test_repetir_sin_profundizar_no_aplica(results) -> None:
    results["perfil"] = "reg"

    [funcion] = vista_reporte(results, None)["funciones"]

    assert "no usó Profundizar" in funcion["controles"][4]["nota"]


def test_la_ejecucion_promedia_el_score_en_reg_deep(results) -> None:
    results["objetivos"][0]["metricas"]["mutation_score"] = 80.0

    v = vista_ejecucion(results)

    assert v["perfil_nombre"] == "Repetir pruebas guardadas + profundizar"
    ms = v["indicadores"]["mutation_score"]
    assert (ms["disponible"], ms["valor"], ms["cumple"]) == (True, 80.0, True)


def test_la_ejecucion_en_reg_sin_profundizar_no_mide(results) -> None:
    results["perfil"] = "reg"

    ms = vista_ejecucion(results)["indicadores"]["mutation_score"]

    assert ms["disponible"] is False
    assert "no usó Profundizar" in ms["texto"]
