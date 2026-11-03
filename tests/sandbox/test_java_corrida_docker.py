"""Corrida #182 con tres agentes y guardrail productivos, IA grabada y Docker real."""

import json
import os
import shutil
from pathlib import Path

import pytest

from qagent.lenguajes import JavaAdapter
from qagent.llm import cargar_precios
from qagent.sandbox.imagen import _imagen_existe
from qagent.sandbox.modelos import IMAGEN_JAVA
from qagent.storage.exportar_informe import exportar_informe
from qagent.storage.registro import escribir_corrida
from qagent.storage.vista_ejecucion import vista_ejecucion
from qagent.storage.vista_reporte import vista_reporte
from tests.agents.java_controlado import RAIZ, preparar_corrida

pytestmark = pytest.mark.docker


def test_corrida_banco_detecta_tres_bugs_y_guarda_metricas(
    cliente_docker, tmp_path, monkeypatch
):
    """Seis métodos pasan por orquestador, JUnit, JaCoCo, Reviewer y resultados.

    Solo las respuestas de IA están grabadas. Generator, oráculo, comparación de
    aserciones y revisión son productivos; no se parchea el registro de adaptadores.
    """
    if not _imagen_existe(cliente_docker, IMAGEN_JAVA):
        pytest.skip("Falta qagent-sandbox:java.")
    proyecto = tmp_path / "banco"
    shutil.copytree(RAIZ / "bench_java/src", proyecto / "src")
    shutil.copyfile(
        RAIZ / "src/qagent/sandbox/java/calentamiento/pom.xml", proyecto / "pom.xml"
    )
    originales = {
        p.relative_to(proyecto): p.read_bytes()
        for p in proyecto.rglob("*")
        if p.is_file()
    }
    orquestador, tracker, _ = preparar_corrida(monkeypatch, proyecto)
    resultados = [
        orquestador.ejecutar(modulo)
        for modulo in JavaAdapter().analizar(proyecto)["modulos"]
    ]
    objetivos = [o for r in resultados for o in r.objetivos]
    assert len(objetivos) == 6
    for objetivo in objetivos:
        decision = (
            "bug_detectado"
            if objetivo.objetivo.startswith("BancoDefectuoso.")
            else "accept"
        )
        assert objetivo.decision == decision, (objetivo.objetivo, objetivo.revisiones)
        assert objetivo.intentos == 1
        assert objetivo.cobertura["lineas"] == 100.0
        revision = objetivo.revisiones[0]
        assert revision["ejecucion"]["totales"]["total"] == 1
        assert revision["ejecucion"]["entorno"]["limites"]["memoria"] == "4g"
        assert revision["ejecucion"]["entorno"]["limites"]["timeout_s"] == 300
        print(
            f"{objetivo.objetivo}: {decision}; cobertura={objetivo.cobertura}; intentos=1",
            flush=True,
        )
    rutas = escribir_corrida(
        proyecto,
        resultados,
        tracker,
        cargar_precios(),
        "std",
        run_id="20261030-000000-0182",
    )
    results = json.loads(rutas.results.read_text(encoding="utf-8"))
    detalle = json.loads(rutas.detalle.read_text(encoding="utf-8"))
    assert sum(o["decision"] == "accept" for o in results["objetivos"]) == 3
    assert sum(o["decision"] == "bug_detectado" for o in results["objetivos"]) == 3
    for objetivo in results["objetivos"]:
        assert objetivo["lenguaje"] == "java"
        assert {
            "paso",
            "cobertura_lineas",
            "cobertura_ramas",
            "iteraciones",
            "tokens_por_agente",
            "mutation_score",
        } == set(objetivo["metricas"])
    # Son los mismos modelos de vista que consume la aplicación.
    vista = vista_ejecucion(results)
    reporte = vista_reporte(results, detalle)
    assert "BancoDefectuoso.calcularEnvio" in json.dumps(vista)
    assert "BancoCorrecto.sumarPrecios" in json.dumps(reporte)
    for formato in ("md", "html"):
        exportado = exportar_informe(
            proyecto,
            run_id=results["run_id"],
            formato=formato,
            carpeta_destino=tmp_path / "informes",
        )
        assert exportado["ok"]
        texto = Path(exportado["ruta"]).read_text(encoding="utf-8")
        assert "BancoDefectuoso.calcularEnvio" in texto
        assert "java" in texto.lower()
    assert all(
        (proyecto / ruta).read_bytes() == contenido
        for ruta, contenido in originales.items()
    )
    assert not (proyecto / ".qagent-junit.xml").exists()
    assert all(l.tokens_entrada == l.tokens_salida == 0 for l in tracker.llamadas)
    if os.environ.get("QAGENT_GRABAR_JAVA") == "1":
        destino = RAIZ / ".qagent/evidencia-182"
        destino.mkdir(parents=True, exist_ok=True)
        for archivo in (rutas.results, rutas.detalle, rutas.log):
            shutil.copyfile(archivo, destino / archivo.name)
        for archivo in (tmp_path / "informes").iterdir():
            shutil.copyfile(archivo, destino / archivo.name)
        print(
            f"Evidencia real con agentes y guardrail productivos: {destino}", flush=True
        )
