"""DTO con Bean Validation real en Docker offline: MockMvc, Hibernate Validator (#306).

Solo la respuesta del proveedor de IA está grabada. Planner, adaptador, guardrail,
preparación de imagen, Maven/JUnit en Docker sin red y veredictos son productivos.
Los esperados salen de las restricciones de `PedidoDto` y de `@ResponseStatus`.
"""

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

pytestmark = pytest.mark.docker
BANCO = Path(__file__).resolve().parents[2] / "bench_java/src/test/resources/spring"
MODULO = "src/main/java/org/qagent/bench/spring/PedidosController.java"
VALIDO = {"cliente": "Ana", "cantidad": 2, "nota": "urgente"}
CASOS = [
    {
        "id": "pedido_valido",
        "json": VALIDO,
        "status_code": 201,
        "origen": "status_code",
        "categoria": "normal",
    },
    {
        "id": "cliente_en_blanco",
        "json": {**VALIDO, "cliente": " "},
        "status_code": 400,
        "origen": "bean_validation",
        "evidencia": ["PedidoDto.cliente@NotBlank"],
        "categoria": "error",
    },
    {
        "id": "cantidad_mayor_que_max",
        "json": {**VALIDO, "cantidad": 11},
        "status_code": 400,
        "origen": "bean_validation",
        "evidencia": ["PedidoDto.cantidad@Max"],
        "categoria": "error",
    },
]
_IMPORTS = """package org.qagent.bench.spring;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders;
import org.springframework.test.web.servlet.result.MockMvcResultMatchers;
@WebMvcTest(controllers = PedidosController.class)
@ContextConfiguration(classes = PedidosController.class)
class PedidosControllerTest {
    @Autowired private MockMvc mvc;
    @MockBean private org.qagent.bench.spring.ArticulosService mock_servicio;
"""


def _caso_contrato(caso: dict, ruta: str) -> dict:
    """Propuesta grabada del Planner: petición, estado y procedencia declarados."""
    propuesta = {
        "id": caso["id"],
        "entrada": {"metodo": "POST", "ruta": ruta, "json": caso["json"]},
        "valor_esperado": {"status_code": caso["status_code"]},
        "origen": caso["origen"],
        "categoria": caso["categoria"],
    }
    if "evidencia" in caso:
        propuesta["evidencia"] = caso["evidencia"]
    return propuesta


def _junit(ruta: str, casos: list[dict]) -> str:
    """JUnit grabado: la plantilla MockMvc con la petición y el estado de cada caso."""
    lineas = [_IMPORTS.rstrip("\n")]
    for caso in casos:
        cuerpo = json.dumps(json.dumps(caso["json"], separators=(",", ":")))
        lineas += [
            "    /** Comprueba la petición y el estado declarados en el contrato. */",
            f"    @Test void test_{caso['id']}() throws Exception {{",
            (
                f'        mvc.perform(MockMvcRequestBuilders.post("{ruta}")'
                f'.contentType("application/json").content({cuerpo}))'
                f".andExpect(MockMvcResultMatchers.status().is({caso['status_code']}));"
            ),
            "    }",
        ]
    return "\n".join([*lineas, "}", ""])


class ClienteDtoGrabado:
    """Sustituye solo al proveedor de IA; no decide validez ni veredictos."""

    def __init__(self) -> None:
        self.planner = FakeLLMClient(
            grabaciones={
                f"PedidosController.java::POST {ruta}": [
                    _caso_contrato(c, ruta) for c in CASOS
                ]
                for ruta in ("/api/pedidos", "/api/pedidos-defecto")
            }
        )

    def generar(self, prompt: str, rol: str = "planner") -> RespuestaLLM:
        if rol != "generator":
            return self.planner.generar(prompt, rol)
        contrato = json.loads(prompt.split("CONTRATO_JSON: ", 1)[1])
        ruta = contrato["casos"][0]["entrada"]["ruta"]
        ids = [c["id"] for c in contrato["casos"]]
        codigo = _junit(ruta, [c for c in CASOS if c["id"] in ids])
        return RespuestaLLM(codigo, 0, 0, 0, "fake-spring-dto-grabado")


def test_dto_valido_y_violaciones_en_docker_detectan_el_defecto(
    cliente_docker, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bean Validation real: 201 válido, 400 por cada restricción y D-Spring-02."""
    receta = receta_de(IMAGEN_JAVA)
    _, archivos = _buscar_dependencias(BANCO, receta)
    if not _imagen_existe(
        cliente_docker, etiqueta_para_dependencias(receta.prefijo, archivos)
    ):
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
        lambda *a, **kw: ClienteDtoGrabado(),
    )
    contenedores = []
    ejecutar_real = ContainerCollection.run

    def observar(self, *args, **kwargs):
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
                "endpoints": ["POST /api/pedidos", "POST /api/pedidos-defecto"],
            }
        ],
    )
    assert resumen.estado == FIN, resumen.motivo
    assert (resumen.aceptadas, resumen.bugs_detectados) == (1, 1)
    assert resumen.sin_veredicto == resumen.estancadas == 0
    assert resumen.tokens == 0
    carpeta = Path(resumen.carpeta)
    results = json.loads((carpeta / "results.json").read_text("utf-8"))
    por_objetivo = {o["funcion"]: o for o in results["objetivos"]}
    assert por_objetivo["POST /api/pedidos"]["decision"] == "accept"
    assert por_objetivo["POST /api/pedidos-defecto"]["decision"] == "bug_detectado"
    detalle = json.loads((carpeta / "detalle.json").read_text("utf-8"))
    funciones = {f["funcion"]: f for f in detalle["funciones"]}
    contrato = funciones["POST /api/pedidos"]["contrato"]
    assert [c["origen"] for c in contrato["casos"]] == [
        "status_code",
        "bean_validation",
        "bean_validation",
    ]
    assert contrato["casos"][2]["evidencia"] == ["PedidoDto.cantidad@Max"]
    casos = funciones["POST /api/pedidos"]["intentos"][-1]["ejecucion"]["casos"]
    assert len(casos) == 3 and all(c["estado"] == "paso" for c in casos), casos
    defectuoso = funciones["POST /api/pedidos-defecto"]["intentos"][0]["ejecucion"]
    fallidos = [c for c in defectuoso["casos"] if c["estado"] != "paso"]
    assert [(c["esperado"], c["obtenido"]) for c in fallidos] == [("201", "200")]
    for identidad, opciones in contenedores:
        assert opciones["network_mode"] == "none"
        assert opciones["read_only"] is True
        assert not cliente_docker.containers.list(all=True, filters={"id": identidad})
    assert all(
        (proyecto / p).read_bytes() == contenido for p, contenido in originales.items()
    )
    print(
        "Spring DTO real: 201 válido, 400 NotBlank y Max con evidencia; D-Spring-02 201/200 detectado; sin red."
    )
