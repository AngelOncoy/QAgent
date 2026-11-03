"""Entrada del backend de la aplicación con Java y Docker real; IA grabada (#182)."""

import json
import shutil
from pathlib import Path

import pytest

from qagent.almacenamiento import AlmacenProyecto
from qagent.config import cargar_configuracion
from qagent.llm import FakeLLMClient
from qagent.orchestrator.corrida import FIN, ejecutar_corrida
from qagent.orchestrator.regresion import ejecutar_regresion
from qagent.sandbox.imagen import _imagen_existe
from qagent.sandbox.modelos import IMAGEN_JAVA
from qagent.storage.vista_reporte import vista_reporte
from tests.agents.java_controlado import CASOS, RAIZ, ClienteJavaGrabado

pytestmark = pytest.mark.docker


def test_entrada_de_corrida_java_guarda_resultados_para_la_aplicacion(
    cliente_docker, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """El backend selecciona Java, ejecuta y persiste sin sustituir los agentes."""
    if not _imagen_existe(cliente_docker, IMAGEN_JAVA):
        pytest.skip("Falta qagent-sandbox:java.")
    proyecto = tmp_path / "banco-app"
    shutil.copytree(RAIZ / "bench_java/src", proyecto / "src")
    shutil.copyfile(
        RAIZ / "src/qagent/sandbox/java/calentamiento/pom.xml", proyecto / "pom.xml"
    )
    originales = {
        p.relative_to(proyecto): p.read_bytes()
        for p in proyecto.rglob("*")
        if p.is_file()
    }
    AlmacenProyecto(proyecto).inicializar()
    objetivo = "BancoCorrecto.sumarPrecios"
    entrada, esperado, _ = CASOS[objetivo]
    planner = FakeLLMClient(
        grabaciones={
            "BancoCorrecto.java::" + objetivo: [
                {
                    "id": "contrato",
                    "entrada": entrada,
                    "valor_esperado": esperado,
                    "origen": "docstring",
                    "categoria": "normal",
                }
            ]
        }
    )
    generator = ClienteJavaGrabado()

    class ClienteGrabado:
        """Respuestas del proveedor grabadas; las decisiones de agentes son reales."""

        def generar(self, prompt: str, rol: str = "planner"):
            """Entrega la respuesta grabada correspondiente al rol solicitado."""
            cliente = generator if rol == "generator" else planner
            return cliente.generar(prompt, rol=rol)

    monkeypatch.setattr(
        "qagent.orchestrator.corrida.crear_cliente", lambda *a, **kw: ClienteGrabado()
    )
    config = cargar_configuracion(simulado=True).config
    assert config is not None
    modulo = "src/main/java/org/qagent/bench/BancoCorrecto.java"
    eventos = []
    resumen = ejecutar_corrida(
        proyecto,
        "std",
        config,
        None,
        simulado=True,
        preparar_imagen=lambda ruta: IMAGEN_JAVA,
        al_evento=eventos.append,
        seleccion=[{"ruta": modulo, "funciones": [objetivo], "endpoints": []}],
    )
    assert resumen.estado == FIN, resumen.motivo
    assert resumen.aceptadas == resumen.total_procesados == 1
    assert resumen.bugs_detectados == resumen.estancadas == resumen.sin_veredicto == 0
    assert resumen.tokens == 0
    results = json.loads((Path(resumen.carpeta) / "results.json").read_text("utf-8"))
    [guardado] = results["objetivos"]
    assert guardado["funcion"] == objetivo
    assert guardado["lenguaje"] == "java"
    assert guardado["decision"] == "accept"
    assert guardado["metricas"]["cobertura_lineas"] == 100.0
    assert vista_reporte(results, None)["funciones"][0]["lenguaje"] == "java"
    assert eventos[-1]["tipo"] == "fin"
    run_repetida = AlmacenProyecto(proyecto).crear_run(tipos_prueba=["funcion"])
    repetida = ejecutar_regresion(
        proyecto,
        "reg",
        config,
        run_id=run_repetida["run_id"],
        preparar_imagen=lambda ruta: IMAGEN_JAVA,
    )
    assert repetida.estado == FIN, repetida.motivo
    assert repetida.aceptadas == repetida.total_procesados == 1
    assert repetida.sin_veredicto == repetida.estancadas == 0
    assert repetida.tokens == 0
    resultado_repetido = json.loads(
        (Path(repetida.carpeta) / "results.json").read_text("utf-8")
    )["objetivos"][0]
    assert resultado_repetido["reutilizada"] is True
    assert resultado_repetido["lenguaje"] == "java"
    assert resultado_repetido["metricas"]["cobertura_lineas"] == 100.0
    assert all(
        (proyecto / ruta).read_bytes() == contenido
        for ruta, contenido in originales.items()
    )
    print(
        "Entrada de la aplicación: Java seleccionado, 1 accept, JaCoCo y results.json válidos",
        flush=True,
    )
