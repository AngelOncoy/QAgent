"""Reporte de auditoría (HU-21): cifras de results.json, textos de detalle.json."""

from __future__ import annotations

import copy
import json

import pytest

from qagent.contracts import RUN_LOG, validar
from qagent.storage import escribir_corrida
from qagent.storage.vista_ejecucion import leer_results
from qagent.storage.vista_reporte import leer_detalle, vista_reporte
from tests.storage.test_registro import correr, precios  # noqa: F401 (fixture)

METAS = {
    "pass_rate_min": 70,
    "cobertura_lineas_min": 60,
    "iteraciones_promedio_max": 2.0,
    "tope_por_corrida_usd": 1.0,
}


@pytest.fixture
def corrida(tmp_path, precios):  # noqa: F811
    """Corrida aceptada en el segundo intento, escrita en .qagent/runs/."""
    tracker, resultado = correr(precios, decisiones=("retry", "accept"))
    rutas = escribir_corrida(
        tmp_path, resultado, tracker, precios, "deep", metas=METAS, rama="develop"
    )
    return tmp_path, rutas


def reporte(raiz):
    results = leer_results(raiz)
    return results, vista_reporte(results, leer_detalle(raiz, results["run_id"]))


def test_cabecera_con_numero_fecha_perfil_rama_y_modelos(corrida) -> None:
    raiz, rutas = corrida
    results, v = reporte(raiz)

    assert v["run_id"] == rutas.run_id
    assert v["fecha"] == results["fecha"]
    assert (v["perfil"], v["rama"]) == ("deep", "develop")
    assert v["total_funciones"] == results["resumen"]["total_funciones"]
    assert set(v["modelos"]) == {"planner", "generator", "reviewer"}
    assert (
        v["modelos"]["reviewer"]["modelo"] == results["modelos"]["reviewer"]["modelo"]
    )


def test_los_indicadores_coinciden_con_results_json(corrida) -> None:
    """Criterio 5: las cifras del Reporte son las del archivo."""
    raiz, _ = corrida
    results, v = reporte(raiz)
    resumen, k = results["resumen"], v["indicadores"]

    assert k["pass_rate"]["valor"] == resumen["pass_rate"]
    assert k["cobertura"]["lineas"] == resumen["cobertura_lineas_promedio"]
    assert k["cobertura"]["ramas"] == resumen["cobertura_ramas_promedio"]
    assert k["costo"]["usd"] == resumen["costo_total_usd"]
    assert k["balance"]["ok"] + k["balance"]["alertas"] == resumen["total_funciones"]
    for funcion, objetivo in zip(v["funciones"], results["objetivos"]):
        assert funcion["cobertura_lineas"] == objetivo["metricas"]["cobertura_lineas"]


def test_cinco_controles_por_funcion(corrida) -> None:
    raiz, _ = corrida
    results, v = reporte(raiz)

    [funcion] = v["funciones"]
    controles = {c["clave"]: c["estado"] for c in funcion["controles"]}
    assert list(controles) == [
        "sintaxis",
        "sandbox",
        "aserciones",
        "cobertura",
        "mutation",
    ]
    assert controles == {
        "sintaxis": "ok",
        "sandbox": "ok",
        "aserciones": "ok",
        "cobertura": "ok",  # el Reviewer simulado reporta 100 % / 100 %
        "mutation": "no_aplica",  # la función no es crítica
    }
    assert results["objetivos"][0]["controles"]["sintaxis"] is True
    assert funcion["verde"] is True


def test_las_tres_pestanas_tienen_contrato_test_y_traza(corrida) -> None:
    raiz, rutas = corrida
    _, v = reporte(raiz)
    detalle = json.loads(rutas.detalle.read_text(encoding="utf-8"))

    [funcion] = v["funciones"]
    assert funcion["contrato"]["version"] == "2"
    assert funcion["codigo"] == detalle["funciones"][0]["codigo"]
    assert funcion["traza"] is None  # aceptada: no hay traza de fallo
    assert [i["decision"] for i in detalle["funciones"][0]["intentos"]] == [
        "retry",
        "accept",
    ]


def test_un_bug_detectado_es_incidente_con_traza(tmp_path, precios) -> None:  # noqa: F811
    tracker, resultado = correr(precios, decisiones=("bug_detectado",))
    escribir_corrida(tmp_path, resultado, tracker, precios, "deep", metas=METAS)

    _, v = reporte(tmp_path)

    [funcion] = v["funciones"]
    assert funcion["verde"] is False
    assert funcion["traza"] == "assert 19 == 20"
    assert funcion["controles"][2]["etiqueta"].startswith("Oráculo trazable")
    assert {f["clave"]: f["cantidad"] for f in v["filtros"]} == {
        "todas": 1,
        "verde": 0,
        "incidentes": 1,
    }


def test_corrida_anterior_sin_controles_ni_detalle(corrida) -> None:
    raiz, _ = corrida
    results = leer_results(raiz)
    viejo = copy.deepcopy(results)
    del viejo["rama"]
    del viejo["objetivos"][0]["controles"]
    validar(RUN_LOG, viejo)

    v = vista_reporte(viejo, None)

    [funcion] = v["funciones"]
    estados = [c["estado"] for c in funcion["controles"]]
    assert estados == ["sin_dato", "sin_dato", "sin_dato", "ok", "no_aplica"]
    assert funcion["contrato"] is None and funcion["codigo"] is None
    assert v["rama"] is None
    assert v["detalle_disponible"] is False


def test_funcion_critica_sin_mutmut_queda_pendiente(corrida) -> None:
    """Una corrida Profundo sin resultado de mutmut es anterior a EN-09."""
    raiz, _ = corrida
    results = leer_results(raiz)
    results["objetivos"][0]["critical"] = True

    [funcion] = vista_reporte(results, None)["funciones"]

    mutation = funcion["controles"][4]
    assert mutation["estado"] == "pendiente"
    assert "anterior a EN-09" in mutation["nota"]


def critica_con(results: dict, score, mutacion=None) -> dict:
    objetivo = results["objetivos"][0]
    objetivo["critical"] = True
    objetivo["metricas"]["mutation_score"] = score
    if mutacion is not None:
        objetivo["mutacion"] = mutacion
    return results


MUTACION_OK = {
    "estado": "ok",
    "puntuacion": 75.0,
    "detectados": 3,
    "sobrevivientes": [
        {"mutante": "m.x_f__mutmut_2", "linea": 9, "cambio": "x > 1 → x >= 1"}
    ],
    "mensaje": None,
}


@pytest.mark.parametrize("score, estado", [(75.0, "ok"), (60.0, "ok"), (40.0, "falla")])
def test_mutation_score_contra_la_meta(corrida, score, estado) -> None:
    raiz, _ = corrida
    results = critica_con(
        leer_results(raiz), score, {**MUTACION_OK, "puntuacion": score}
    )

    [funcion] = vista_reporte(results, None)["funciones"]

    mutation = funcion["controles"][4]
    assert mutation["estado"] == estado
    assert f"(obtenido: {score:g} %)" in mutation["etiqueta"]
    assert mutation["nota"] == "1 mutante(s) sobreviviente(s)"
    assert funcion["mutacion"]["sobrevivientes"][0]["linea"] == 9
    assert funcion["verde"] is (estado == "ok")


def test_mutacion_sin_puntuacion_explica_el_motivo(corrida) -> None:
    raiz, _ = corrida
    mutacion = {
        **MUTACION_OK,
        "estado": "tiempo_agotado",
        "puntuacion": None,
        "detectados": 0,
        "sobrevivientes": [],
        "mensaje": "Se agotó el tiempo máximo de la mutación (120 s).",
    }
    results = critica_con(leer_results(raiz), None, mutacion)

    [funcion] = vista_reporte(results, None)["funciones"]

    mutation = funcion["controles"][4]
    assert mutation["estado"] == "sin_dato"
    assert "Se agotó el tiempo" in mutation["nota"]
    assert funcion["verde"] is False


def test_critica_en_corrida_sin_profundizar_no_aplica(corrida) -> None:
    raiz, _ = corrida
    results = critica_con(leer_results(raiz), None)
    results["perfil"] = "std"

    [funcion] = vista_reporte(results, None)["funciones"]

    assert funcion["controles"][4]["estado"] == "no_aplica"
    assert "no usó Profundizar" in funcion["controles"][4]["nota"]


def test_critica_sin_prueba_aprobada_no_aplica(tmp_path, precios) -> None:  # noqa: F811
    tracker, resultado = correr(precios, decisiones=("bug_detectado",))
    escribir_corrida(tmp_path, resultado, tracker, precios, "deep", metas=METAS)
    results = critica_con(leer_results(tmp_path), None)

    [funcion] = vista_reporte(results, None)["funciones"]

    assert funcion["controles"][4]["estado"] == "no_aplica"
    assert "Sin prueba aprobada" in funcion["controles"][4]["nota"]


def test_endpoint_muestra_identidad_contrato_http_y_cinco_controles(corrida) -> None:
    raiz, _ = corrida
    results = leer_results(raiz)
    objetivo = results["objetivos"][0]
    objetivo["tipo"] = "endpoint"
    objetivo["funcion"] = "POST /items"
    contrato = {
        "version": "2",
        "tipo": "endpoint",
        "objetivo": "POST /items",
        "manejador": "crear_item",
        "firma": "(datos: ItemEntrada) -> Item",
        "casos": [
            {
                "id": "crear_valido",
                "descripcion": "crea un elemento",
                "entrada": {
                    "metodo": "POST",
                    "ruta": "/items",
                    "json": {"nombre": "<script>alert(1)</script>"},
                },
                "valor_esperado": {
                    "status_code": 201,
                    "json_contiene": {"nombre": "<b>lapiz</b>"},
                },
                "origen": "status_code",
            }
        ],
    }
    detalle = {
        "funciones": [
            {
                "modulo": objetivo["modulo"],
                "funcion": "POST /items",
                "contrato": contrato,
                "codigo": "def test_endpoint(): pass",
                "traza": None,
            }
        ]
    }

    vista = vista_reporte(results, detalle)
    [endpoint] = vista["funciones"]

    assert endpoint["tipo"] == "endpoint"
    assert endpoint["identificador"] == "POST /items"
    assert endpoint["manejador"] == "crear_item"
    assert endpoint["contrato_http"]["casos"][0] == {
        "id": "crear_valido",
        "descripcion": "crea un elemento",
        "peticion": contrato["casos"][0]["entrada"],
        "respuesta_esperada": contrato["casos"][0]["valor_esperado"],
        "origen": "status_code",
        "categoria": "normal",  # #76: inferida (el caso no la trae y espera un 2xx)
    }
    assert len(endpoint["controles"]) == 5
    assert vista["filtros_tipo"][2] == {
        "clave": "endpoint",
        "etiqueta": "Endpoints",
        "cantidad": 1,
    }
