"""Pruebas de los contratos JSON entre agentes (EN-01). Sin red y con 0 tokens."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from qagent.contracts import (
    CONTRATOS,
    DETALLE,
    DIR_CONTRATOS,
    GENERATED_TEST,
    GENERATED_TEST_V2,
    PLANNER,
    PLANNER_V3,
    REVIEW_RESULT,
    RUN_LOG,
    ContratoInvalido,
    cargar_schema,
    es_valido,
    validar,
)
from qagent.llm import FakeLLMClient


def ejemplo(nombre: str) -> dict[str, Any]:
    """Copia del ejemplo válido de `contracts/ejemplos/`."""
    ruta = DIR_CONTRATOS / "ejemplos" / f"{nombre}.json"
    return json.loads(ruta.read_text(encoding="utf-8"))


# --- Schemas y ejemplos ---------------------------------------------------------


@pytest.mark.parametrize("nombre", CONTRATOS)
def test_schema_es_json_schema_valido(nombre: str) -> None:
    Draft202012Validator.check_schema(cargar_schema(nombre))


# (contrato, archivo de contracts/ejemplos/): run_log tiene un ejemplo por tipo.
EJEMPLOS = [
    (PLANNER, PLANNER),
    (PLANNER, "planner_contract.endpoint"),
    (GENERATED_TEST, GENERATED_TEST),
    (REVIEW_RESULT, REVIEW_RESULT),
    (RUN_LOG, "run_log.log"),
    (RUN_LOG, "run_log.results"),
    (DETALLE, DETALLE),
    (PLANNER_V3, PLANNER_V3),
    (PLANNER_V3, "planner_contract.v3.typescript"),
    (PLANNER_V3, "planner_contract.v3.java"),
    (GENERATED_TEST_V2, GENERATED_TEST_V2),
    (GENERATED_TEST_V2, "generated_test.v2.java"),
]


def test_cada_contrato_tiene_ejemplo() -> None:
    assert {contrato for contrato, _ in EJEMPLOS} == set(CONTRATOS)


@pytest.mark.parametrize(("nombre", "archivo"), EJEMPLOS)
def test_ejemplo_cumple_su_contrato(nombre: str, archivo: str) -> None:
    dato = ejemplo(archivo)
    assert validar(nombre, dato) is dato


def test_contrato_desconocido() -> None:
    with pytest.raises(KeyError):
        validar("no_existe", {})


# --- Errores comunes ------------------------------------------------------------


@pytest.mark.parametrize(
    ("nombre", "campo"),
    [
        (PLANNER, "casos"),
        (PLANNER, "huella"),
        (GENERATED_TEST, "codigo"),
        (REVIEW_RESULT, "decision"),
    ],
)
def test_falta_campo_obligatorio(nombre: str, campo: str) -> None:
    dato = ejemplo(nombre)
    del dato[campo]
    with pytest.raises(ContratoInvalido) as error:
        validar(nombre, dato)
    assert error.value.contrato == nombre
    assert any(campo in e for e in error.value.errores)


def test_campo_extra_se_rechaza() -> None:
    dato = ejemplo(GENERATED_TEST)
    dato["comentario"] = "no está en el contrato"
    assert not es_valido(GENERATED_TEST, dato)


@pytest.mark.parametrize(
    ("nombre", "campo", "valor"),
    [
        (PLANNER, "tipo", "clase"),
        (REVIEW_RESULT, "decision", "aprobar"),
        (REVIEW_RESULT, "estado_sandbox", "colgado"),
    ],
)
def test_valor_fuera_del_enum(nombre: str, campo: str, valor: str) -> None:
    dato = ejemplo(nombre)
    dato[campo] = valor
    assert not es_valido(nombre, dato)


# --- planner_contract.v2 --------------------------------------------------------


def test_oraculo_no_puede_salir_de_ejecutar_el_codigo() -> None:
    dato = ejemplo(PLANNER)
    dato["casos"][0]["origen"] = "ejecucion"
    with pytest.raises(ContratoInvalido) as error:
        validar(PLANNER, dato)
    assert any(e.startswith("casos/0/origen") for e in error.value.errores)


def test_caso_sin_valor_esperado_ni_excepcion() -> None:
    dato = ejemplo(PLANNER)
    del dato["casos"][0]["valor_esperado"]
    assert not es_valido(PLANNER, dato)


def test_plan_sin_casos() -> None:
    dato = ejemplo(PLANNER)
    dato["casos"] = []
    assert not es_valido(PLANNER, dato)


def test_contrato_de_endpoint() -> None:
    dato = ejemplo(PLANNER)
    dato.update(
        tipo="endpoint",
        objetivo="GET /items/{item_id}",
        manejador="leer_item",
        aplicacion="app",
        dependencias=[],
        firma="(item_id: int)",
    )
    dato["casos"] = [
        {
            "id": "item_existe",
            "entrada": {"metodo": "GET", "ruta": "/items/1"},
            "valor_esperado": {"status_code": 200},
            "origen": "status_code",
        }
    ]
    assert es_valido(PLANNER, dato)


def test_objetivo_debe_corresponder_al_tipo() -> None:
    funcion_con_ruta = ejemplo(PLANNER)
    funcion_con_ruta["objetivo"] = "GET /items"
    endpoint_con_nombre = ejemplo(PLANNER)
    endpoint_con_nombre["tipo"] = "endpoint"
    assert not es_valido(PLANNER, funcion_con_ruta)
    assert not es_valido(PLANNER, endpoint_con_nombre)


# --- generated_test -------------------------------------------------------------


@pytest.mark.parametrize("intento", [0, 4])
def test_intento_fuera_de_rango(intento: int) -> None:
    dato = ejemplo(GENERATED_TEST)
    dato["intento"] = intento
    assert not es_valido(GENERATED_TEST, dato)


# --- review_result: reglas contra Assertion Laundering --------------------------


def veredicto(**cambios: Any) -> dict[str, Any]:
    dato = copy.deepcopy(ejemplo(REVIEW_RESULT))
    dato.update(cambios)
    return dato


def test_retry_valido() -> None:
    dato = veredicto(
        estado_sandbox="fallo",
        tipo_fallo="error_test",
        hash_error="3fa2b1c9",
        decision="retry",
        feedback="ImportError: falta importar pytest",
    )
    assert es_valido(REVIEW_RESULT, dato)


def test_retry_sin_feedback() -> None:
    dato = veredicto(
        estado_sandbox="fallo", tipo_fallo="error_test", decision="retry", feedback=""
    )
    assert not es_valido(REVIEW_RESULT, dato)


def test_retry_en_el_ultimo_intento_debe_ser_stalled() -> None:
    dato = veredicto(
        intento=3,
        estado_sandbox="fallo",
        tipo_fallo="error_test",
        decision="retry",
        feedback="sigue fallando",
    )
    assert not es_valido(REVIEW_RESULT, dato)
    dato["decision"] = "stalled"
    assert es_valido(REVIEW_RESULT, dato)


def test_no_se_reintenta_un_bug_del_codigo() -> None:
    dato = veredicto(
        estado_sandbox="fallo",
        tipo_fallo="bug_codigo",
        decision="retry",
        feedback="assert 75.0 == 80.0",
    )
    assert not es_valido(REVIEW_RESULT, dato)
    dato["decision"] = "bug_detectado"
    assert es_valido(REVIEW_RESULT, dato)


def test_bug_detectado_exige_tipo_bug_codigo() -> None:
    dato = veredicto(
        estado_sandbox="fallo",
        tipo_fallo="error_test",
        decision="bug_detectado",
        feedback="x",
    )
    assert not es_valido(REVIEW_RESULT, dato)


def test_no_se_acepta_un_test_con_laundering() -> None:
    assert not es_valido(REVIEW_RESULT, veredicto(laundering_detectado=True))


@pytest.mark.parametrize("estado", ["fallo", "timeout", "oom", "error"])
def test_no_se_acepta_si_el_sandbox_no_paso(estado: str) -> None:
    assert not es_valido(REVIEW_RESULT, veredicto(estado_sandbox=estado))


def test_cobertura_nula_si_no_hubo_coverage() -> None:
    dato = veredicto(
        estado_sandbox="timeout", cobertura=None, decision="stalled", feedback="timeout"
    )
    assert es_valido(REVIEW_RESULT, dato)


# --- IA simulada coherente con los contratos -----------------------------------


def test_respuesta_simulada_del_planner_cumple_el_contrato() -> None:
    plan = json.loads(FakeLLMClient().generar("plan", rol="planner").contenido)
    assert isinstance(plan, list) and plan
    for contrato in plan:
        validar(PLANNER, contrato)


def test_respuesta_simulada_del_reviewer_cumple_el_contrato() -> None:
    respuesta = FakeLLMClient().generar("revisar", rol="reviewer").contenido
    validar(REVIEW_RESULT, json.loads(respuesta))


# --- Contrato de endpoints (EN-14) ----------------------------------------------


def endpoint() -> dict[str, Any]:
    return ejemplo("planner_contract.endpoint")


def test_endpoint_exige_manejador() -> None:
    dato = endpoint()
    del dato["manejador"]
    assert not es_valido(PLANNER, dato)


@pytest.mark.parametrize("campo", ["aplicacion", "dependencias"])
def test_endpoint_exige_datos_para_testclient(campo: str) -> None:
    dato = endpoint()
    del dato[campo]
    assert not es_valido(PLANNER, dato)


def test_dependencia_de_endpoint_exige_funcion_y_reemplazo() -> None:
    dato = endpoint()
    del dato["dependencias"][0]["reemplazo"]
    assert not es_valido(PLANNER, dato)


def test_funcion_no_necesita_manejador() -> None:
    dato = ejemplo(PLANNER)
    assert "manejador" not in dato
    assert es_valido(PLANNER, dato)


@pytest.mark.parametrize(
    "cambio",
    [
        lambda caso: caso.update(excepcion="ValueError"),
        lambda caso: caso["entrada"].pop("ruta"),
        lambda caso: caso["entrada"].update(metodo="HEAD"),
        lambda caso: caso["entrada"].update(ruta="items"),
        lambda caso: caso["entrada"].update(cuerpo={}),
        lambda caso: caso.update(valor_esperado=201),
        lambda caso: caso["valor_esperado"].pop("status_code"),
        lambda caso: caso["valor_esperado"].update(status_code=99),
        lambda caso: caso["valor_esperado"].update(json={"nombre": "lapiz"}),
    ],
    ids=[
        "excepcion",
        "sin_ruta",
        "metodo_no_soportado",
        "ruta_sin_barra",
        "campo_desconocido",
        "valor_esperado_no_objeto",
        "sin_status",
        "status_invalido",
        "json_y_json_contiene",
    ],
)
def test_caso_de_endpoint_invalido(cambio) -> None:
    dato = endpoint()
    cambio(dato["casos"][0])
    assert not es_valido(PLANNER, dato)


def test_caso_de_funcion_no_sirve_para_un_endpoint() -> None:
    dato = endpoint()
    dato["casos"] = ejemplo(PLANNER)["casos"]
    assert not es_valido(PLANNER, dato)


# --- EN-09: mutation testing en results.json -------------------------------------

MUTACION = {
    "estado": "ok",
    "puntuacion": 75.0,
    "detectados": 3,
    "sobrevivientes": [
        {"mutante": "calc.x_f__mutmut_2", "linea": 12, "cambio": "x > 1 → x >= 1"}
    ],
    "mensaje": None,
}


def resultados_con_mutacion(mutacion: dict[str, Any]) -> dict[str, Any]:
    dato = ejemplo("run_log.results")
    objetivo = dato["objetivos"][0]
    objetivo["critical"] = True
    objetivo["metricas"]["mutation_score"] = mutacion.get("puntuacion")
    objetivo["mutacion"] = mutacion
    return dato


def test_results_acepta_el_detalle_de_mutacion() -> None:
    assert es_valido(RUN_LOG, resultados_con_mutacion(copy.deepcopy(MUTACION)))


def test_results_acepta_mutacion_sin_puntuacion() -> None:
    mutacion = {
        **MUTACION,
        "estado": "tiempo_agotado",
        "puntuacion": None,
        "detectados": 0,
        "sobrevivientes": [],
        "mensaje": "Se agotó el tiempo máximo de la mutación (120 s).",
    }
    assert es_valido(RUN_LOG, resultados_con_mutacion(mutacion))


@pytest.mark.parametrize(
    "cambio",
    [
        {"estado": "inventado"},
        {"puntuacion": 120},
        {"detectados": -1},
        {"sobrevivientes": [{"mutante": "m", "linea": 0, "cambio": ""}]},
        {"sobrevivientes": [{"mutante": "m", "cambio": ""}]},
    ],
)
def test_results_rechaza_mutacion_invalida(cambio) -> None:
    assert not es_valido(RUN_LOG, resultados_con_mutacion({**MUTACION, **cambio}))


def test_results_rechaza_mutacion_sin_campos_obligatorios() -> None:
    mutacion = copy.deepcopy(MUTACION)
    del mutacion["sobrevivientes"]
    assert not es_valido(RUN_LOG, resultados_con_mutacion(mutacion))


def test_results_acepta_mutacion_reutilizada() -> None:
    """#70: el resultado puede venir de .qagent/mutacion/ con su corrida de origen."""
    mutacion = {**MUTACION, "reutilizada": True, "run_origen": "20261017-101500-abcd"}
    assert es_valido(RUN_LOG, resultados_con_mutacion(mutacion))


@pytest.mark.parametrize(
    "cambio", [{"reutilizada": "si"}, {"run_origen": "ayer"}, {"run_origen": None}]
)
def test_results_rechaza_reutilizacion_invalida(cambio) -> None:
    assert not es_valido(RUN_LOG, resultados_con_mutacion({**MUTACION, **cambio}))
