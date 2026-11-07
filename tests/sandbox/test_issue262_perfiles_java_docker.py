"""#262: Humo normal y estándar con límite declarado sobre el banco Java intacto."""

import json
import shutil
from pathlib import Path

import pytest
from docker.models.containers import ContainerCollection

from qagent.almacenamiento import AlmacenProyecto
from qagent.config import cargar_configuracion
from qagent.llm import FakeLLMClient, RespuestaLLM
from qagent.llm.fake import MARCA_CONTRATO
from qagent.orchestrator.corrida import ejecutar_corrida
from qagent.orchestrator.regresion import ejecutar_regresion
from qagent.storage.vista_ejecucion import leer_results
from qagent.storage.vista_reporte import leer_detalle, vista_reporte

pytestmark = pytest.mark.docker
BANCO = Path(__file__).resolve().parents[2] / "bench_java"
MODULO = "src/main/java/org/qagent/bench/BancoDefectuoso.java"
OBJETIVO = "BancoDefectuoso.calcularEnvio"
CASOS = [
    {
        "id": "envio_normal",
        "entrada": {"importe": 50},
        "valor_esperado": 10,
        "origen": "docstring",
        "categoria": "normal",
    },
    {
        "id": "envio_limite",
        "entrada": {"importe": 100},
        "valor_esperado": 0,
        "origen": "docstring",
        "categoria": "limite",
    },
]


class ProveedorEnvioGrabado:
    """Respuestas fijadas desde el Javadoc; no ejecuta Java para elegir el oráculo."""

    def __init__(self) -> None:
        self.planner = FakeLLMClient(
            grabaciones={"BancoDefectuoso.java::" + OBJETIVO: CASOS}
        )

    def generar(self, prompt: str, rol: str = "planner") -> RespuestaLLM:
        """Genera únicamente los casos que el Planner productivo conservó."""
        if rol != "generator":
            return self.planner.generar(prompt, rol=rol)
        contrato = json.loads(prompt.rsplit(MARCA_CONTRATO, 1)[1])
        metodos = []
        for caso in contrato["casos"]:
            importe = caso["entrada"]["importe"]
            esperado = caso["valor_esperado"]
            metodos.append(
                f"@Test void test_{caso['id']}() {{ assertEquals({esperado}.0, "
                f"BancoDefectuoso.calcularEnvio({importe}.0)); }}"
            )
        codigo = (
            "package org.qagent.bench; import org.junit.jupiter.api.Test; "
            "import static org.junit.jupiter.api.Assertions.*; "
            "class BancoDefectuosoTest {" + "\n".join(metodos) + "}"
        )
        return RespuestaLLM(codigo, 0, 0, 0, "fake-envio-grabado")


@pytest.mark.parametrize("perfil", ["humo", "std"])
def test_envio_respeta_perfil_oraculo_y_regresion(
    cliente_docker, tmp_path, monkeypatch, perfil
) -> None:
    """JUnit real prueba 50 en Humo y conserva 50 + 100 en estándar sin red."""
    proyecto = tmp_path / "banco"
    shutil.copytree(BANCO, proyecto, ignore=shutil.ignore_patterns("target", ".qagent"))
    originales = {
        p.relative_to(proyecto): p.read_bytes()
        for p in proyecto.rglob("*")
        if p.is_file()
    }
    almacen = AlmacenProyecto(proyecto)
    almacen.inicializar()
    run = almacen.crear_run(tipos_prueba=["funcion"])
    monkeypatch.setattr(
        "qagent.orchestrator.corrida.crear_cliente",
        lambda *a, **kw: ProveedorEnvioGrabado(),
    )
    contenedores = []
    ejecutar = ContainerCollection.run

    def observar(self, *args, **kwargs):
        """Registra opciones de aislamiento sin simular la ejecución."""
        contenedor = ejecutar(self, *args, **kwargs)
        contenedores.append((contenedor.id, kwargs))
        return contenedor

    monkeypatch.setattr(ContainerCollection, "run", observar)
    config = cargar_configuracion(simulado=True).config
    seleccion = [
        {"ruta": MODULO, "funciones": [OBJETIVO], "endpoints": [], "criticas": []}
    ]
    resumen = ejecutar_corrida(
        proyecto,
        perfil,
        config,
        None,
        simulado=True,
        seleccion=seleccion,
        run_id=run["run_id"],
    )
    assert resumen.estado == "fin", resumen.motivo
    assert resumen.total_procesados == 1
    assert resumen.sin_veredicto == resumen.objetivos_omitidos == resumen.tokens == 0
    results = leer_results(proyecto, resumen.run_id)
    detalle = leer_detalle(proyecto, resumen.run_id)
    [funcion] = vista_reporte(results, detalle)["funciones"]
    casos = funcion["contrato"]["casos"]
    assert funcion["lenguaje"] == "java"
    assert funcion["ejecucion"]["totales"]["total"] == (1 if perfil == "humo" else 2)
    assert [c["entrada"]["importe"] for c in casos] == (
        [50] if perfil == "humo" else [50, 100]
    )
    assert [c["valor_esperado"] for c in casos] == (
        [10] if perfil == "humo" else [10, 0]
    )
    if perfil == "humo":
        assert funcion["decision"] == "accept"
        assert "un caso normal" in funcion["resumen_ejecucion"]
        assert funcion["mutation_score"] is None
        almacen = AlmacenProyecto(proyecto)
        guardada = almacen.crear_run(tipos_prueba=["funcion"])
        regresion = ejecutar_regresion(
            proyecto, "reg", config, run_id=guardada["run_id"], seleccion=seleccion
        )
        assert regresion.aceptadas == regresion.total_procesados == 1
        assert regresion.tokens == 0
    else:
        assert funcion["decision"] == "bug_detectado"
        [fallo] = [
            c for c in funcion["ejecucion"]["casos"] if c["resultado"] == "fallo"
        ]
        assert float(fallo["esperado"]) == 0
        assert float(fallo["obtenido"]) == 10
        assert "Maven" not in funcion["resumen_ejecucion"]
    assert all(
        (proyecto / p).read_bytes() == contenido for p, contenido in originales.items()
    )
    for identidad, opciones in contenedores:
        assert opciones["network_mode"] == "none"
        assert opciones["read_only"] is True
        assert not cliente_docker.containers.list(all=True, filters={"id": identidad})
    print(
        f"Java {perfil}: importes={[c['entrada']['importe'] for c in casos]}; decision={funcion['decision']}; sin red; originales intactos; 0 tokens",
        flush=True,
    )
