"""#75: el informe y la ejecución dicen que la corrida fue Humo y no exigen ramas."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from qagent.almacenamiento import AlmacenProyecto, ErrorAlmacen
from qagent.storage import escribir_corrida
from qagent.storage.registro import controles
from qagent.storage.vista_ejecucion import leer_results, vista_ejecucion
from qagent.storage.vista_reporte import vista_reporte
from tests.storage.test_registro import correr, precios  # noqa: F401 (fixture)


def objetivo_con_cobertura(lineas: float, ramas: float | None) -> SimpleNamespace:
    return SimpleNamespace(
        revisiones=[
            {
                "estado_sandbox": "ok",
                "tipo_fallo": None,
                "laundering_detectado": False,
                "feedback": "",
            }
        ],
        codigo="def test_x():\n    assert True\n",
        cobertura={"lineas": lineas, "ramas": ramas},
        critical=False,
        mutacion=None,
    )


@pytest.mark.parametrize(
    "perfil, cumple", [("humo", True), ("std", False), ("deep", False)]
)
def test_en_humo_la_cobertura_de_ramas_no_se_exige(perfil, cumple) -> None:
    objetivo = objetivo_con_cobertura(lineas=90.0, ramas=25.0)

    assert controles(objetivo, {"cobertura_lineas_min": 60}, perfil)["cobertura"] is (
        cumple
    )


def test_en_humo_la_cobertura_de_lineas_si_se_exige() -> None:
    objetivo = objetivo_con_cobertura(lineas=40.0, ramas=None)

    assert controles(objetivo, {"cobertura_lineas_min": 60}, "humo")["cobertura"] is (
        False
    )


@pytest.fixture
def results_humo(tmp_path, precios):  # noqa: F811
    tracker, resultado = correr(precios, decisiones=("accept",))
    escribir_corrida(tmp_path, resultado, tracker, precios, "humo")
    return leer_results(tmp_path)


def test_la_ejecucion_marca_humo_y_el_pass_rate_como_principal(results_humo) -> None:
    v = vista_ejecucion(results_humo)

    assert v["perfil_nombre"] == "Humo"
    assert v["es_humo"] is True
    assert v["indicadores"]["cobertura"]["exige_ramas"] is False


def test_el_informe_marca_humo_y_explica_las_ramas(results_humo) -> None:
    v = vista_reporte(results_humo, None)

    assert v["es_humo"] is True
    assert v["indicadores"]["cobertura"]["exige_ramas"] is False
    cobertura = v["funciones"][0]["controles"][3]
    assert "no se exigen en Humo" in cobertura["etiqueta"]


def test_fuera_de_humo_no_cambia_nada(tmp_path, precios) -> None:  # noqa: F811
    tracker, resultado = correr(precios, decisiones=("accept",))
    escribir_corrida(tmp_path, resultado, tracker, precios, "std")
    results = leer_results(tmp_path)

    assert vista_ejecucion(results)["es_humo"] is False
    assert vista_ejecucion(results)["indicadores"]["cobertura"]["exige_ramas"] is True
    etiqueta = vista_reporte(results, None)["funciones"][0]["controles"][3]["etiqueta"]
    assert "Humo" not in etiqueta


def test_el_perfil_de_una_spec_se_valida(tmp_path) -> None:
    almacen = AlmacenProyecto(tmp_path)
    contrato = {
        "version": "2",
        "modulo": "m.py",
        "huella": "a" * 64,
        "tipo": "funcion",
        "objetivo": "f",
        "firma": "()",
        "critical": False,
        "casos": [
            {"id": "c", "entrada": {}, "valor_esperado": 1, "origen": "docstring"}
        ],
    }

    spec = almacen.guardar_spec(contrato, "20261017-101500-abcd", perfil="humo")
    assert spec["perfil"] == "humo"
    with pytest.raises(ErrorAlmacen):
        almacen.guardar_spec(contrato, "20261017-101500-abcd", perfil="Humo!")
    with pytest.raises(ErrorAlmacen):
        almacen.guardar_plan_modulo(
            "m.py",
            "a" * 64,
            [contrato],
            "20261017-101500-abcd",
            "generado",
            perfiles={"f": 3},
        )
