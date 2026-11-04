"""Aceptación de EP-12 con el banco original, entrada de escritorio y Docker real."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from docker.models.containers import ContainerCollection

from qagent.almacenamiento import AlmacenProyecto
from qagent.app import desktop
from qagent.config import cargar_configuracion
from qagent.llm import FakeLLMClient, RespuestaLLM
from qagent.orchestrator.corrida import FIN, ejecutar_corrida
from qagent.orchestrator.regresion import ejecutar_regresion
from qagent.sandbox.imagen import (
    _buscar_dependencias,
    _imagen_existe,
    etiqueta_para_dependencias,
    receta_de,
)
from qagent.sandbox.modelos import IMAGEN_JAVA
from qagent.storage.vista_reporte import vista_reporte
from tests.agents.java_controlado import CASOS, RAIZ, ClienteJavaGrabado

pytestmark = pytest.mark.docker
BANCO = RAIZ / "bench_java"


class ProveedorJavaGrabado:
    """Respuestas declaradas por el banco: solo sustituye al proveedor de IA."""

    def __init__(self) -> None:
        """Carga entradas y esperados de la especificación independiente de TA-01."""
        grabaciones = {
            nombre.split(".")[0] + ".java::" + nombre: [
                {
                    "id": "contrato",
                    "entrada": entrada,
                    "valor_esperado": esperado,
                    "origen": "docstring",
                    "categoria": "limite"
                    if nombre.endswith("calcularEnvio")
                    else "normal",
                }
            ]
            for nombre, (entrada, esperado, _) in CASOS.items()
        }
        self.planner = FakeLLMClient(grabaciones=grabaciones)
        self.generator = ClienteJavaGrabado()

    def generar(self, prompt: str, rol: str = "planner") -> RespuestaLLM:
        """Entrega respuestas grabadas sin reemplazar agentes, guardrails ni ejecución."""
        return (self.generator if rol == "generator" else self.planner).generar(
            prompt, rol=rol
        )


def test_banco_original_desde_escritorio_hasta_resultados_y_regresion(
    cliente_docker, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Conserva el POM original, detecta tres defectos y repite las pruebas aprobadas."""
    receta = receta_de(IMAGEN_JAVA)
    _, dependencias = _buscar_dependencias(BANCO, receta)
    imagen = etiqueta_para_dependencias(receta.prefijo, dependencias)
    if not _imagen_existe(cliente_docker, imagen):
        pytest.skip(
            "Prepara la imagen derivada de bench_java; la prueba ejecuta sin descargas."
        )
    proyecto = tmp_path / "banco-original"
    shutil.copytree(BANCO, proyecto, ignore=shutil.ignore_patterns("target", ".qagent"))
    originales = {
        p.relative_to(proyecto): p.read_bytes()
        for p in proyecto.rglob("*")
        if p.is_file()
    }
    monkeypatch.setattr(
        desktop.recientes, "ruta_por_defecto", lambda: tmp_path / "recientes.json"
    )
    api = desktop.DesktopAPI()
    abierto = api.abrir_proyecto(str(proyecto))
    assert abierto["ok"] is True
    assert abierto["lenguaje"] == "java"
    vista = api.obtener_vista_previa(str(proyecto))
    assert vista["ok"] is True
    assert vista["resumen"]["total_funciones_publicas"] == 6
    seleccion = [
        {
            "ruta": m["ruta"],
            "funciones": [f["nombre"] for f in m["funciones"]],
            "endpoints": [],
            "criticas": [],
        }
        for m in vista["modulos"]
        if m["funciones"]
    ]
    monkeypatch.setattr(
        "qagent.orchestrator.corrida.crear_cliente",
        lambda *a, **kw: ProveedorJavaGrabado(),
    )
    contenedores = []
    ejecutar_real = ContainerCollection.run

    def observar(self, *args, **kwargs):
        """Registra el aislamiento del contenedor sin modificar su ejecución."""
        contenedor = ejecutar_real(self, *args, **kwargs)
        contenedores.append((contenedor.id, kwargs))
        return contenedor

    monkeypatch.setattr(ContainerCollection, "run", observar)
    config = cargar_configuracion(simulado=True).config
    assert config is not None
    resumen = ejecutar_corrida(
        proyecto, "std", config, None, simulado=True, seleccion=seleccion
    )
    assert resumen.estado == FIN, resumen.motivo
    assert resumen.aceptadas == resumen.bugs_detectados == 3
    assert (
        resumen.sin_veredicto == resumen.estancadas == resumen.objetivos_omitidos == 0
    )
    assert resumen.tokens == 0
    results = json.loads((Path(resumen.carpeta) / "results.json").read_text("utf-8"))
    assert len(results["objetivos"]) == 6
    assert len(vista_reporte(results, None)["funciones"]) == 6
    detalle = json.loads((Path(resumen.carpeta) / "detalle.json").read_text("utf-8"))
    for funcion in detalle["funciones"]:
        assert len(funcion["intentos"]) == 1
        ejecucion = funcion["intentos"][0]["ejecucion"]
        assert ejecucion["totales"]["total"] == 1
        assert (
            ejecucion["entorno"]["limites"]["timeout_s"]
            == config.limites_sandbox("java").timeout_s
        )
    for objetivo in results["objetivos"]:
        nombre = objetivo["funcion"]
        assert objetivo["lenguaje"] == "java"
        assert objetivo["decision"] == (
            "bug_detectado" if nombre.startswith("BancoDefectuoso.") else "accept"
        )
        assert objetivo["metricas"]["cobertura_lineas"] == 100.0
        print(
            f"EP-12 {nombre}: {objetivo['decision']}; JaCoCo=100%; lenguaje=java",
            flush=True,
        )
    almacen = AlmacenProyecto(proyecto)
    guardada = almacen.crear_run(tipos_prueba=["funcion"])
    repetida = ejecutar_regresion(
        proyecto, "reg", config, run_id=guardada["run_id"], seleccion=seleccion
    )
    assert repetida.estado == FIN, repetida.motivo
    assert repetida.aceptadas == repetida.total_procesados == 3
    assert repetida.tokens == 0
    assert api.abrir_reciente(str(proyecto))["ok"] is True
    assert len(contenedores) == 9
    for identidad, opciones in contenedores:
        assert opciones["network_mode"] == "none"
        assert opciones["read_only"] is True
        assert opciones["mem_limit"] == config.limites_sandbox("java").memoria
        assert not cliente_docker.containers.list(all=True, filters={"id": identidad})
    assert all(
        (proyecto / p).read_bytes() == contenido for p, contenido in originales.items()
    )
    print(
        "EP-12: POM original intacto; 3 accept + 3 bugs; regresión 3 accept; Docker sin red, contenedores eliminados; IA grabada, 0 tokens.",
        flush=True,
    )
    print(f"Resultados verificables: {resumen.carpeta}", flush=True)
