"""Corrida sobre el banco JS/TS con tres agentes y guardrails productivos y Docker real (#178).

Comprueba que las pruebas generadas para las funciones del banco se ejecutan dentro del
sandbox Node (qagent-sandbox:node), detectan los 3 bugs sembrados y aprueban las 4 funciones
sin bug, midiendo la cobertura de líneas y ramas y guardando los resultados con la columna
lenguaje y sus 5 métricas.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from qagent.agents.generator import GeneratorAgent
from qagent.agents.planner import PlannerAgent
from qagent.agents.reviewer import ReviewerAgent
from qagent.lenguajes import JavaScriptAdapter, TypeScriptAdapter
from qagent.llm import TokenTracker, cargar_precios
from qagent.llm.fake import FakeLLMClient
from qagent.orchestrator import Orquestador
from qagent.sandbox import LimitesSandbox
from qagent.sandbox.imagen import _imagen_existe
from qagent.sandbox.modelos import IMAGEN_NODE
from qagent.storage.exportar_informe import exportar_informe
from qagent.storage.registro import escribir_corrida
from qagent.storage.vista_ejecucion import vista_ejecucion
from qagent.storage.vista_reporte import vista_reporte
from tests.lenguajes.test_banco_js import BANCO, GRABACIONES

pytestmark = pytest.mark.docker


def test_corrida_banco_js_ts_detecta_tres_bugs_y_guarda_metricas(
    cliente_docker, tmp_path
) -> None:
    """Las funciones del banco JS/TS pasan por orquestador, Vitest, Reviewer y registro."""
    if not _imagen_existe(cliente_docker, IMAGEN_NODE):
        pytest.skip("Falta qagent-sandbox:node.")

    proyecto = tmp_path / "banco"
    shutil.copytree(BANCO, proyecto)

    tracker = TokenTracker()
    precios = cargar_precios()

    resultados = []
    configuraciones = [
        (TypeScriptAdapter(), ["src/precios.ts", "src/texto.ts"]),
        (JavaScriptAdapter(), ["src/personas.mjs", "src/listas.cjs"]),
    ]

    for adaptador, modulos in configuraciones:
        estructura = adaptador.analizar(proyecto)
        modulos_dict = {
            m["modulo"].replace("\\", "/"): m for m in estructura["modulos"]
        }

        planner = PlannerAgent(
            FakeLLMClient(grabaciones=GRABACIONES),
            tracker,
            es_simulado=True,
            adaptador=adaptador,
        )
        generator = GeneratorAgent(
            FakeLLMClient(),
            tracker,
            es_simulado=True,
            ruta_proyecto=proyecto,
        )
        limites = LimitesSandbox(cpus=4.0, memoria="2g", timeout_s=120)
        reviewer = ReviewerAgent(
            tracker,
            proyecto,
            IMAGEN_NODE,
            limites=limites,
        )
        orquestador = Orquestador(
            planner, generator, reviewer, tracker=tracker, timeout_paso_s=240
        )

        for mod_ruta in modulos:
            if mod_ruta in modulos_dict:
                res = orquestador.ejecutar(modulos_dict[mod_ruta])
                resultados.append(res)

    objetivos = [o for r in resultados for o in r.objetivos]
    assert len(objetivos) == 7

    esperados_bug = {"calcularDescuento", "clasificarEdad", "buscarElementoMayor"}
    esperados_accept = {
        "esPalindromo",
        "invertirPalabras",
        "Formateador.moneda",
        "versionFormato",
    }

    for obj in objetivos:
        if obj.objetivo in esperados_bug:
            assert obj.decision == "bug_detectado", (
                f"{obj.objetivo} debió ser bug_detectado"
            )
        elif obj.objetivo in esperados_accept:
            assert obj.decision == "accept", f"{obj.objetivo} debió ser accept"
        else:
            pytest.fail(f"Objetivo inesperado: {obj.objetivo}")

        assert obj.intentos == 1
        assert obj.cobertura is not None
        assert "lineas" in obj.cobertura
        assert "ramas" in obj.cobertura

        revision = obj.revisiones[0]
        assert revision["ejecucion"]["totales"]["total"] >= 1
        assert revision["ejecucion"]["entorno"]["limites"]["memoria"] == "2g"
        assert revision["ejecucion"]["entorno"]["limites"]["timeout_s"] == 120

    rutas = escribir_corrida(
        proyecto,
        resultados,
        tracker,
        precios,
        "std",
        run_id="20261106-000000-0178",
    )
    results = json.loads(rutas.results.read_text(encoding="utf-8"))
    detalle = json.loads(rutas.detalle.read_text(encoding="utf-8"))

    assert sum(o["decision"] == "accept" for o in results["objetivos"]) == 4
    assert sum(o["decision"] == "bug_detectado" for o in results["objetivos"]) == 3

    for objetivo in results["objetivos"]:
        assert objetivo["lenguaje"] in {"javascript", "typescript"}
        assert {
            "paso",
            "cobertura_lineas",
            "cobertura_ramas",
            "iteraciones",
            "tokens_por_agente",
            "mutation_score",
        } == set(objetivo["metricas"])

    vista = vista_ejecucion(results)
    reporte = vista_reporte(results, detalle)

    assert "calcularDescuento" in json.dumps(vista)
    assert "esPalindromo" in json.dumps(reporte)

    for formato in ("md", "html"):
        exportado = exportar_informe(
            proyecto,
            run_id=results["run_id"],
            formato=formato,
            carpeta_destino=tmp_path / "informes",
        )
        assert exportado["ok"]
        archivo = Path(exportado["ruta"])
        assert archivo.is_file()
        assert archivo.stat().st_size > 0
        texto = archivo.read_text(encoding="utf-8")
        assert "calcularDescuento" in texto
        assert "vitest" in texto.lower()
