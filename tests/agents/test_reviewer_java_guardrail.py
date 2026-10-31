"""Guardrail del Reviewer real antes del puerto de ejecución, sin Docker/IA (#184)."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from qagent import contracts
from qagent.agents.generator import GeneratorAgent
from qagent.agents.planner import PlannerAgent
from qagent.agents.reviewer import ReviewerAgent
from qagent.lenguajes import JavaAdapter
from qagent.lenguajes.java_generacion import ReglasGeneracionJava
from qagent.llm import FakeLLMClient, TokenTracker
from qagent.orchestrator import Orquestador
from qagent.sandbox import ResultadoSandbox
from tests.agents.test_generator_java import CODIGO, ClienteJUnitGrabado, preparar


def generado(contrato: dict, codigo: str, intento: int) -> dict:
    """Generated_test.v2 válido para comparar intentos sin escribir ni ejecutar Java."""
    return contracts.generated_test_para(
        contrato, intento, codigo, "src/test/java/ejemplo/BancoTest.java"
    )


@pytest.mark.parametrize(
    "reemplazo",
    [
        "Banco.duplicar(2);",
        "assertEquals(5, Banco.duplicar(2));",
        "org.junit.jupiter.api.Assertions.assertNotNull(Banco.duplicar(2));",
        "org.junit.jupiter.api.Assertions.assertTrue(true);",
        "try { assertEquals(4, Banco.duplicar(2)); } catch (Exception ignorada) {}",
    ],
)
def test_reviewer_marca_laundering_antes_de_ejecutar(
    tmp_path: Path, reemplazo: str
) -> None:
    """Cada degradación se rechaza con contrato, adaptador y Reviewer reales."""
    contrato = preparar(tmp_path)
    ejecutor = Mock(
        side_effect=AssertionError("El intento debilitado no puede llegar al ejecutor.")
    )
    cliente = Mock()
    cliente.generar.side_effect = AssertionError("El guardrail no consulta IA.")
    reviewer = ReviewerAgent(
        TokenTracker(), tmp_path, "sin-uso", ejecutor=ejecutor, cliente=cliente
    )
    codigo = CODIGO.replace("assertEquals(4, Banco.duplicar(2));", reemplazo)
    revision = reviewer.revisar(
        contrato, generado(contrato, codigo, 2), generado(contrato, CODIGO, 1)
    )
    contracts.validar(contracts.REVIEW_RESULT, revision)
    assert revision["laundering_detectado"] is True
    assert revision["tipo_fallo"] == "error_test"
    assert revision["decision"] == "retry"
    assert revision["hash_error"]
    assert "Assertion Laundering" in revision["feedback"]
    assert "ejecucion" not in revision
    ejecutor.assert_not_called()
    cliente.generar.assert_not_called()


@pytest.mark.parametrize(
    "cuerpo",
    [
        "Banco.duplicar(-1);",
        "try { Banco.duplicar(-1); } catch (Exception ignorada) {}",
    ],
)
def test_assertthrows_eliminado_o_silenciado_se_registra_como_laundering(
    tmp_path: Path, cuerpo: str
) -> None:
    """Eliminar el esperado de excepción no puede convertir el fallo en un éxito."""
    contrato = preparar(tmp_path)
    contrato["casos"][0].pop("valor_esperado")
    contrato["casos"][0].update(
        entrada={"x": -1}, excepcion="IllegalArgumentException", categoria="error"
    )
    original = CODIGO.replace(
        "import static org.junit.jupiter.api.Assertions.assertEquals;",
        "import static org.junit.jupiter.api.Assertions.assertThrows;",
    )
    original = original.replace(
        "assertEquals(4, Banco.duplicar(2));",
        "assertThrows(IllegalArgumentException.class, () -> Banco.duplicar(-1));",
    )
    cambiado = original.replace(
        "assertThrows(IllegalArgumentException.class, () -> Banco.duplicar(-1));",
        cuerpo,
    )
    ejecutor = Mock(
        side_effect=AssertionError("No debe ejecutarse el intento debilitado.")
    )
    reviewer = ReviewerAgent(TokenTracker(), tmp_path, "sin-uso", ejecutor=ejecutor)
    revision = reviewer.revisar(
        contrato, generado(contrato, cambiado, 2), generado(contrato, original, 1)
    )
    assert revision["laundering_detectado"] is True
    assert revision["decision"] == "retry"
    ejecutor.assert_not_called()


@pytest.mark.parametrize(
    "archivo",
    ["src/test/java/otro/BancoTest.java", "src/test/java/ejemplo/OtroTest.java"],
)
def test_archivo_del_artefacto_corresponde_al_paquete_y_clase(
    tmp_path: Path, archivo: str
) -> None:
    """Una ruta formalmente válida pero ajena al contexto no llega al comando ni ejecutor."""
    contrato = preparar(tmp_path)
    ejecutor = Mock(side_effect=AssertionError("No debe llegar al ejecutor."))
    reviewer = ReviewerAgent(TokenTracker(), tmp_path, "sin-uso", ejecutor=ejecutor)
    test = generado(contrato, CODIGO, 1)
    test["archivo"] = archivo
    revision = reviewer.revisar(contrato, test, None)
    assert revision["decision"] == "retry"
    assert revision["tipo_fallo"] == "error_test"
    assert "paquete y clase" in revision["feedback"]
    assert not reviewer._referencias
    ejecutor.assert_not_called()


class ReglasConPuertoEjecucionSimulado(ReglasGeneracionJava):
    """Solo sustituye el puerto de cobertura de #182; sintaxis y oráculo son reales."""

    def rango_de_objetivo(
        self, raiz: Path, modulo: str, nombre: str
    ) -> tuple[int, int] | None:
        """La ejecución simulada no mide cobertura; no se fabrica un porcentaje."""
        return None


class AdaptadorConPuertoEjecucionSimulado(JavaAdapter):
    """Representa únicamente el runner futuro; no reemplaza ningún guardrail de #184."""

    def comando_pruebas(self, modulo: str, framework: str | None = None) -> list[str]:
        """Comando de evidencia que nunca se invoca: el ejecutor es un doble grabado."""
        return ["runner-simulado-no-ejecutar"]

    def reglas_revision(self) -> ReglasConPuertoEjecucionSimulado:
        """Mantiene sintaxis y oráculo de producción, sin cobertura real en esta prueba."""
        return ReglasConPuertoEjecucionSimulado()


def ejecutor_grabado() -> Mock:
    """Puerto controlado: inspecciona la copia del test y devuelve JUnit grabado."""

    def ejecutar(imagen, raiz, ruta_tests, modulo):
        archivo = ruta_tests / "src/test/java/ejemplo/BancoTest.java"
        assert archivo.read_text(encoding="utf-8") == CODIGO
        assert not (raiz / "src/test").exists()
        return ResultadoSandbox(
            exit_code=0,
            stdout="JUnit grabado, sin ejecución.",
            stderr="",
            junit_xml='<testsuite tests="1"><testcase classname="ejemplo.BancoTest" name="test_positivo"/></testsuite>',
        )

    return Mock(side_effect=ejecutar)


def test_referencia_valida_no_se_reemplaza_por_un_intento_debilitado(
    tmp_path: Path, monkeypatch
) -> None:
    """Tras aceptar una referencia, dos reparaciones malas se comparan contra ella."""
    contrato = preparar(tmp_path)
    adaptador = AdaptadorConPuertoEjecucionSimulado()
    monkeypatch.setattr(
        "qagent.agents.reviewer.adaptador_de_contrato", lambda contrato: adaptador
    )
    ejecutor = ejecutor_grabado()
    reviewer = ReviewerAgent(TokenTracker(), tmp_path, "sin-uso", ejecutor=ejecutor)
    primera = generado(contrato, CODIGO, 1)
    assert reviewer.revisar(contrato, primera, None)["decision"] == "accept"
    segunda = generado(
        contrato, CODIGO.replace("assertEquals(4,", "assertEquals(5,"), 2
    )
    rechazo2 = reviewer.revisar(contrato, segunda, primera)
    tercera = generado(contrato, segunda["codigo"], 3)
    rechazo3 = reviewer.revisar(contrato, tercera, segunda)
    assert rechazo2["laundering_detectado"] is True
    assert rechazo3["laundering_detectado"] is True
    assert rechazo3["decision"] == "stalled"
    assert rechazo2["hash_error"] == rechazo3["hash_error"]
    assert reviewer._referencias[(contrato["modulo"], contrato["objetivo"])] == CODIGO
    assert ejecutor.call_count == 1


class ClienteCorreccionSintaxis(ClienteJUnitGrabado):
    """Respuesta inválida seguida de la corrección, con feedback observable y cero tokens."""

    def generar(self, prompt: str, rol: str = "generator"):
        """Conserva la aserción y corrige únicamente la sintaxis en el segundo intento."""
        self.codigo = (
            CODIGO.replace("assertEquals(4,", "assertEquals(4 ")
            if not self.prompts
            else CODIGO
        )
        return super().generar(prompt, rol)


def test_orquestador_real_devuelve_error_de_sintaxis_al_generator(
    tmp_path: Path, monkeypatch
) -> None:
    """Planner, Generator, Reviewer y reintento reales; solo LLM y runner están simulados."""
    contrato = preparar(tmp_path)
    [modulo] = JavaAdapter().analizar(tmp_path)["modulos"]
    adaptador = AdaptadorConPuertoEjecucionSimulado()
    monkeypatch.setattr(
        "qagent.agents.reviewer.adaptador_de_contrato", lambda contrato: adaptador
    )
    tracker = TokenTracker()
    planner = PlannerAgent(
        FakeLLMClient(grabaciones={"Banco.java::Banco.duplicar": contrato["casos"]}),
        tracker,
        es_simulado=True,
        adaptador=JavaAdapter(),
    )
    cliente = ClienteCorreccionSintaxis()
    generator = GeneratorAgent(
        cliente, tracker, es_simulado=True, ruta_proyecto=tmp_path
    )
    ejecutor = ejecutor_grabado()
    reviewer = ReviewerAgent(tracker, tmp_path, "sin-uso", ejecutor=ejecutor)
    resultado = Orquestador(planner, generator, reviewer, tracker=tracker).ejecutar(
        modulo
    )
    [objetivo] = resultado.objetivos
    assert objetivo.decision == "accept", resultado.motivo_fallo
    assert objetivo.intentos == 2
    assert objetivo.revisiones[0]["tipo_fallo"] == "error_test"
    assert objetivo.revisiones[0]["decision"] == "retry"
    assert objetivo.revisiones[0]["feedback"] in cliente.prompts[1]
    assert objetivo.laundering_detectado is False
    assert len(cliente.prompts) == 2
    assert ejecutor.call_count == 1
    assert tracker.total_tokens == 0
