"""Progreso, contratos e informes Spring tras recuperar IDs formales (#302)."""

import json
import shutil
from pathlib import Path

from qagent.almacenamiento import AlmacenProyecto
from qagent.config import cargar_configuracion
from qagent.lenguajes.base import ResultadoConstruccion
from qagent.orchestrator import corrida
from qagent.sandbox.modelos import ResultadoSandbox
from qagent.storage.vista_reporte import vista_reporte
from tests.sandbox.test_spring_corrida_docker import (
    BANCO,
    MODULO,
    ClienteSpringGrabado,
)

IMAGEN = "sha256:" + "a" * 64
SELECCION = [
    {
        "ruta": MODULO,
        "funciones": [],
        "endpoints": [
            "POST /api/articulos",
            "POST /api/articulos-defecto",
            "POST /api/sin-contrato",
        ],
    }
]


class ClienteIdsSpring(ClienteSpringGrabado):
    """Propuestas grabadas con ID mixto, un inválido y una colisión; cero API."""

    def __init__(self):
        super().__init__()
        self.llamadas = []
        primero = self.planner.grabaciones[
            "ArticulosController.java::POST /api/articulos"
        ][0]
        primero["id"] = "CrearPago_Normal"
        self.planner.grabaciones["ArticulosController.java::POST /api/articulos"] = [
            primero,
            {**primero, "id": "CREARPAGO-NORMAL"},
            {"id": "Invalido"},
        ]
        self.planner.grabaciones[
            "ArticulosController.java::POST /api/articulos-defecto"
        ][0]["id"] = "CrearPago_Otro"

    def generar(self, prompt, rol="planner"):
        self.llamadas.append(rol)
        respuesta = super().generar(prompt, rol)
        if rol == "generator":
            contrato = json.loads(prompt.split("CONTRATO_JSON: ", 1)[1])
            respuesta.contenido = respuesta.contenido.replace(
                "test_declarado", "test_" + contrato["casos"][0]["id"]
            )
        return respuesta


def verificar_guardado(raiz, resumen):
    carpeta = Path(resumen.carpeta)
    results = json.loads((carpeta / "results.json").read_text(encoding="utf-8"))
    detalle = json.loads((carpeta / "detalle.json").read_text(encoding="utf-8"))
    vista = vista_reporte(results, detalle)
    assert len(vista["funciones"]) == 2
    assert all(o["lenguaje"] == "java" for o in results["objetivos"])
    plan = AlmacenProyecto(raiz).leer_plan_modulo(MODULO)
    assert [c["casos"][0]["id"] for c in plan["contratos"]] == [
        "crearpago_normal",
        "crearpago_otro",
    ]
    assert all(
        c["casos"][0]["valor_esperado"] == {"status_code": 201}
        for c in plan["contratos"]
    )
    assert all(c["casos"][0]["origen"] == "status_code" for c in plan["contratos"])
    assert all(
        c["framework_app"] == "spring" and c["lenguaje"] == "java"
        for c in plan["contratos"]
    )
    assert (
        len(results["omitidos"]) == 1
        and "sin resultado esperado verificable" in results["omitidos"][0]["motivo"]
    )
    assert (
        resumen.total_seleccionados == 3
        and resumen.total_elegibles == resumen.total_procesados == 2
    )
    assert resumen.total_pendientes == 0 and resumen.tokens == 0
    return results, detalle


def test_pipeline_spring_normaliza_persiste_y_conserva_progreso(tmp_path, monkeypatch):
    raiz = tmp_path / "spring"
    shutil.copytree(BANCO, raiz)
    cliente = ClienteIdsSpring()
    monkeypatch.setattr(corrida, "crear_cliente", lambda *a, **k: cliente)
    eventos = []
    resumen = corrida.ejecutar_corrida(
        raiz,
        "std",
        cargar_configuracion(simulado=True).config,
        None,
        simulado=True,
        preparar_imagen=lambda *a: IMAGEN,
        validar_construccion=lambda *a, **k: ResultadoConstruccion(
            "aprobado", "aprobado", "Simulado", imagen_id=IMAGEN
        ),
        ejecutor=lambda *a, **k: ResultadoSandbox(
            0,
            "",
            "",
            junit_xml='<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="test_crearpago_normal" classname="org.qagent.bench.spring.ArticulosControllerTest"/></testsuite>',
        ),
        seleccion=SELECCION,
        al_evento=eventos.append,
    )
    assert resumen.estado == "fin" and resumen.aceptadas == 2, resumen
    verificar_guardado(raiz, resumen)
    assert [e for e in eventos if e["tipo"] == "veredicto"][-1]["progreso"] == {
        "hechos": 2,
        "total": 3,
    }
    assert any("ID repetido después de normalizar" in e["mensaje"] for e in eventos)
    assert (
        cliente.llamadas.count("planner") == 1
        and cliente.llamadas.count("generator") == 2
    )
