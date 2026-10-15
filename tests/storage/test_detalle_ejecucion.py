"""detalle.json guarda los casos, la salida y el entorno de cada intento (EN-17)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qagent import contracts
from qagent.orchestrator import Estado, ResultadoCorrida
from qagent.orchestrator.orquestador import ResultadoObjetivo
from qagent.storage.registro import construir_detalle
from tests.storage.test_registro import precios  # noqa: F401 (fixture)

EJEMPLO = json.loads(
    (contracts.DIR_CONTRATOS / "ejemplos" / "detalle.json").read_text(encoding="utf-8")
)
EJECUCION = EJEMPLO["funciones"][0]["intentos"][0]["ejecucion"]


def _revision(intento: int, decision: str, ejecucion: dict | None) -> dict:
    revision = {
        "version": "1",
        "objetivo": "doble",
        "intento": intento,
        "estado_sandbox": "fallo" if decision != "accept" else "ok",
        "cobertura": {"lineas": 100.0, "ramas": None},
        "laundering_detectado": False,
        "tipo_fallo": "bug_codigo" if decision == "bug_detectado" else None,
        "hash_error": "ab" * 8 if decision != "accept" else None,
        "decision": decision,
        "feedback": "assert 12 == 8",
    }
    if ejecucion is not None:
        revision["ejecucion"] = ejecucion
    return revision


def _corrida(*revisiones: dict) -> ResultadoCorrida:
    objetivo = ResultadoObjetivo(
        objetivo="doble",
        critical=False,
        decision=revisiones[-1]["decision"],
        intentos=len(revisiones),
        revisiones=list(revisiones),
        contrato=None,
        codigo="def test_x():\n    assert doble(4) == 8\n",
    )
    return ResultadoCorrida(
        modulo="modulo.py",
        estado_final=Estado.FIN,
        motivo_fallo=None,
        objetivos=[objetivo],
        traza_estados=[],
        tokens_por_agente={},
        duracion_s=1.0,
    )


def test_cada_intento_guarda_su_ejecucion_y_feedback() -> None:
    detalle = construir_detalle(
        "run-1", [_corrida(_revision(1, "bug_detectado", EJECUCION))]
    )

    intento = detalle["funciones"][0]["intentos"][0]
    assert intento["feedback"] == "assert 12 == 8"
    assert intento["hash_error"] == "ab" * 8
    assert intento["cobertura"] == {"lineas": 100.0, "ramas": None}
    assert intento["ejecucion"]["casos"][0]["linea"] == 4
    assert contracts.es_valido(contracts.DETALLE, detalle)


def test_entorno_y_totales_salen_del_ultimo_intento_ejecutado() -> None:
    corrida = _corrida(
        _revision(1, "retry", None),  # no llegó al sandbox
        _revision(2, "bug_detectado", EJECUCION),
    )

    detalle = construir_detalle("run-1", [corrida])

    assert detalle["entorno"]["python"] == "3.11.9"
    assert detalle["totales_casos"] == {
        "total": 2,
        "pasaron": 1,
        "fallaron": 1,
        "errores": 0,
        "omitidos": 0,
    }


def test_sin_ejecuciones_el_entorno_es_nulo_y_los_totales_cero() -> None:
    detalle = construir_detalle("run-1", [_corrida(_revision(1, "retry", None))])

    assert detalle["entorno"] is None
    assert detalle["totales_casos"]["total"] == 0
    assert contracts.es_valido(contracts.DETALLE, detalle)


def test_los_secretos_no_llegan_al_archivo() -> None:
    ejecucion = json.loads(json.dumps(EJECUCION))
    ejecucion["salida"] = "ANTHROPIC_API_KEY=sk-ant-api03-" + "a" * 40
    revision = _revision(1, "bug_detectado", ejecucion)
    revision["feedback"] = "clave sk-ant-api03-" + "b" * 40

    texto = json.dumps(construir_detalle("run-1", [_corrida(revision)]))

    assert "sk-ant-api03-" + "a" * 40 not in texto
    assert "sk-ant-api03-" + "b" * 40 not in texto


@pytest.mark.parametrize("campo", ["entorno", "totales_casos", "funciones"])
def test_el_contrato_exige_los_campos_nuevos(campo: str) -> None:
    dato = json.loads(json.dumps(EJEMPLO))
    del dato[campo]

    assert not contracts.es_valido(contracts.DETALLE, dato)


def test_la_carpeta_de_la_corrida_guarda_el_detalle(tmp_path: Path, precios) -> None:  # noqa: F811
    from qagent.llm import TokenTracker
    from qagent.storage import escribir_corrida

    rutas = escribir_corrida(
        tmp_path,
        [_corrida(_revision(1, "bug_detectado", EJECUCION))],
        TokenTracker(),
        precios,
        "deep",
    )

    escrito = json.loads(rutas.detalle.read_text(encoding="utf-8"))
    assert (
        escrito["funciones"][0]["intentos"][0]["ejecucion"]["totales"]["fallaron"] == 1
    )
