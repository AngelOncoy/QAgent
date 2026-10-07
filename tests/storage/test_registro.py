"""Pruebas del registro de la corrida (EN-05): log.json y results.json.

Los agentes simulados reportan tokens distintos de 0 para comprobar el costo, pero
nunca se llama a una API real ni a Docker.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import pytest
from fakes import (
    MODULO,
    GeneratorSimulado,
    PlannerSimulado,
    ReviewerGuionado,
    ReviewerSandboxTimeout,
)

from pyagent.contracts import RUN_LOG, ContratoInvalido, validar
from pyagent.llm import TokenTracker, cargar_precios
from pyagent.orchestrator import Orquestador
from pyagent.storage import escribir_corrida, nuevo_run_id

# Tokens que "devuelve la API" en cada llamada, por agente (prompt, completion).
TOKENS = {"planner": (1500, 400), "generator": (800, 300), "reviewer": (600, 100)}


class ConTokens:
    """Envuelve un agente simulado y registra su llamada con tokens fijos."""

    def __init__(self, agente: Any, rol: str, tracker: TokenTracker) -> None:
        self._agente, self._rol, self._tracker = agente, rol, tracker

    def _registrar(self) -> None:
        prompt, completion = TOKENS[self._rol]
        modelo = self._tracker.precios[self._rol].modelo
        self._tracker.registrar(self._rol, modelo, prompt, completion, es_simulado=True)

    def planificar(self, modulo):
        self._registrar()
        return self._agente.planificar(modulo)

    def generar(self, contrato, intento, feedback):
        self._registrar()
        return self._agente.generar(contrato, intento, feedback)

    def revisar(self, contrato, test, test_anterior):
        self._registrar()
        return self._agente.revisar(contrato, test, test_anterior)


@pytest.fixture
def precios():
    """Precios reales del config.toml del repositorio."""
    return cargar_precios()


def correr(precios, reviewer=None, decisiones=("accept",), modulo=MODULO):
    """Ejecuta una corrida y devuelve (tracker, resultado)."""
    tracker = TokenTracker(precios)
    mudo = TokenTracker()  # los fakes de EN-04 registran 0 tokens aquí; se ignora
    reviewer = reviewer or ReviewerGuionado(mudo, list(decisiones))
    orquestador = Orquestador(
        ConTokens(PlannerSimulado(mudo), "planner", tracker),
        ConTokens(GeneratorSimulado(mudo), "generator", tracker),
        ConTokens(reviewer, "reviewer", tracker),
        tracker=tracker,
    )
    return tracker, orquestador.ejecutar(modulo)


def leer(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


# --- Criterio 5: evidencia de aceptación ----------------------------------------


def test_archivos_validan_y_costo_coincide_con_tokens_por_precio(
    tmp_path: Path, precios
) -> None:
    tracker, resultado = correr(precios, decisiones=["retry", "accept"])

    rutas = escribir_corrida(tmp_path, resultado, tracker, precios, perfil="deep")
    log, results = leer(rutas.log), leer(rutas.results)

    validar(RUN_LOG, log)
    validar(RUN_LOG, results)
    llamadas = {"planner": 1, "generator": 2, "reviewer": 2}
    for agente, n in llamadas.items():
        prompt, completion = TOKENS[agente]
        precio = precios[agente]
        esperado = (
            prompt * n * precio.entrada_usd_m + completion * n * precio.salida_usd_m
        ) / 1_000_000
        total = log["totales_por_agente"][agente]
        assert total["llamadas"] == n
        assert (total["prompt_tokens"], total["completion_tokens"]) == (
            prompt * n,
            completion * n,
        )
        assert total["costo_usd"] == pytest.approx(esperado)
    assert log["total_costo_usd"] == pytest.approx(
        sum(t["costo_usd"] for t in log["totales_por_agente"].values())
    )


# --- Criterio 1: cada llamada con agente, función, intento y tokens -------------


def test_cada_llamada_registra_funcion_intento_y_tokens(
    tmp_path: Path, precios
) -> None:
    tracker, resultado = correr(precios, decisiones=["retry", "accept"])

    log = leer(escribir_corrida(tmp_path, resultado, tracker, precios, "deep").log)

    resumen = [(ll["agente"], ll["funcion"], ll["intento"]) for ll in log["llamadas"]]
    assert resumen == [
        ("planner", None, None),
        ("generator", "duplicar", 1),
        ("reviewer", "duplicar", 1),
        ("generator", "duplicar", 2),
        ("reviewer", "duplicar", 2),
    ]
    primera = log["llamadas"][1]
    assert (primera["prompt_tokens"], primera["completion_tokens"]) == TOKENS[
        "generator"
    ]
    assert primera["modelo"] == precios["generator"].modelo


# --- Criterio 2: costo con el precio de config.toml -----------------------------


def test_costo_de_cada_llamada_usa_el_precio_de_su_agente(
    tmp_path: Path, precios
) -> None:
    tracker, resultado = correr(precios)

    log = leer(escribir_corrida(tmp_path, resultado, tracker, precios, "deep").log)

    for llamada in log["llamadas"]:
        precio = precios[llamada["agente"]]
        assert llamada["costo_usd"] == pytest.approx(
            precio.costo(llamada["prompt_tokens"], llamada["completion_tokens"])
        )


# --- Criterio 3: ruta .pyagent/runs/<run_id>/ -----------------------------------


def test_escribe_en_pyagent_runs_run_id(tmp_path: Path, precios) -> None:
    tracker, resultado = correr(precios)

    rutas = escribir_corrida(tmp_path, resultado, tracker, precios, "deep")

    assert re.fullmatch(r"\d{8}-\d{6}-[0-9a-f]{4}", rutas.run_id)
    assert rutas.carpeta == tmp_path / ".pyagent" / "runs" / rutas.run_id
    assert sorted(p.name for p in rutas.carpeta.iterdir()) == [
        "log.json",
        "results.json",
    ]
    assert leer(rutas.log)["run_id"] == leer(rutas.results)["run_id"] == rutas.run_id


def test_dos_corridas_no_se_pisan(tmp_path: Path, precios) -> None:
    tracker, resultado = correr(precios)

    a = escribir_corrida(tmp_path, resultado, tracker, precios, "deep")
    b = escribir_corrida(tmp_path, resultado, tracker, precios, "deep")

    assert a.carpeta != b.carpeta
    assert nuevo_run_id() != nuevo_run_id()


def test_si_no_cumple_el_schema_no_escribe_nada(tmp_path: Path, precios) -> None:
    tracker, resultado = correr(precios)

    with pytest.raises(ContratoInvalido):
        escribir_corrida(tmp_path, resultado, tracker, precios, perfil="")

    assert not (tmp_path / ".pyagent").exists()


# --- Criterio 4: modelos, perfil y las 5 métricas por función -------------------


def test_results_tiene_modelos_perfil_y_las_5_metricas(tmp_path: Path, precios) -> None:
    tracker, resultado = correr(precios, decisiones=["retry", "accept"])

    results = leer(
        escribir_corrida(tmp_path, resultado, tracker, precios, "rapido").results
    )

    assert results["perfil"] == "rapido"
    assert results["modelos"]["reviewer"]["modelo"] == precios["reviewer"].modelo
    [funcion] = results["objetivos"]
    assert (funcion["modulo"], funcion["funcion"], funcion["decision"]) == (
        "modulo_simulado.py",
        "duplicar",
        "accept",
    )
    assert funcion["metricas"] == {
        "paso": True,
        "cobertura_lineas": 100.0,
        "cobertura_ramas": 100.0,
        "iteraciones": 2,
        "tokens_por_agente": {
            "generator": {"prompt_tokens": 1600, "completion_tokens": 600},
            "reviewer": {"prompt_tokens": 1200, "completion_tokens": 200},
        },
        "mutation_score": None,
    }
    assert results["resumen"]["pass_rate"] == 100.0
    assert results["resumen"]["aceptadas"] == 1


def test_corrida_con_fallo_controlado_tambien_se_registra(
    tmp_path: Path, precios
) -> None:
    tracker, resultado = correr(precios, reviewer=ReviewerSandboxTimeout())

    rutas = escribir_corrida(tmp_path, resultado, tracker, precios, "deep")
    results = leer(rutas.results)

    assert results["estado_final"] == "fallo_controlado"
    assert "timeout" in results["motivo_fallo"]
    assert results["objetivos"][0]["decision"] is None
    assert results["objetivos"][0]["metricas"]["paso"] is False
    assert results["resumen"]["sin_veredicto"] == 1
    assert leer(rutas.log)["estado_final"] == "fallo_controlado"


def test_varios_modulos_en_un_solo_results(tmp_path: Path, precios) -> None:
    tracker = TokenTracker(precios)
    otro = copy.deepcopy(MODULO) | {"ruta": "otro.py"}
    _, r1 = correr(precios)
    _, r2 = correr(precios, modulo=otro)

    results = leer(
        escribir_corrida(tmp_path, [r1, r2], tracker, precios, "deep").results
    )

    assert [o["modulo"] for o in results["objetivos"]] == [
        "modulo_simulado.py",
        "otro.py",
    ]
    assert results["resumen"]["total_funciones"] == 2
