"""Profundo Java desde el backend, PIT real y caché al repetir sin IA (#180)."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from qagent.almacenamiento import AlmacenProyecto
from qagent.config import cargar_configuracion
from qagent.llm import FakeLLMClient
from qagent.orchestrator.corrida import FIN, ejecutar_corrida
from qagent.orchestrator.regresion import ejecutar_regresion
from qagent.sandbox.imagen import _imagen_existe
from qagent.sandbox.modelos import IMAGEN_JAVA
from qagent.storage.exportar_informe import exportar_informe
from qagent.storage.vista_reporte import vista_reporte
from tests.agents.test_generator_java import ClienteJUnitGrabado
from tests.orchestrator.test_pit_cache_resultados import (
    FUENTE,
    MODULO,
    OBJETIVO,
    PRUEBA,
)

pytestmark = pytest.mark.docker
RAIZ = Path(__file__).resolve().parents[2]


def test_profundo_java_usa_pit_y_regresion_reutiliza_score(
    cliente_docker, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """JUnit aprueba, PIT muta solo la crítica y la segunda corrida usa su caché."""
    if not _imagen_existe(cliente_docker, IMAGEN_JAVA):
        pytest.skip("Falta qagent-sandbox:java; no se validó PIT real.")
    proyecto = tmp_path / "java"
    fuente = proyecto / MODULO
    fuente.parent.mkdir(parents=True)
    fuente.write_text(FUENTE, encoding="utf-8")
    pom = ET.fromstring(
        (RAIZ / "src/qagent/sandbox/java/calentamiento/pom.xml").read_text("utf-8")
    )
    plugins = pom.find("{*}build/{*}plugins")
    for plugin in list(plugins):
        if plugin.findtext("{*}artifactId") == "pitest-maven":
            plugins.remove(plugin)
    ET.ElementTree(pom).write(
        proyecto / "pom.xml", encoding="utf-8", xml_declaration=True
    )
    originales = {
        p.relative_to(proyecto): p.read_bytes()
        for p in proyecto.rglob("*")
        if p.is_file()
    }
    almacen = AlmacenProyecto(proyecto)
    almacen.inicializar()
    planner = FakeLLMClient(
        grabaciones={
            "Criticos.java::" + OBJETIVO: [
                {
                    "id": "normal",
                    "entrada": {"valor": 20},
                    "valor_esperado": 40,
                    "origen": "docstring",
                    "categoria": "normal",
                }
            ]
        }
    )
    generator = ClienteJUnitGrabado(PRUEBA)

    class ClienteGrabado:
        """Sustituye respuestas de IA, nunca agentes, guardrail o motores de ejecución."""

        def generar(self, prompt: str, rol: str = "planner"):
            """Devuelve una respuesta reproducible con cero tokens."""
            return (generator if rol == "generator" else planner).generar(
                prompt, rol=rol
            )

    monkeypatch.setattr(
        "qagent.orchestrator.corrida.crear_cliente", lambda *a, **kw: ClienteGrabado()
    )
    config = cargar_configuracion(simulado=True).config
    assert config is not None
    seleccion = [
        {
            "ruta": MODULO,
            "funciones": [OBJETIVO],
            "endpoints": [],
            "criticas": [OBJETIVO],
        }
    ]
    eventos = []
    corrida = ejecutar_corrida(
        proyecto,
        "deep",
        config,
        None,
        simulado=True,
        seleccion=seleccion,
        preparar_imagen=lambda ruta: IMAGEN_JAVA,
        al_evento=eventos.append,
    )
    assert corrida.estado == FIN, corrida.motivo
    assert corrida.aceptadas == corrida.total_procesados == 1
    assert corrida.tokens == 0
    results = json.loads((Path(corrida.carpeta) / "results.json").read_text("utf-8"))
    [objetivo] = results["objetivos"]
    assert objetivo["funcion"] == OBJETIVO
    assert objetivo["lenguaje"] == "java"
    assert objetivo["decision"] == "accept"
    mutacion = objetivo["mutacion"]
    assert mutacion["estado"] == "ok", mutacion
    assert mutacion["detectados"] >= 1
    assert mutacion["sobrevivientes"]
    assert 0 < mutacion["puntuacion"] < 100
    assert objetivo["metricas"]["mutation_score"] == mutacion["puntuacion"]
    assert all(
        "qagent.Criticos.critico(" in s["mutante"] for s in mutacion["sobrevivientes"]
    )
    assert any("Mutation testing (PIT)" in e.get("mensaje", "") for e in eventos)
    assert vista_reporte(results, None)["funciones"][0]["mutacion"] == mutacion
    informe = exportar_informe(proyecto, run_id=corrida.run_id, formato="md")
    assert informe["ok"]
    assert f"{mutacion['puntuacion']:g}%" in Path(informe["ruta"]).read_text("utf-8")

    def prohibido(*args, **kwargs):
        """La caché vigente impide volver a ejecutar PIT."""
        pytest.fail("No debe volver a ejecutarse PIT sin cambios de código o prueba.")

    monkeypatch.setattr("qagent.sandbox.pit_ejecucion.ejecutar_pit", prohibido)
    run = almacen.crear_run(tipos_prueba=["funcion"])
    repetida = ejecutar_regresion(
        proyecto,
        "reg_deep",
        config,
        run_id=run["run_id"],
        seleccion=seleccion,
        preparar_imagen=lambda ruta: IMAGEN_JAVA,
    )
    assert repetida.estado == FIN, repetida.motivo
    assert repetida.aceptadas == repetida.total_procesados == 1
    assert repetida.tokens == 0
    [guardado] = json.loads(
        (Path(repetida.carpeta) / "results.json").read_text("utf-8")
    )["objetivos"]
    assert guardado["mutacion"]["reutilizada"] is True
    assert guardado["mutacion"]["run_origen"] == corrida.run_id
    assert guardado["mutacion"]["puntuacion"] == mutacion["puntuacion"]
    assert guardado["mutacion"]["sobrevivientes"] == mutacion["sobrevivientes"]
    assert all(
        (proyecto / ruta).read_bytes() == datos for ruta, datos in originales.items()
    )
    print(
        f"Profundo Java: JUnit accept; PIT {mutacion['puntuacion']} %; solo {OBJETIVO}; caché reg_deep reutilizada sin ejecutar PIT",
        flush=True,
    )
