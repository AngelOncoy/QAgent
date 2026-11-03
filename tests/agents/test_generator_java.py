"""Generator compartido con respuestas Java grabadas: sin API, Docker ni javac (#184)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qagent import contracts
from qagent.agents.generator import ErrorRespuestaGenerator, GeneratorAgent
from qagent.agents.reviewer import ReviewerAgent
from qagent.lenguajes import JavaAdapter
from qagent.llm import RespuestaLLM, TokenTracker

FUENTE = """package ejemplo;
public class Banco {
    /** Devuelve el doble. @return dos veces x */
    public static int duplicar(int x) { return x * 2; }
}
"""
CODIGO = """package ejemplo;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
class BancoTest {
    /** Comprueba el doble de dos según el contrato del Planner. */
    @Test void test_positivo() { assertEquals(4, Banco.duplicar(2)); }
}
"""


class ClienteJUnitGrabado:
    """Entrega una respuesta conocida y registra prompts; no llama a proveedores."""

    def __init__(self, codigo: str = CODIGO) -> None:
        self.codigo = codigo
        self.prompts: list[str] = []

    def generar(self, prompt: str, rol: str = "generator") -> RespuestaLLM:
        """Devuelve el código grabado con cero tokens y costo cero."""
        assert rol == "generator"
        self.prompts.append(prompt)
        return RespuestaLLM(
            contenido=self.codigo,
            modelo="fake-junit",
            tokens_entrada=0,
            tokens_salida=0,
            costo_usd=0,
        )


def preparar(
    tmp_path: Path, fuente: str = FUENTE, objetivo: str = "Banco.duplicar"
) -> dict:
    """Construye el contrato con firma y huella reales; el esperado es independiente."""
    archivo = tmp_path / "src/main/java/ejemplo/Banco.java"
    archivo.parent.mkdir(parents=True)
    archivo.write_text(fuente, encoding="utf-8")
    [modulo] = JavaAdapter().analizar(tmp_path)["modulos"]
    funcion = next(f for f in modulo["funciones"] if f["nombre"] == objetivo)
    return {
        "version": "3",
        "lenguaje": "java",
        "framework_pruebas": "junit5",
        "modulo": modulo["ruta"],
        "huella": modulo["huella"],
        "tipo": "funcion",
        "objetivo": objetivo,
        "firma": funcion["firma"],
        "critical": False,
        "llama_a": [],
        "casos": [
            {
                "id": "positivo",
                "entrada": {"x": 2},
                "valor_esperado": 4,
                "origen": "docstring",
                "categoria": "normal",
            }
        ],
    }


def test_generator_real_emite_v2_junit_y_ruta_de_paquete(tmp_path: Path) -> None:
    """Genera el contrato real con el adaptador registrado, sin sustituir el Generator."""
    contrato = preparar(tmp_path)
    cliente = ClienteJUnitGrabado()
    tracker = TokenTracker()
    resultado = GeneratorAgent(
        cliente, tracker, es_simulado=True, ruta_proyecto=tmp_path
    ).generar(contrato, 1, None)
    contracts.validar_versionado(contracts.FAMILIA_GENERATED_TEST, resultado)
    assert resultado["version"] == "2"
    assert resultado["lenguaje"] == "java"
    assert resultado["framework_pruebas"] == "junit5"
    assert resultado["archivo"] == "src/test/java/ejemplo/BancoTest.java"
    assert resultado["codigo"] == CODIGO
    assert resultado["casos_cubiertos"] == ["positivo"]
    assert tracker.total_tokens == 0
    assert len(tracker.llamadas) == 1
    assert tracker.llamadas[0].es_simulado is True
    assert not (
        tmp_path / "src/test"
    ).exists()  # El Generator no escribe ni ejecuta Java.


def test_prompt_conserva_oraculo_y_limita_mockito_a_constructor(tmp_path: Path) -> None:
    """El prompt limita mocks a dependencias y conserva los casos del Planner."""
    contrato = preparar(tmp_path)
    cliente = ClienteJUnitGrabado()
    GeneratorAgent(cliente, TokenTracker(), ruta_proyecto=tmp_path).generar(
        contrato, 2, "Corrige únicamente el import de Test."
    )
    [prompt] = cliente.prompts
    assert "JUnit 5" in prompt and "Mockito" in prompt
    assert "únicamente para objetos de dependencia que recibe el constructor" in prompt
    assert "No hagas mock/spy de la clase probada" in prompt
    assert "assertThrows" in prompt and "assertEquals(esperado, obtenido)" in prompt
    assert "intento 2" in prompt and "Corrige únicamente el import de Test." in prompt
    contenido = prompt.split("CONTRATO_JSON: ", 1)[1]
    assert json.loads(contenido) == contrato


def test_prompt_incluye_constructor_sin_enviar_su_cuerpo(tmp_path: Path) -> None:
    """Se extraen firmas y dependencias del AST, sin filtrar el código al oráculo."""
    fuente = """package ejemplo;
import dependencias.Repositorio;
public class Banco {
 public Banco(Repositorio repo) { System.out.println("SECRETO_CONSTRUCTOR"); }
 /** Devuelve el doble. @implNote SECRETO_IMPL */
 public int duplicar(int x) { return 999; /* SECRETO_CUERPO */ }
}
"""
    contrato = preparar(tmp_path, fuente)
    prompt = JavaAdapter().prompt_generator(contrato, 1, None, tmp_path)
    assert "Repositorio" in prompt
    assert "public Banco(Repositorio repo)" in prompt
    assert all(
        secreto not in prompt
        for secreto in (
            "SECRETO_CONSTRUCTOR",
            "SECRETO_IMPL",
            "SECRETO_CUERPO",
            "return 999",
        )
    )


def test_generator_conserva_junit_con_dependencia_mockeada_en_constructor(
    tmp_path: Path,
) -> None:
    """El artefacto JUnit instancia la clase real y simula solo su dependencia declarada."""
    fuente = FUENTE.replace(
        "public class Banco {",
        "import dependencias.Repositorio;\npublic class Banco { public Banco(Repositorio repo) {}",
    )
    fuente = fuente.replace("public static int duplicar", "public int duplicar")
    contrato = preparar(tmp_path, fuente)
    codigo = CODIGO.replace(
        "class BancoTest",
        "import dependencias.Repositorio;\nimport static org.mockito.Mockito.mock;\nclass BancoTest",
    )
    codigo = codigo.replace(
        "assertEquals(4, Banco.duplicar(2));",
        "Repositorio repo = mock(Repositorio.class); Banco banco = new Banco(repo); assertEquals(4, banco.duplicar(2));",
    )
    resultado = GeneratorAgent(
        ClienteJUnitGrabado(codigo),
        TokenTracker(),
        es_simulado=True,
        ruta_proyecto=tmp_path,
    ).generar(contrato, 1, None)
    assert resultado["codigo"] == codigo
    assert "new Banco(repo)" in resultado["codigo"]
    assert "mock(Repositorio.class)" in resultado["codigo"]
    assert "mock(Banco.class)" not in resultado["codigo"]
    contracts.validar_versionado(contracts.FAMILIA_GENERATED_TEST, resultado)


@pytest.mark.parametrize("excepcion", [False, True])
def test_generator_conserva_booleanos_y_excepciones_del_contrato(
    tmp_path: Path, excepcion: bool
) -> None:
    """Conserva assertTrue o assertThrows según el contrato, sin calcular nuevos esperados."""
    fuente = FUENTE.replace(
        "public static int duplicar(int x)", "public static boolean duplicar(int x)"
    ).replace("return x * 2;", "return x > 0;")
    contrato = preparar(tmp_path, fuente)
    if excepcion:
        contrato["casos"][0].pop("valor_esperado")
        contrato["casos"][0].update(
            excepcion="IllegalArgumentException", categoria="error"
        )
        codigo = CODIGO.replace(
            "import static org.junit.jupiter.api.Assertions.assertEquals;",
            "import static org.junit.jupiter.api.Assertions.assertThrows;",
        )
        codigo = codigo.replace(
            "assertEquals(4, Banco.duplicar(2));",
            "assertThrows(IllegalArgumentException.class, () -> Banco.duplicar(2));",
        )
    else:
        contrato["casos"][0]["valor_esperado"] = True
        codigo = CODIGO.replace(
            "import static org.junit.jupiter.api.Assertions.assertEquals;",
            "import static org.junit.jupiter.api.Assertions.assertTrue;",
        )
        codigo = codigo.replace(
            "assertEquals(4, Banco.duplicar(2));", "assertTrue(Banco.duplicar(2));"
        )
    resultado = GeneratorAgent(
        ClienteJUnitGrabado(codigo),
        TokenTracker(),
        es_simulado=True,
        ruta_proyecto=tmp_path,
    ).generar(contrato, 1, None)
    assert resultado["codigo"] == codigo
    assert resultado["casos_cubiertos"] == ["positivo"]
    contracts.validar_versionado(contracts.FAMILIA_GENERATED_TEST, resultado)


def test_paquete_se_lee_del_ast_y_no_del_directorio(tmp_path: Path) -> None:
    """Una fuente ubicada en ejemplo puede declarar otro paquete; se respeta el AST."""
    contrato = preparar(
        tmp_path, FUENTE.replace("package ejemplo;", "package otro.paquete;")
    )
    assert (
        JavaAdapter().archivo_para_contrato(contrato, tmp_path)
        == "src/test/java/otro/paquete/BancoTest.java"
    )


@pytest.mark.parametrize("salto", ["\n", "\r\n", "\r"])
def test_firma_multilinea_no_cambia_por_saltos_de_linea(
    tmp_path: Path, salto: str
) -> None:
    """La lectura del contexto y la del analizador coinciden con LF, CRLF y CR."""
    fuente = FUENTE.replace("duplicar(int x)", "duplicar(\n        int x\n    )")
    contrato = preparar(tmp_path, fuente)
    archivo = tmp_path / contrato["modulo"]
    archivo.write_bytes(fuente.replace("\n", salto).encode("utf-8"))
    resultado = GeneratorAgent(
        ClienteJUnitGrabado(), TokenTracker(), es_simulado=True, ruta_proyecto=tmp_path
    ).generar(contrato, 1, None)
    assert resultado["archivo"] == "src/test/java/ejemplo/BancoTest.java"
    assert resultado["codigo"] == CODIGO
    assert JavaAdapter().validar_oraculo(contrato, CODIGO, tmp_path) is None


def test_java_sin_paquete_y_clase_anidada_conservan_rutas(tmp_path: Path) -> None:
    """El paquete por defecto no añade carpetas inventadas y una clase anidada se distingue."""
    contrato = preparar(tmp_path, FUENTE.replace("package ejemplo;", ""))
    assert (
        JavaAdapter().archivo_para_contrato(contrato, tmp_path)
        == "src/test/java/BancoTest.java"
    )
    assert (
        JavaAdapter().archivo_de_prueba("Exterior.Interior.f", paquete="a.b")
        == "src/test/java/a/b/Exterior_InteriorTest.java"
    )


@pytest.mark.parametrize(
    "objetivo", ["f", "../Banco.f", "Banco.f/otro", ".Banco.f", "Banco..f"]
)
def test_nombre_de_objetivo_no_puede_escapar_de_la_ruta(objetivo: str) -> None:
    """No convierte nombres mal formados en rutas de prueba."""
    with pytest.raises(ValueError):
        JavaAdapter().archivo_de_prueba(objetivo)


def test_error_de_sintaxis_retorna_codigo_para_reintento(tmp_path: Path) -> None:
    """Generator y Reviewer rechazan la sintaxis antes de tocar cualquier ejecutor."""
    contrato = preparar(tmp_path)
    invalido = CODIGO.replace("assertEquals(4,", "assertEquals(4 ")
    cliente = ClienteJUnitGrabado(invalido)
    generator = GeneratorAgent(
        cliente, TokenTracker(), es_simulado=True, ruta_proyecto=tmp_path
    )
    with pytest.raises(ErrorRespuestaGenerator) as error:
        generator.generar(contrato, 1, None)
    assert error.value.codigo == invalido
    reviewer = ReviewerAgent(
        TokenTracker(),
        tmp_path,
        "imagen-no-usada",
        ejecutor=lambda *args: pytest.fail("No debe ejecutar Java inválido."),
    )
    test = contracts.generated_test_para(contrato, 1, error.value.codigo)
    revision = reviewer.revisar(contrato, test, None)
    assert revision["decision"] == "retry"
    assert revision["tipo_fallo"] == "error_test"
    assert revision["hash_error"]
    assert "ejecucion" not in revision
    corregido = GeneratorAgent(
        ClienteJUnitGrabado(), TokenTracker(), ruta_proyecto=tmp_path
    ).generar(contrato, 2, revision["feedback"])
    assert corregido["intento"] == 2
    assert JavaAdapter().validar_sintaxis(corregido["codigo"]) == []


def test_contexto_faltante_o_firma_obsoleta_no_se_inventa(tmp_path: Path) -> None:
    """La generación necesita contexto y rechaza contratos que ya no corresponden."""
    contrato = preparar(tmp_path)
    with pytest.raises(ValueError, match="ruta_proyecto"):
        JavaAdapter().prompt_generator(contrato, 1, None, None)
    contrato["firma"] = "public static int duplicar(String x)"
    with pytest.raises(ValueError, match="firma"):
        JavaAdapter().archivo_para_contrato(contrato, tmp_path)


def test_constructor_privado_no_se_sustituye_por_mock_del_objetivo(
    tmp_path: Path,
) -> None:
    """No se inventa una instancia ni se recomienda mockear la clase probada."""
    fuente = FUENTE.replace(
        "public class Banco {", "public class Banco { private Banco() {}"
    )
    fuente = fuente.replace("public static int duplicar", "public int duplicar")
    contrato = preparar(tmp_path, fuente)
    with pytest.raises(ValueError, match="constructor accesible"):
        JavaAdapter().prompt_generator(contrato, 1, None, tmp_path)


def test_java_integrado_conserva_guardrail_obligatorio() -> None:
    """La ejecución integrada no permite aprobar contratos inválidos sin oráculo."""
    assert JavaAdapter().completo is True
    assert JavaAdapter().reglas_revision().validar_oraculo({}, CODIGO) is not None
