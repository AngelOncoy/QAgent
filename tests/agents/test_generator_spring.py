"""Generator y guardrail MockMvc productivos, con IA grabada y sin Java/Docker (#183)."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from qagent import contracts
from qagent.agents.generator import ErrorRespuestaGenerator, GeneratorAgent
from qagent.agents.planner import PlannerAgent
from qagent.agents.reviewer import ReviewerAgent
from qagent.lenguajes import JavaAdapter
from qagent.lenguajes.java_generacion import contexto_java
from qagent.lenguajes.java_spring_generacion import codigo_spring
from qagent.llm import FakeLLMClient, TokenTracker
from tests.agents.test_generator_java import ClienteJUnitGrabado

FUENTE = """package ejemplo;
import org.springframework.web.bind.annotation.*;
import org.springframework.http.HttpStatus;
@RestController class Api {
  private final Servicio servicio;
  public Api(Servicio servicio) { this.servicio = servicio; }
  @PostMapping("/items") @ResponseStatus(HttpStatus.CREATED)
  public void crear() { servicio.guardar(); /* SECRETO_CUERPO */ }
}
"""

# Respuesta grabada independiente de la función que construye la plantilla.
CODIGO = """package ejemplo;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders;
import org.springframework.test.web.servlet.result.MockMvcResultMatchers;
@WebMvcTest(controllers = Api.class)
@ContextConfiguration(classes = Api.class)
class ApiTest {
    @Autowired private MockMvc mvc;
    @MockBean private ejemplo.Servicio mock_servicio;
    @Test void test_creacion() throws Exception {
        mvc.perform(MockMvcRequestBuilders.post("/items")).andExpect(MockMvcResultMatchers.status().is(201));
    }
}
"""


def preparar_spring(tmp_path: Path, fuente: str = FUENTE) -> dict:
    """Obtiene el contrato con el analizador y Planner reales, sin ejecutar la fuente."""
    archivo = tmp_path / "src/main/java/ejemplo/Api.java"
    archivo.parent.mkdir(parents=True)
    archivo.write_text(fuente, encoding="utf-8")
    [modulo] = JavaAdapter().analizar(tmp_path)["modulos"]
    casos = [
        {
            "id": "creacion",
            "entrada": {"metodo": "POST", "ruta": "/items"},
            "valor_esperado": {"status_code": 201},
            "origen": "status_code",
            "categoria": "normal",
        }
    ]
    planner = PlannerAgent(
        FakeLLMClient(grabaciones={"Api.java::POST /items": casos}),
        TokenTracker(),
        es_simulado=True,
        adaptador=JavaAdapter(),
    )
    [contrato] = planner.planificar_endpoints(modulo)
    return contrato


def test_generator_real_spring_emite_v2_y_ruta(tmp_path: Path) -> None:
    """El Generator común recibe declaraciones Spring y produce el artefacto del paquete."""
    contrato = preparar_spring(tmp_path)
    cliente = ClienteJUnitGrabado(CODIGO)
    tracker = TokenTracker()
    artefacto = GeneratorAgent(
        cliente, tracker, es_simulado=True, ruta_proyecto=tmp_path
    ).generar(contrato, 1, None)
    contracts.validar_versionado(contracts.FAMILIA_GENERATED_TEST, artefacto)
    assert artefacto["codigo"] == CODIGO
    assert artefacto["archivo"] == "src/test/java/ejemplo/ApiTest.java"
    assert artefacto["version"] == "2"
    assert artefacto["casos_cubiertos"] == ["creacion"]
    assert JavaAdapter().validar_oraculo(contrato, CODIGO, tmp_path) is None
    assert "@WebMvcTest" in cliente.prompts[0]
    assert "@MockBean private ejemplo.Servicio mock_servicio" in cliente.prompts[0]
    assert "SECRETO_CUERPO" not in cliente.prompts[0]
    assert tracker.total_tokens == 0
    assert not (tmp_path / "src/test").exists()


@pytest.mark.parametrize(
    "antes,despues",
    [
        (".is(201)", ".is(200)"),
        ('.post("/items")', '.post("/otra")'),
        ('.post("/items")', '.get("/items")'),
        (".andExpect(MockMvcResultMatchers.status().is(201))", ""),
        ("controllers = Api.class", "controllers = Otra.class"),
        (
            "@WebMvcTest(controllers = Api.class)",
            "@org.springframework.boot.test.context.SpringBootTest",
        ),
        (
            "@MockBean private ejemplo.Servicio mock_servicio;",
            "@MockBean private ejemplo.Api mock_servicio;",
        ),
        ("@Autowired private MockMvc mvc;", "@MockBean private MockMvc mvc;"),
        ("@Test void", "@org.junit.jupiter.api.Disabled @Test void"),
        ("throws Exception {", "throws Exception { if (true) return;"),
        (
            'mvc.perform(MockMvcRequestBuilders.post("/items"))',
            'org.mockito.Mockito.mock(MockMvc.class).perform(MockMvcRequestBuilders.post("/items"))',
        ),
    ],
)
def test_reviewer_rechaza_debilitamiento_sin_ejecutar(
    tmp_path: Path, antes: str, despues: str
) -> None:
    """Cada alteración se detecta entre intentos antes de invocar IA o el sandbox."""
    contrato = preparar_spring(tmp_path)
    assert antes in CODIGO
    alterado = CODIGO.replace(antes, despues)
    ejecutor = Mock(
        side_effect=AssertionError("No puede ejecutarse una prueba debilitada.")
    )
    cliente = Mock()
    cliente.generar.side_effect = AssertionError("El guardrail no usa IA.")
    reviewer = ReviewerAgent(
        TokenTracker(), tmp_path, "sin-uso", ejecutor=ejecutor, cliente=cliente
    )
    anterior = contracts.generated_test_para(
        contrato, 1, CODIGO, "src/test/java/ejemplo/ApiTest.java"
    )
    nuevo = contracts.generated_test_para(
        contrato, 2, alterado, "src/test/java/ejemplo/ApiTest.java"
    )
    resultado = reviewer.revisar(contrato, nuevo, anterior)
    assert resultado["laundering_detectado"] is True
    assert resultado["decision"] == "retry"
    ejecutor.assert_not_called()
    cliente.generar.assert_not_called()


def test_primera_prueba_inventada_no_llega_al_ejecutor(tmp_path: Path) -> None:
    """El primer intento también debe respetar el oráculo; no necesita una referencia previa."""
    contrato = preparar_spring(tmp_path)
    ejecutor = Mock(side_effect=AssertionError("No se ejecuta un estado inventado."))
    reviewer = ReviewerAgent(TokenTracker(), tmp_path, "sin-uso", ejecutor=ejecutor)
    artefacto = contracts.generated_test_para(
        contrato,
        1,
        CODIGO.replace(".is(201)", ".is(200)"),
        "src/test/java/ejemplo/ApiTest.java",
    )
    resultado = reviewer.revisar(contrato, artefacto, None)
    assert resultado["tipo_fallo"] == "error_test"
    assert resultado["decision"] == "retry"
    assert "Oráculo inválido" in resultado["feedback"]
    ejecutor.assert_not_called()


def test_formato_comentarios_y_orden_imports_no_cambian_oraculo(tmp_path: Path) -> None:
    """La comparación usa tokens reales e ignora comentarios y orden de imports."""
    contrato = preparar_spring(tmp_path)
    lineas = CODIGO.splitlines()
    cambiado = "\n".join([lineas[0], *reversed(lineas[1:9]), *lineas[9:]])
    cambiado = cambiado.replace(".is(201)", ".is( /* esperado declarado */ 201 )")
    assert JavaAdapter().validar_oraculo(contrato, cambiado, tmp_path) is None
    assert JavaAdapter().comparar_aserciones(CODIGO, cambiado).es_laundering is False


def test_error_sintaxis_se_devuelve_al_generator(tmp_path: Path) -> None:
    """Una clase mal formada se rechaza con el diagnóstico del parser, sin ejecutar Java."""
    contrato = preparar_spring(tmp_path)
    generator = GeneratorAgent(
        ClienteJUnitGrabado(CODIGO[:-3]), TokenTracker(), ruta_proyecto=tmp_path
    )
    with pytest.raises(ErrorRespuestaGenerator, match="inválido"):
        generator.generar(contrato, 1, None)


def test_contexto_rechaza_dependencias_inventadas(tmp_path: Path) -> None:
    """Un contrato manipulado no autoriza simular el controlador ni agregar beans."""
    contrato = preparar_spring(tmp_path)
    contrato["dependencias"] = [{"funcion": "servicio", "reemplazo": "ejemplo.Api"}]
    with pytest.raises(ValueError, match="dependencias inyectadas"):
        contexto_java(contrato, tmp_path)


def test_plantilla_preserva_cuerpo_query_y_headers(tmp_path: Path) -> None:
    """La petición JSON y los parámetros literales se mantienen sin interpolar código."""
    fuente = FUENTE.replace(
        "public void crear()",
        "public void crear(@RequestBody Object cuerpo, @RequestParam int cantidad)",
    )
    # El Planner verifica la petición completa; la fuente no se ejecuta para decidirla.
    archivo = tmp_path / "src/main/java/ejemplo/Api.java"
    archivo.parent.mkdir(parents=True)
    archivo.write_text(fuente, encoding="utf-8")
    modulo = JavaAdapter().analizar(tmp_path)["modulos"][0]
    caso = {
        "id": "creacion",
        "entrada": {
            "metodo": "POST",
            "ruta": "/items",
            "query": {"cantidad": 2},
            "headers": {"X-Prueba": "local"},
            "json": {"nombre": "hola"},
        },
        "valor_esperado": {"status_code": 201},
        "origen": "status_code",
        "categoria": "normal",
    }
    planner = PlannerAgent(
        FakeLLMClient(grabaciones={"Api.java::POST /items": [caso]}),
        TokenTracker(),
        es_simulado=True,
        adaptador=JavaAdapter(),
    )
    [contrato] = planner.planificar_endpoints(modulo)
    codigo = codigo_spring(contrato, contexto_java(contrato, tmp_path))
    assert '.param("cantidad", "2")' in codigo
    assert '.header("X-Prueba", "local")' in codigo
    assert '.contentType("application/json")' in codigo
    assert JavaAdapter().validar_sintaxis(codigo) == []
    assert JavaAdapter().validar_oraculo(contrato, codigo, tmp_path) is None
    assert (
        JavaAdapter().validar_oraculo(
            contrato, codigo.replace('"cantidad", "2"', '"cantidad", "3"'), tmp_path
        )
        is not None
    )


def test_dependencia_por_campo_autowired(tmp_path: Path) -> None:
    """La inyección por campo también declara un MockBean, sin construir el servicio."""
    fuente = FUENTE.replace(
        "@RestController class Api",
        "import org.springframework.beans.factory.annotation.Autowired;\n@RestController class Api",
    )
    fuente = fuente.replace(
        "private final Servicio servicio;", "@Autowired private Servicio servicio;"
    )
    fuente = fuente.replace(
        "public Api(Servicio servicio) { this.servicio = servicio; }", ""
    )
    contrato = preparar_spring(tmp_path, fuente)
    assert contrato["dependencias"] == [
        {"funcion": "servicio", "reemplazo": "ejemplo.Servicio"}
    ]
    assert JavaAdapter().validar_oraculo(contrato, CODIGO, tmp_path) is None


def test_nombre_dependencia_no_colisiona_con_mockmvc(tmp_path: Path) -> None:
    """El nombre mvc de un servicio no duplica el campo real de MockMvc."""
    contrato = preparar_spring(tmp_path, FUENTE.replace("servicio", "mvc"))
    codigo = codigo_spring(contrato, contexto_java(contrato, tmp_path))
    assert "@Autowired private MockMvc mvc;" in codigo
    assert "@MockBean private ejemplo.Servicio mock_mvc;" in codigo
    assert JavaAdapter().validar_oraculo(contrato, codigo, tmp_path) is None


@pytest.mark.parametrize(
    "constructor",
    [
        "public Api(String nombre) {}",
        "public Api(Servicio uno, Servicio dos) {}",
        "public Api() {} public Api(Servicio servicio) {}",
    ],
)
def test_dependencias_ambiguas_se_omiten_sin_inventar_mocks(
    tmp_path: Path, constructor: str
) -> None:
    """No se adivinan beans, valores de configuración ni constructores ambiguos."""
    fuente = FUENTE.replace(
        "public Api(Servicio servicio) { this.servicio = servicio; }", constructor
    )
    archivo = tmp_path / "Api.java"
    archivo.write_text(fuente, encoding="utf-8")
    modulo = JavaAdapter().analizar(tmp_path)["modulos"][0]
    endpoint = modulo["endpoints"][0]
    assert endpoint["dependencias_resueltas"] is False
    assert (
        "sin resultado esperado verificable"
        in JavaAdapter().motivo_endpoint_no_planificable(endpoint)
    )


def test_contrato_manipulado_no_inyecta_codigo_en_nombre_de_caso(
    tmp_path: Path,
) -> None:
    """La plantilla valida el schema antes de interpolar nombres provenientes del contrato."""
    contrato = preparar_spring(tmp_path)
    contexto = contexto_java(contrato, tmp_path)
    contrato["casos"][0]["id"] = "nombre() { ejecutar(); } void otro"
    with pytest.raises(contracts.ContratoInvalido):
        codigo_spring(contrato, contexto)
