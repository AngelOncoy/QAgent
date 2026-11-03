"""Backend Spring completo con MockMvc/Mockito reales en Docker offline (#183)."""

import json
import shutil
from pathlib import Path

import pytest
from docker.models.containers import ContainerCollection

from qagent.almacenamiento import AlmacenProyecto
from qagent.config import cargar_configuracion
from qagent.llm import FakeLLMClient, RespuestaLLM
from qagent.orchestrator.corrida import FIN, ejecutar_corrida
from qagent.sandbox.imagen import (
    _buscar_dependencias,
    _imagen_existe,
    etiqueta_para_dependencias,
    receta_de,
)
from qagent.sandbox.modelos import IMAGEN_JAVA
from qagent.storage.vista_reporte import vista_reporte
from tests.agents.test_generator_spring import CODIGO

pytestmark = pytest.mark.docker
BANCO = Path(__file__).resolve().parents[2] / "bench_java/src/test/resources/spring"
MODULO = "src/main/java/org/qagent/bench/spring/ArticulosController.java"


class ClienteSpringGrabado:
    """Solo reemplaza la respuesta del proveedor; los agentes y guardrails son reales."""

    def __init__(self) -> None:
        """Declara el 201 esperado sin ejecutar ni leer cuerpos de controladores."""
        self.planner = FakeLLMClient(
            grabaciones={
                "ArticulosController.java::POST " + ruta: [
                    {
                        "id": "declarado",
                        "entrada": {"metodo": "POST", "ruta": ruta},
                        "valor_esperado": {"status_code": 201},
                        "origen": "status_code",
                        "categoria": "normal",
                    }
                ]
                for ruta in ("/api/articulos", "/api/articulos-defecto")
            }
        )

    def generar(self, prompt: str, rol: str = "planner") -> RespuestaLLM:
        """Entrega Java grabado; ninguna lógica de decisión se sustituye por el cliente."""
        if rol != "generator":
            return self.planner.generar(prompt, rol)
        contrato = json.loads(prompt.split("CONTRATO_JSON: ", 1)[1])
        codigo = (
            CODIGO.replace("package ejemplo;", "package org.qagent.bench.spring;")
            .replace("Api", "ArticulosController")
            .replace("ejemplo.Servicio", "org.qagent.bench.spring.ArticulosService")
            .replace("test_creacion", "test_declarado")
            .replace('"/items"', json.dumps(contrato["casos"][0]["entrada"]["ruta"]))
        )
        return RespuestaLLM(codigo, 0, 0, 0, "fake-spring-grabado")


def test_corrida_spring_real_detecta_bug_y_omite_sin_declaracion(
    cliente_docker, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ejecuta Planner→Generator→Reviewer y persiste métricas sin red ni servicios reales."""
    receta = receta_de(IMAGEN_JAVA)
    _, archivos = _buscar_dependencias(BANCO, receta)
    etiqueta = etiqueta_para_dependencias(receta.prefijo, archivos)
    if not _imagen_existe(cliente_docker, etiqueta):
        pytest.skip(
            "Prepara primero la imagen derivada del banco Spring; la prueba no descarga dependencias."
        )
    proyecto = tmp_path / "banco-spring"
    shutil.copytree(BANCO, proyecto)
    originales = {
        p.relative_to(proyecto): p.read_bytes()
        for p in proyecto.rglob("*")
        if p.is_file()
    }
    AlmacenProyecto(proyecto).inicializar()
    monkeypatch.setattr(
        "qagent.orchestrator.corrida.crear_cliente",
        lambda *a, **kw: ClienteSpringGrabado(),
    )
    contenedores = []
    ejecutar_real = ContainerCollection.run

    def observar(self, *args, **kwargs):
        """Registra restricciones sin cambiar la creación o ejecución del contenedor."""
        contenedor = ejecutar_real(self, *args, **kwargs)
        contenedores.append((contenedor.id, kwargs))
        return contenedor

    monkeypatch.setattr(ContainerCollection, "run", observar)
    config = cargar_configuracion(simulado=True).config
    resumen = ejecutar_corrida(
        proyecto,
        "std",
        config,
        None,
        simulado=True,
        seleccion=[
            {
                "ruta": MODULO,
                "funciones": [],
                "endpoints": [
                    "POST /api/articulos",
                    "POST /api/articulos-defecto",
                    "POST /api/sin-contrato",
                ],
            }
        ],
    )
    assert resumen.estado == FIN, resumen.motivo
    assert resumen.aceptadas == 1
    assert resumen.bugs_detectados == 1
    assert resumen.sin_veredicto == resumen.estancadas == 0
    assert resumen.objetivos_omitidos == 1
    assert resumen.tokens == 0
    results = json.loads((Path(resumen.carpeta) / "results.json").read_text("utf-8"))
    por_objetivo = {o["funcion"]: o for o in results["objetivos"]}
    assert por_objetivo["POST /api/articulos"]["decision"] == "accept"
    assert por_objetivo["POST /api/articulos-defecto"]["decision"] == "bug_detectado"
    for objetivo in por_objetivo.values():
        assert objetivo["lenguaje"] == "java"
        assert objetivo["metricas"]["cobertura_lineas"] == 100.0
    assert "sin resultado esperado verificable" in results["omitidos"][0]["motivo"]
    assert len(vista_reporte(results, None)["funciones"]) == 2
    detalle = json.loads((Path(resumen.carpeta) / "detalle.json").read_text("utf-8"))
    defectuoso = next(
        f for f in detalle["funciones"] if f["funcion"] == "POST /api/articulos-defecto"
    )
    caso_fallido = defectuoso["intentos"][0]["ejecucion"]["casos"][0]
    assert (caso_fallido["esperado"], caso_fallido["obtenido"]) == ("201", "200")
    assert len(contenedores) == 2
    for identidad, opciones in contenedores:
        assert opciones["network_mode"] == "none"
        assert opciones["read_only"] is True
        assert opciones["mem_limit"] == config.limites_sandbox("java").memoria
        assert not cliente_docker.containers.list(all=True, filters={"id": identidad})
    assert all(
        (proyecto / p).read_bytes() == contenido for p, contenido in originales.items()
    )
    print(
        "Spring real: 1 accept, 1 bug de estado 201/200, 1 omitido; MockMvc + MockBean, JaCoCo 100%, sin red, contenedores eliminados."
    )
