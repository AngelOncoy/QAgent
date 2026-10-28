"""Compatibilidad del adaptador de Python con el flujo actual (EN-17).

El adaptador solo delega: debe dar exactamente lo mismo que los módulos que ya
usan el orquestador, el Planner y el Reviewer. Sin Docker ni red.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qagent import contracts
from qagent.analysis import analizar_proyecto, comparar_aserciones
from qagent.analysis.contexto import PAQUETES_BASE
from qagent.lenguajes import (
    PythonAdapter,
    adaptador_de_contrato,
    adaptador_para,
    detectar_lenguaje,
)
from qagent.sandbox import IMAGEN_BASE
from qagent.sandbox.ejecucion import ARCHIVO_TEST_GENERADO, comando_pytest
from qagent.sandbox.informe_pytest import JUnitInvalido, parsear_junit
from qagent.sandbox.mutacion import SCRIPT_MUTACION, comando_mutacion

MODULO = '''\
"""Precios de la tienda."""

from fastapi import FastAPI

app = FastAPI()


def calcular_descuento(precio: float, porcentaje: float) -> float:
    """Aplica el porcentaje; lanza ValueError si es mayor a 100."""
    if porcentaje > 100:
        raise ValueError("porcentaje inválido")
    return precio * (1 - porcentaje / 100)


@app.get("/items/{item_id}")
def leer(item_id: int) -> dict:
    return {"id": item_id}
'''

JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="2" time="0.5" timestamp="2026-10-27T10:00:00">
<testcase classname="tests.test_precios" name="test_ok" time="0.1"/>
<testcase classname="tests.test_precios" name="test_falla" time="0.2">
<failure message="assert 1 == 2">assert 1 == 2</failure></testcase>
</testsuite></testsuites>"""


@pytest.fixture
def proyecto(tmp_path: Path) -> Path:
    (tmp_path / "tienda").mkdir()
    (tmp_path / "tienda" / "precios.py").write_text(MODULO, encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", "utf-8")
    return tmp_path


def test_analizar_da_lo_mismo_que_el_analizador_actual(proyecto: Path) -> None:
    estructura = PythonAdapter().analizar(proyecto)
    assert estructura.pop("lenguaje") == "python"
    assert estructura == analizar_proyecto(proyecto)


def test_objetivos_de_un_proyecto_python(proyecto: Path) -> None:
    adaptador = PythonAdapter()
    objetivos = adaptador.objetivos(adaptador.analizar(proyecto))
    assert {"modulo": "tienda/precios.py", "tipo": "funcion",
            "objetivo": "calcular_descuento"} in objetivos  # fmt: skip
    assert {"modulo": "tienda/precios.py", "tipo": "endpoint",
            "objetivo": "GET /items/{item_id}"} in objetivos  # fmt: skip
    # La función que atiende la ruta no se prueba dos veces.
    assert not any(o["objetivo"] == "leer" for o in objetivos)


def test_analizar_no_es_una_carpeta(tmp_path: Path) -> None:
    with pytest.raises(NotADirectoryError):
        PythonAdapter().analizar(tmp_path / "no_existe")


def test_detecta_python(proyecto: Path) -> None:
    [deteccion] = detectar_lenguaje(proyecto)
    assert deteccion.lenguaje == "python"
    assert deteccion.marcadores == ("pyproject.toml",)


def test_comando_es_el_de_pytest_actual() -> None:
    assert PythonAdapter().comando_pruebas("tienda.precios") == comando_pytest(
        "tienda.precios"
    )
    assert PythonAdapter().comando_pruebas("m", "pytest") == comando_pytest("m")


def test_comando_con_framework_de_otro_lenguaje() -> None:
    with pytest.raises(ValueError):
        PythonAdapter().comando_pruebas("m", "jest")


def test_entorno_sandbox_actual() -> None:
    entorno = PythonAdapter().entorno_sandbox()
    assert entorno.imagen == IMAGEN_BASE == "qagent-sandbox:base"
    assert entorno.paquetes_base == PAQUETES_BASE
    assert entorno.informe == "junit.xml"


def test_interpretar_resultados_es_parsear_junit() -> None:
    resultado = PythonAdapter().interpretar_resultados(JUNIT)
    assert resultado == parsear_junit(JUNIT).a_dict()
    assert (resultado["total"], resultado["pasaron"], resultado["fallaron"]) == (
        2,
        1,
        1,
    )


def test_interpretar_un_informe_invalido() -> None:
    with pytest.raises(JUnitInvalido):
        PythonAdapter().interpretar_resultados("")


@pytest.mark.parametrize(
    ("codigo", "errores"),
    [
        ("def test_x():\n    assert True\n", 0),
        ("def test_x(:\n", 1),
        ("x = 1\x00", 1),
    ],
)
def test_validar_sintaxis(codigo: str, errores: int) -> None:
    assert len(PythonAdapter().validar_sintaxis(codigo)) == errores


def test_validar_sintaxis_indica_la_linea() -> None:
    [error] = PythonAdapter().validar_sintaxis("x = 1\ndef (:\n")
    assert error.startswith("línea 2:")


def test_comparar_aserciones_es_el_detector_actual() -> None:
    original = "def test_a():\n    assert f(1) == 2\n"
    reparado = "def test_a():\n    assert True\n"
    resultado = PythonAdapter().comparar_aserciones(original, reparado)
    assert resultado.es_laundering is True
    assert resultado == comparar_aserciones(original, reparado)


def test_un_contrato_v2_de_las_specs_guardadas_usa_el_adaptador_de_python() -> None:
    ruta = contracts.DIR_CONTRATOS / "ejemplos"
    for archivo in ("planner_contract.v2.json", "planner_contract.endpoint.json"):
        contrato = json.loads((ruta / archivo).read_text(encoding="utf-8"))
        assert isinstance(adaptador_de_contrato(contrato), PythonAdapter)
    assert isinstance(adaptador_para("python"), PythonAdapter)


def test_archivo_de_prueba_es_el_que_escribe_el_reviewer() -> None:
    assert PythonAdapter().archivo_de_prueba("calcular_descuento") == "test_generado.py"
    assert ARCHIVO_TEST_GENERADO == "test_generado.py"


def test_leer_cobertura_lee_coverage_json(tmp_path: Path) -> None:
    informe = {"totals": {"percent_covered": 80.0}, "files": {}}
    (tmp_path / "coverage.json").write_text(json.dumps(informe), encoding="utf-8")
    assert PythonAdapter().leer_cobertura(tmp_path) == informe


@pytest.mark.parametrize("contenido", [None, "{no es json"])
def test_leer_cobertura_sin_informe_valido(
    tmp_path: Path, contenido: str | None
) -> None:
    if contenido is not None:
        (tmp_path / "coverage.json").write_text(contenido, encoding="utf-8")
    assert PythonAdapter().leer_cobertura(tmp_path) is None


def test_comando_mutacion_es_el_del_sandbox() -> None:
    resultado = PythonAdapter().comando_mutacion("pkg/calc.py", ["f", "g"])
    comando, entorno = comando_mutacion("pkg/calc.py", ["f", "g"])
    assert (resultado.comando, resultado.entorno) == (comando, entorno)
    assert resultado.comando == ["python", "-c", SCRIPT_MUTACION]
    assert resultado.entorno == {
        "PYTHONPATH": "",
        "QAGENT_MUT_ARCHIVO": "pkg/calc.py",
        "QAGENT_MUT_FUNCIONES": '["f", "g"]',
    }
