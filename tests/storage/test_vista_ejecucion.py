"""Vista «Ejecución de pruebas» (HU-18): todo sale de results.json."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from qagent.contracts import RUN_LOG, validar
from qagent.storage import escribir_corrida
from qagent.storage.vista_ejecucion import (
    ResultadosNoDisponibles,
    estado_de,
    leer_results,
    ultimo_run_con_resultados,
    vista_ejecucion,
)
from tests.storage.test_registro import correr, precios  # noqa: F401 (fixture)

EJEMPLO = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "qagent"
    / "contracts"
    / "ejemplos"
    / "run_log.results.json"
)
METAS = {
    "pass_rate_min": 70,
    "cobertura_lineas_min": 60,
    "iteraciones_promedio_max": 2.0,
    "tope_por_corrida_usd": 1.0,
}


def objetivo(
    funcion,
    decision,
    *,
    modulo="a.py",
    iteraciones=1,
    laundering=False,
    motivo=None,
    paso=True,
    lineas=80.0,
    ramas=50.0,
    tipo=None,
):
    dato = {
        "modulo": modulo,
        "funcion": funcion,
        "critical": False,
        "decision": decision,
        "motivo_estancado": motivo,
        "laundering_detectado": laundering,
        "duracion_s": 1.5,
        "metricas": {
            "paso": paso,
            "cobertura_lineas": lineas,
            "cobertura_ramas": ramas,
            "iteraciones": iteraciones,
            "tokens_por_agente": {},
            "mutation_score": None,
        },
    }
    if tipo is not None:
        dato["tipo"] = tipo
    return dato


@pytest.fixture
def results() -> dict:
    """Corrida con un caso de cada estado, en dos módulos."""
    datos = json.loads(EJEMPLO.read_text(encoding="utf-8"))
    datos["objetivos"] = [
        objetivo("aprobada", "accept"),
        objetivo("con_bug", "bug_detectado", paso=False),
        objetivo(
            "lavada",
            "stalled",
            iteraciones=3,
            laundering=True,
            motivo="limite_intentos",
            paso=False,
            lineas=None,
            ramas=None,
        ),
        objetivo(
            "estancada",
            "stalled",
            modulo="b.py",
            iteraciones=2,
            motivo="error_repetido",
            paso=False,
            lineas=40.0,
            ramas=None,
        ),
    ]
    datos["resumen"].update(
        total_funciones=4,
        aceptadas=1,
        bugs_detectados=1,
        stalled=2,
        pass_rate=25.0,
        cobertura_lineas_promedio=66.7,
        cobertura_ramas_promedio=50.0,
        iteraciones_promedio=1.75,
        metas=METAS,
    )
    validar(RUN_LOG, datos)
    return datos


def test_cada_estado_sale_del_veredicto(results) -> None:
    assert [estado_de(o) for o in results["objetivos"]] == [
        "aprobado",
        "bug_detectado",
        "rechazado_laundering",
        "estancado",
    ]


def test_los_indicadores_coinciden_con_results_json(results) -> None:
    """Criterio 5: los 4 indicadores son los valores del archivo, comparados con su meta."""
    k = vista_ejecucion(results)["indicadores"]
    resumen = results["resumen"]

    assert k["pass_rate"]["valor"] == resumen["pass_rate"]
    assert (k["pass_rate"]["meta"], k["pass_rate"]["cumple"]) == (70, False)
    assert k["cobertura"]["lineas"] == resumen["cobertura_lineas_promedio"]
    assert k["cobertura"]["ramas"] == resumen["cobertura_ramas_promedio"]
    assert k["cobertura"]["cumple"] is True
    assert k["iteraciones"]["valor"] == resumen["iteraciones_promedio"]
    assert k["iteraciones"]["cumple"] is True
    assert k["costo"]["costo_total_usd"] == resumen["costo_total_usd"]
    for agente, fila in resumen["por_agente"].items():
        assert k["costo"]["por_agente"][agente]["costo_usd"] == fila["costo_usd"]
        assert k["costo"]["por_agente"][agente]["tokens"] == (
            fila["prompt_tokens"] + fila["completion_tokens"]
        )
    # EN-09: sin funciones críticas no hay Mutation Score que promediar.
    assert k["mutation_score"]["disponible"] is False
    assert k["mutation_score"]["texto"].startswith("No se midió")


def test_mutation_score_promedia_las_criticas_con_puntuacion(results) -> None:
    results["perfil"] = "deep"
    objetivos = results["objetivos"]
    for objetivo, score in zip(objetivos, (80.0, 40.0)):
        objetivo["critical"] = True
        objetivo["metricas"]["mutation_score"] = score

    ms = vista_ejecucion(results)["indicadores"]["mutation_score"]

    assert ms["disponible"] is True
    assert (ms["valor"], ms["meta"], ms["cumple"], ms["funciones"]) == (
        60.0,
        60,
        True,
        2,
    )


@pytest.mark.parametrize(
    "perfil, critica, texto",
    [
        ("std", True, "no usó Profundizar"),
        ("deep", False, "no hay funciones marcadas"),
        ("deep", True, "el motivo está en el informe"),
    ],
)
def test_mutation_score_sin_valor_explica_por_que(
    results, perfil, critica, texto
) -> None:
    results["perfil"] = perfil
    for objetivo in results["objetivos"]:
        objetivo["critical"] = critica
        objetivo["metricas"]["mutation_score"] = None

    ms = vista_ejecucion(results)["indicadores"]["mutation_score"]

    assert ms["disponible"] is False
    assert texto in ms["texto"]


def test_filtros_con_su_conteo(results) -> None:
    filtros = {f["clave"]: f["cantidad"] for f in vista_ejecucion(results)["filtros"]}

    assert filtros == {
        "aprobado": 1,
        "rechazado_laundering": 1,
        "estancado": 1,
        "bug_detectado": 1,
    }


def test_los_filtros_pedidos_se_muestran_aunque_esten_en_cero(results) -> None:
    results["objetivos"] = results["objetivos"][:1]

    claves = [f["clave"] for f in vista_ejecucion(results)["filtros"]]

    assert claves == ["aprobado", "rechazado_laundering", "estancado"]


def test_filtros_de_tipo_e_identidad_http_salen_de_results(results) -> None:
    results["objetivos"][1]["tipo"] = "endpoint"
    results["objetivos"][1]["funcion"] = "POST /items"

    vista = vista_ejecucion(results)

    assert vista["filtros_tipo"] == [
        {"clave": "todos", "etiqueta": "Todos", "cantidad": 4},
        {"clave": "funcion", "etiqueta": "Funciones", "cantidad": 3},
        {"clave": "endpoint", "etiqueta": "Endpoints", "cantidad": 1},
    ]
    endpoint = vista["modulos"][0]["pruebas"][1]
    assert endpoint["identificador"] == "POST /items"
    assert (endpoint["metodo"], endpoint["ruta"]) == ("POST", "/items")
    assert endpoint["identidad_completa"] is True


def test_endpoint_incompleto_no_recibe_una_ruta_inventada(results) -> None:
    results["objetivos"][0]["tipo"] = "endpoint"
    results["objetivos"][0]["funcion"] = "crear_item"

    endpoint = vista_ejecucion(results)["modulos"][0]["pruebas"][0]

    assert endpoint["identificador"] == "Endpoint sin método/ruta"
    assert endpoint["metodo"] is None and endpoint["ruta"] is None
    assert endpoint["identidad_completa"] is False


def test_corrida_antigua_sin_tipo_se_conserva_como_funcion(results) -> None:
    prueba = vista_ejecucion(results)["modulos"][0]["pruebas"][0]

    assert prueba["tipo"] == "funcion"
    assert prueba["identificador"] == "aprobada"


def test_pruebas_agrupadas_por_modulo(results) -> None:
    modulos = vista_ejecucion(results)["modulos"]

    assert [m["modulo"] for m in modulos] == ["a.py", "b.py"]
    estancada = modulos[1]["pruebas"][0]
    assert estancada == {
        "funcion": "estancada",
        "tipo": "funcion",
        "identificador": "estancada",
        "metodo": None,
        "ruta": None,
        "identidad_completa": True,
        "estado": "estancado",
        "intento_final": 2,
        "duracion_s": 1.5,
        "cobertura_lineas": 40.0,
        "cobertura_ramas": None,
        "motivo_estancado": "error_repetido",
        "critical": False,
    }


def test_corrida_anterior_a_hu18_se_completa_con_sus_propios_datos(results) -> None:
    viejo = copy.deepcopy(results)
    for clave in (
        "cobertura_ramas_promedio",
        "iteraciones_promedio",
        "por_agente",
        "metas",
    ):
        del viejo["resumen"][clave]
    for o in viejo["objetivos"]:
        del o["laundering_detectado"], o["duracion_s"]
    validar(RUN_LOG, viejo)

    vista = vista_ejecucion(viejo)

    assert vista["indicadores"]["cobertura"]["ramas"] == 50.0  # promedio de 50 y 50
    assert vista["indicadores"]["iteraciones"]["valor"] == 1.75
    assert vista["indicadores"]["pass_rate"]["cumple"] is None  # sin meta registrada
    assert vista["metas_registradas"] is False
    assert vista["modulos"][0]["pruebas"][0]["duracion_s"] is None


def test_de_la_corrida_al_archivo_y_a_la_vista(tmp_path, precios) -> None:  # noqa: F811
    """Lo que escribe la corrida es lo que muestra la vista, sin cifras intermedias."""
    tracker, resultado = correr(precios, decisiones=("retry", "accept"))
    rutas = escribir_corrida(tmp_path, resultado, tracker, precios, "deep", metas=METAS)

    archivo = json.loads(rutas.results.read_text(encoding="utf-8"))
    vista = vista_ejecucion(leer_results(tmp_path))

    resumen = archivo["resumen"]
    assert vista["run_id"] == rutas.run_id
    assert vista["indicadores"]["pass_rate"]["valor"] == resumen["pass_rate"]
    assert (
        vista["indicadores"]["iteraciones"]["valor"]
        == resumen["iteraciones_promedio"]
        == 2
    )
    assert (
        vista["indicadores"]["costo"]["costo_total_usd"]
        == resumen["costo_total_usd"]
        > 0
    )
    assert resumen["metas"] == METAS
    assert archivo["objetivos"][0]["duracion_s"] >= 0


def test_sin_corridas_avisa(tmp_path) -> None:
    assert ultimo_run_con_resultados(tmp_path) is None
    with pytest.raises(ResultadosNoDisponibles, match="todavía no tiene"):
        leer_results(tmp_path)


def test_results_invalido_avisa(tmp_path) -> None:
    carpeta = tmp_path / ".qagent" / "runs" / "20261010-120000-abcd"
    carpeta.mkdir(parents=True)
    (carpeta / "results.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ResultadosNoDisponibles, match="no es válido"):
        leer_results(tmp_path)


def test_un_agente_sin_llamadas_aparece_con_cero(results) -> None:
    del results["resumen"]["por_agente"]["reviewer"]

    reviewer = vista_ejecucion(results)["indicadores"]["costo"]["por_agente"][
        "reviewer"
    ]

    assert reviewer == {"tokens": 0, "costo_usd": 0.0, "llamadas": 0}
