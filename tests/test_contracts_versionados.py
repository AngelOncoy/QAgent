"""Contratos versionados con lenguaje y framework (EN-17). Sin red y con 0 tokens.

Comprueba que los contratos antiguos (planner v2, generated_test v1) siguen siendo
válidos, que los nuevos (planner v3, generated_test v2) representan lenguaje y
framework, que se rechazan las estructuras inválidas y que un v2 se convierte a v3
sin perder datos.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from qagent import contracts
from qagent.contracts import (
    DIR_CONTRATOS,
    FAMILIA_GENERATED_TEST,
    FAMILIA_PLANNER,
    FRAMEWORKS_APP,
    FRAMEWORKS_PRUEBAS,
    GENERATED_TEST,
    GENERATED_TEST_V2,
    LENGUAJES,
    PLANNER,
    PLANNER_V3,
    ContratoInvalido,
    cargar_schema,
    contrato_de_version,
    es_valido,
    normalizar_generated_test,
    normalizar_planner,
    validar_versionado,
)


def ejemplo(nombre: str) -> dict[str, Any]:
    ruta = DIR_CONTRATOS / "ejemplos" / f"{nombre}.json"
    return json.loads(ruta.read_text(encoding="utf-8"))


PLANES_V2 = ["planner_contract.v2", "planner_contract.endpoint"]
PLANES_V3 = [
    "planner_contract.v3",
    "planner_contract.v3.typescript",
    "planner_contract.v3.java",
]
TESTS_V2 = ["generated_test.v2", "generated_test.v2.java"]


# --- Coherencia entre schemas y constantes ----------------------------------------


@pytest.mark.parametrize("nombre", [PLANNER_V3, GENERATED_TEST_V2])
def test_enum_de_lenguajes_coincide_con_las_constantes(nombre: str) -> None:
    propiedades = cargar_schema(nombre)["properties"]
    assert tuple(propiedades["lenguaje"]["enum"]) == LENGUAJES
    todos = {f for fs in FRAMEWORKS_PRUEBAS.values() for f in fs}
    assert set(propiedades["framework_pruebas"]["enum"]) == todos


def test_enum_de_frameworks_app_coincide_con_las_constantes() -> None:
    propiedades = cargar_schema(PLANNER_V3)["properties"]
    todos = {f for fs in FRAMEWORKS_APP.values() for f in fs}
    assert set(propiedades["framework_app"]["enum"]) == todos


def test_los_schemas_antiguos_no_cambian_de_version() -> None:
    assert cargar_schema(PLANNER)["properties"]["version"] == {"const": "2"}
    assert cargar_schema(GENERATED_TEST)["properties"]["version"] == {"const": "1"}
    assert "lenguaje" not in cargar_schema(PLANNER)["properties"]


# --- Validación de contratos antiguos y nuevos ------------------------------------


@pytest.mark.parametrize("archivo", PLANES_V2)
def test_planner_v2_sigue_siendo_valido(archivo: str) -> None:
    dato = ejemplo(archivo)
    assert contrato_de_version(FAMILIA_PLANNER, dato) == PLANNER
    assert validar_versionado(FAMILIA_PLANNER, dato) is dato


def test_generated_test_v1_sigue_siendo_valido() -> None:
    dato = ejemplo("generated_test")
    assert contrato_de_version(FAMILIA_GENERATED_TEST, dato) == GENERATED_TEST
    assert validar_versionado(FAMILIA_GENERATED_TEST, dato) is dato


@pytest.mark.parametrize("archivo", PLANES_V3)
def test_planner_v3_valido(archivo: str) -> None:
    dato = ejemplo(archivo)
    assert contrato_de_version(FAMILIA_PLANNER, dato) == PLANNER_V3
    assert validar_versionado(FAMILIA_PLANNER, dato) is dato


@pytest.mark.parametrize("archivo", TESTS_V2)
def test_generated_test_v2_valido(archivo: str) -> None:
    dato = ejemplo(archivo)
    assert validar_versionado(FAMILIA_GENERATED_TEST, dato) is dato


@pytest.mark.parametrize(
    ("lenguaje", "framework"),
    [(lenguaje, f) for lenguaje, fs in FRAMEWORKS_PRUEBAS.items() for f in fs],
)
def test_cada_combinacion_valida_de_lenguaje_y_framework(
    lenguaje: str, framework: str
) -> None:
    dato = ejemplo("generated_test.v2")
    dato.update(lenguaje=lenguaje, framework_pruebas=framework)
    assert es_valido(GENERATED_TEST_V2, dato)


# --- Rechazo de estructuras inválidas ---------------------------------------------


@pytest.mark.parametrize("version", [None, "1", "4", 3])
def test_version_desconocida_del_planner(version: Any) -> None:
    dato = ejemplo("planner_contract.v3")
    dato["version"] = version
    with pytest.raises(ContratoInvalido) as error:
        validar_versionado(FAMILIA_PLANNER, dato)
    assert error.value.errores[0].startswith("version:")


@pytest.mark.parametrize("dato", [None, [], "texto", {}])
def test_dato_que_no_es_contrato(dato: Any) -> None:
    with pytest.raises(ContratoInvalido):
        validar_versionado(FAMILIA_PLANNER, dato)


def test_familia_desconocida() -> None:
    with pytest.raises(KeyError):
        validar_versionado("no_existe", {"version": "1"})


@pytest.mark.parametrize("campo", ["lenguaje", "framework_pruebas"])
def test_planner_v3_exige_lenguaje_y_framework(campo: str) -> None:
    dato = ejemplo("planner_contract.v3")
    del dato[campo]
    assert not es_valido(PLANNER_V3, dato)


@pytest.mark.parametrize(
    ("archivo", "cambios"),
    [
        ("planner_contract.v3", {"lenguaje": "cobol"}),
        ("planner_contract.v3", {"framework_pruebas": "jest"}),
        ("planner_contract.v3.typescript", {"framework_pruebas": "pytest"}),
        ("planner_contract.v3.java", {"framework_pruebas": "jest"}),
        ("planner_contract.v3.java", {"framework_app": "express"}),
        ("planner_contract.v3.java", {"framework_app": "fastapi"}),
    ],
)
def test_lenguaje_y_framework_incompatibles(
    archivo: str, cambios: dict[str, str]
) -> None:
    dato = ejemplo(archivo)
    dato.update(cambios)
    assert not es_valido(PLANNER_V3, dato)


def test_generated_test_v2_con_framework_de_otro_lenguaje() -> None:
    dato = ejemplo("generated_test.v2.java")
    dato["framework_pruebas"] = "pytest"
    assert not es_valido(GENERATED_TEST_V2, dato)


def test_endpoint_v3_exige_framework_app() -> None:
    dato = ejemplo("planner_contract.v3.java")
    del dato["framework_app"]
    assert not es_valido(PLANNER_V3, dato)


def test_endpoint_fastapi_v3_exige_dependencias() -> None:
    dato = normalizar_planner(ejemplo("planner_contract.endpoint"))
    del dato["dependencias"]
    assert not es_valido(PLANNER_V3, dato)


def test_endpoint_spring_no_exige_dependencias() -> None:
    dato = ejemplo("planner_contract.v3.java")
    del dato["dependencias"]
    assert es_valido(PLANNER_V3, dato)


def test_funcion_python_v3_no_admite_nombre_calificado() -> None:
    dato = ejemplo("planner_contract.v3")
    dato["objetivo"] = "Precios.calcular_descuento"
    assert not es_valido(PLANNER_V3, dato)


def test_funcion_java_v3_admite_clase_y_metodo() -> None:
    dato = ejemplo("planner_contract.v3.typescript")
    dato.update(lenguaje="java", framework_pruebas="junit5")
    dato["objetivo"] = "Precios.calcularDescuento"
    assert es_valido(PLANNER_V3, dato)


def test_v3_conserva_el_oraculo_sin_ejecucion() -> None:
    dato = ejemplo("planner_contract.v3.typescript")
    dato["casos"][0]["origen"] = "ejecucion"
    assert not es_valido(PLANNER_V3, dato)


@pytest.mark.parametrize("archivo", ["../fuera.py", "carpeta/test_x.py", ""])
def test_archivo_del_test_sin_carpetas(archivo: str) -> None:
    dato = ejemplo("generated_test.v2")
    dato["archivo"] = archivo
    assert not es_valido(GENERATED_TEST_V2, dato)


def test_campo_extra_en_v3_se_rechaza() -> None:
    dato = ejemplo("planner_contract.v3")
    dato["runner"] = "otro"
    assert not es_valido(PLANNER_V3, dato)


# --- Compatibilidad: de v2 a v3 ----------------------------------------------------


@pytest.mark.parametrize("archivo", PLANES_V2)
def test_normalizar_planner_v2_conserva_todos_los_campos(archivo: str) -> None:
    original = ejemplo(archivo)
    copia = copy.deepcopy(original)
    nuevo = normalizar_planner(original)

    assert original == copia, "no debe modificar el contrato recibido"
    assert nuevo["version"] == "3"
    assert nuevo["lenguaje"] == "python"
    assert nuevo["framework_pruebas"] == "pytest"
    extras = {"version", "lenguaje", "framework_pruebas", "framework_app"}
    assert {k: v for k, v in nuevo.items() if k not in extras} == {
        k: v for k, v in original.items() if k != "version"
    }


def test_normalizar_endpoint_v2_agrega_fastapi() -> None:
    endpoint = normalizar_planner(ejemplo("planner_contract.endpoint"))
    assert endpoint["framework_app"] == "fastapi"
    assert "framework_app" not in normalizar_planner(ejemplo("planner_contract.v2"))


@pytest.mark.parametrize("archivo", PLANES_V3)
def test_normalizar_planner_v3_devuelve_una_copia_igual(archivo: str) -> None:
    original = ejemplo(archivo)
    nuevo = normalizar_planner(original)
    assert nuevo == original
    assert nuevo is not original


def test_normalizar_planner_rechaza_un_v2_invalido() -> None:
    dato = ejemplo("planner_contract.v2")
    dato["casos"] = []
    with pytest.raises(ContratoInvalido):
        normalizar_planner(dato)


def test_normalizar_generated_test_v1() -> None:
    original = ejemplo("generated_test")
    nuevo = normalizar_generated_test(original)
    assert nuevo == {
        **original,
        "version": "2",
        "lenguaje": "python",
        "framework_pruebas": "pytest",
    }
    assert original["version"] == "1"


def test_el_flujo_de_python_sigue_usando_v2() -> None:
    """Las specs guardadas y el Planner validan con v2; EN-17 no las migra."""
    assert contracts.PLANNER == "planner_contract.v2"
    assert contracts.GENERATED_TEST == "generated_test"
