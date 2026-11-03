"""Oráculos Java ligados a casos reales del contrato, sin ejecutar Java (#184)."""

from pathlib import Path

import pytest

from qagent.lenguajes import JavaAdapter
from qagent.lenguajes.java_oraculo import validar_java
from tests.agents.test_generator_java import CODIGO, FUENTE, preparar


def test_acepta_resultado_del_metodo_con_entrada_y_esperado_correctos(
    tmp_path: Path,
) -> None:
    """El contrato, no el cuerpo de producción, determina el esperado de la aserción."""
    contrato = preparar(tmp_path, FUENTE.replace("return x * 2;", "return 999;"))
    assert JavaAdapter().validar_oraculo(contrato, CODIGO, tmp_path) is None


@pytest.mark.parametrize(
    "codigo",
    [
        CODIGO.replace("assertEquals(4,", "assertEquals(5,"),
        CODIGO.replace("duplicar(2)", "duplicar(3)"),
        CODIGO.replace("Banco.duplicar(2)", "4"),
        CODIGO.replace("Banco.duplicar", "Otra.duplicar"),
        CODIGO.replace("class BancoTest", "class OtroTest"),
        CODIGO.replace("package ejemplo;", "package otro;"),
        CODIGO.replace("package ejemplo;", "package ejemplo; import otro.Banco;"),
        CODIGO.replace(
            "class BancoTest {", "class BancoTest extends otro.Aserciones {"
        ),
        CODIGO.replace("class BancoTest {", "class BancoTest { { Otra.preparar(); }"),
        CODIGO.replace("org.junit.jupiter.api.Test", "falso.Test"),
        CODIGO.replace(
            "assertEquals(4, Banco.duplicar(2));",
            "assert false; assertEquals(4, Banco.duplicar(2));",
        ),
        CODIGO.replace(
            "assertEquals(4, Banco.duplicar(2));",
            "Otra.preparar(); assertEquals(4, Banco.duplicar(2));",
        ),
        CODIGO.replace(
            "assertEquals(4, Banco.duplicar(2));",
            "int otraLlamada = Banco.duplicar(3); assertEquals(4, Banco.duplicar(2));",
        ),
        CODIGO.replace(
            "assertEquals(4, Banco.duplicar(2));",
            "assertEquals(4, Banco.duplicar(2), Otra.mensaje());",
        ),
        CODIGO.replace("org.junit.jupiter.api.Assertions", "falso.Assertions"),
        CODIGO.replace("assertEquals(4, Banco.duplicar(2));", ""),
        CODIGO.replace(
            "assertEquals(4, Banco.duplicar(2));",
            "if (false) { assertEquals(4, Banco.duplicar(2)); }",
        ),
        CODIGO.replace(
            "assertEquals(4, Banco.duplicar(2));",
            'assertEquals(4, Banco.duplicar(2)); org.junit.jupiter.api.Assertions.fail("ajeno");',
        ),
        CODIGO.replace("@Test void", "@Test private void"),
        CODIGO.replace("@Test void", "@Test static void"),
        CODIGO.replace("@Test void", "@Test @org.junit.jupiter.api.Disabled void"),
        CODIGO.replace(
            "assertEquals(4, Banco.duplicar(2));",
            "try { assertEquals(4, Banco.duplicar(2)); } catch (Exception e) {}",
        ),
        CODIGO.replace(
            "assertEquals(4, Banco.duplicar(2));",
            "Runnable despues = () -> { assertEquals(4, Banco.duplicar(2)); };",
        ),
        CODIGO.replace(
            "assertEquals(4, Banco.duplicar(2));",
            "assertEquals(4, Banco.duplicar(2)); assertEquals(0, 1);",
        ),
        CODIGO.replace(
            "assertEquals(4, Banco.duplicar(2));",
            "int valor = Banco.duplicar(2); valor = 4; assertEquals(4, valor);",
        ),
        CODIGO.replace(
            "assertEquals(4, Banco.duplicar(2));",
            "assertEquals(4, envoltura(Banco.duplicar(2)));",
        ),
    ],
)
def test_rechaza_oraculos_no_demostrables_antes_de_ejecutar(
    tmp_path: Path, codigo: str
) -> None:
    """Tautologías, llamadas ajenas, cambios y evasiones no prueban el contrato."""
    contrato = preparar(tmp_path)
    error = JavaAdapter().validar_oraculo(contrato, codigo, tmp_path)
    assert error is not None
    assert error.startswith("Oráculo inválido:")


@pytest.mark.parametrize(
    "reemplazo",
    [
        "int resultado = Banco.duplicar(2); assertEquals(4, resultado);",
        "int entrada = 2; int esperado = 4; assertEquals(esperado, Banco.duplicar(entrada));",
        "assertEquals(4.0, Banco.duplicar(2), 0.000001);",
        "assertEquals(4, /* comentario */ Banco.duplicar(2));",
    ],
)
def test_acepta_alias_estables_mensajes_y_tolerancia_acotada(
    tmp_path: Path, reemplazo: str
) -> None:
    """El análisis sigue datos literales y resultados locales sin ejecutar expresiones."""
    fuente = (
        FUENTE.replace("public static int duplicar", "public static double duplicar")
        if "0.000001" in reemplazo
        else FUENTE
    )
    contrato = preparar(tmp_path, fuente)
    codigo = CODIGO.replace("assertEquals(4, Banco.duplicar(2));", reemplazo)
    assert JavaAdapter().validar_oraculo(contrato, codigo, tmp_path) is None


def test_tolerancia_no_puede_anular_la_comparacion(tmp_path: Path) -> None:
    """Una tolerancia enorme no convierte cualquier resultado en aprobación."""
    contrato = preparar(
        tmp_path,
        FUENTE.replace("public static int duplicar", "public static double duplicar"),
    )
    codigo = CODIGO.replace(
        "assertEquals(4, Banco.duplicar(2));",
        "assertEquals(4.0, Banco.duplicar(2), 100.0);",
    )
    assert JavaAdapter().validar_oraculo(contrato, codigo, tmp_path) is not None


@pytest.mark.parametrize(
    "cuerpo",
    [
        "assertThrows(IllegalArgumentException.class, () -> Banco.duplicar(-1));",
        "assertThrows(IllegalArgumentException.class, () -> { Banco.duplicar(-1); });",
    ],
)
def test_excepcion_se_comprueba_en_la_llamada_del_caso(
    tmp_path: Path, cuerpo: str
) -> None:
    """La excepción debe ser la del contrato y la lambda solo llama al objetivo."""
    contrato = preparar(tmp_path)
    contrato["casos"][0].pop("valor_esperado")
    contrato["casos"][0].update(
        entrada={"x": -1}, excepcion="IllegalArgumentException", categoria="error"
    )
    codigo = CODIGO.replace(
        "import static org.junit.jupiter.api.Assertions.assertEquals;",
        "import static org.junit.jupiter.api.Assertions.assertThrows;",
    )
    codigo = codigo.replace("assertEquals(4, Banco.duplicar(2));", cuerpo)
    assert JavaAdapter().validar_oraculo(contrato, codigo, tmp_path) is None
    assert (
        JavaAdapter().validar_oraculo(
            contrato,
            codigo.replace("IllegalArgumentException.class", "Exception.class"),
            tmp_path,
        )
        is not None
    )


def preparar_mockito(tmp_path: Path) -> tuple[dict, str]:
    """Clase de producción con dependencia de constructor y test Mockito declarativo."""
    fuente = FUENTE.replace(
        "public class Banco {",
        "import dependencias.Repositorio;\npublic class Banco { public Banco(Repositorio repo) {}",
    )
    fuente = fuente.replace("public static int duplicar", "public int duplicar")
    contrato = preparar(tmp_path, fuente)
    codigo = CODIGO.replace(
        "class BancoTest",
        "import dependencias.Repositorio;\nimport static org.mockito.Mockito.*;\nclass BancoTest",
    )
    codigo = codigo.replace(
        "assertEquals(4, Banco.duplicar(2));",
        "Repositorio repo = mock(Repositorio.class); Banco banco = new Banco(repo); assertEquals(4, banco.duplicar(2));",
    )
    return contrato, codigo


def test_mockito_solo_sustituye_dependencia_del_constructor(tmp_path: Path) -> None:
    """Se conserva la instancia real y el mock se entrega al constructor declarado."""
    contrato, codigo = preparar_mockito(tmp_path)
    assert JavaAdapter().validar_oraculo(contrato, codigo, tmp_path) is None
    con_stub = codigo.replace(
        "assertEquals(4, banco.duplicar(2));",
        "when(repo.obtener(2)).thenReturn(4); assertEquals(4, banco.duplicar(2));",
    )
    assert JavaAdapter().validar_oraculo(contrato, con_stub, tmp_path) is None


@pytest.mark.parametrize(
    ("original", "reemplazo"),
    [
        ("new Banco(repo)", "mock(Banco.class)"),
        ("new Banco(repo)", "spy(new Banco(repo))"),
        ("mock(Repositorio.class)", "mock(OtraDependencia.class)"),
        (
            "assertEquals(4, banco.duplicar(2));",
            "Repositorio otro = mock(Repositorio.class); assertEquals(4, banco.duplicar(2));",
        ),
        (
            "assertEquals(4, banco.duplicar(2));",
            "when(banco.duplicar(2)).thenReturn(4); assertEquals(4, banco.duplicar(2));",
        ),
        (
            "assertEquals(4, banco.duplicar(2));",
            "mockStatic(Banco.class); assertEquals(4, banco.duplicar(2));",
        ),
    ],
)
def test_rechaza_mock_o_stub_del_objetivo_y_dependencias_inventadas(
    tmp_path: Path, original: str, reemplazo: str
) -> None:
    """Los mocks no pueden reemplazar el comportamiento que se intenta comprobar."""
    contrato, codigo = preparar_mockito(tmp_path)
    assert (
        JavaAdapter().validar_oraculo(
            contrato, codigo.replace(original, reemplazo), tmp_path
        )
        is not None
    )


@pytest.mark.parametrize(
    ("retorno", "implementacion", "esperado", "correcta", "incorrecta"),
    [
        (
            "boolean",
            "return x > 0;",
            True,
            "assertTrue(Banco.duplicar(2));",
            "assertTrue(true);",
        ),
        (
            "String",
            'return "a";',
            "a",
            'assertEquals("a", Banco.duplicar(2));',
            "assertEquals('a', Banco.duplicar(2));",
        ),
        (
            "char",
            "return 'a';",
            "a",
            "assertEquals('a', Banco.duplicar(2));",
            'assertEquals("a", Banco.duplicar(2));',
        ),
        (
            "String",
            "return null;",
            None,
            "assertNull(Banco.duplicar(2));",
            "assertNotNull(Banco.duplicar(2));",
        ),
        (
            "List<Integer>",
            "return List.of(x, x + 1);",
            [2, 3],
            "assertEquals(List.of(2, 3), Banco.duplicar(2));",
            "assertEquals(new int[]{2, 3}, Banco.duplicar(2));",
        ),
        (
            "int[]",
            "return new int[]{x, x + 1};",
            [2, 3],
            "assertArrayEquals(new int[]{2, 3}, Banco.duplicar(2));",
            "assertEquals(new int[]{2, 3}, Banco.duplicar(2));",
        ),
        (
            "long",
            "return 9007199254740993L;",
            9007199254740993,
            "assertEquals(9007199254740993L, Banco.duplicar(2));",
            "assertEquals(9007199254740993.0, Banco.duplicar(2));",
        ),
    ],
)
def test_forma_de_asercion_respeta_tipos_y_no_solo_literales(
    tmp_path: Path,
    retorno: str,
    implementacion: str,
    esperado,
    correcta: str,
    incorrecta: str,
) -> None:
    """No confunde igualdad de arrays, char/String, tautologías ni enteros redondeados."""
    fuente = (
        "package ejemplo; import java.util.List; public class Banco { public static "
        + retorno
        + " duplicar(int x) { "
        + implementacion
        + " } }"
    )
    contrato = preparar(tmp_path, fuente)
    contrato["casos"][0]["valor_esperado"] = esperado
    codigo = CODIGO.replace(
        "import static org.junit.jupiter.api.Assertions.assertEquals;",
        "import static org.junit.jupiter.api.Assertions.*;\nimport java.util.List;",
    )
    codigo = codigo.replace("assertEquals(4, Banco.duplicar(2));", correcta)
    assert JavaAdapter().validar_oraculo(contrato, codigo, tmp_path) is None
    assert (
        JavaAdapter().validar_oraculo(
            contrato, codigo.replace(correcta, incorrecta), tmp_path
        )
        is not None
    )


def test_constructor_protegido_es_accesible_en_el_mismo_paquete(tmp_path: Path) -> None:
    """El guardrail respeta el acceso protected desde el paquete de la fuente."""
    contrato, codigo = preparar_mockito(tmp_path)
    archivo = tmp_path / contrato["modulo"]
    archivo.write_text(
        archivo.read_text(encoding="utf-8").replace(
            "public Banco(Repositorio", "protected Banco(Repositorio"
        ),
        encoding="utf-8",
    )
    assert JavaAdapter().validar_oraculo(contrato, codigo, tmp_path) is None


def test_import_de_dependencia_homonima_no_sustituye_la_declarada(
    tmp_path: Path,
) -> None:
    """El mismo nombre simple en otro paquete no prueba la dependencia de la fuente."""
    contrato, codigo = preparar_mockito(tmp_path)
    assert (
        JavaAdapter().validar_oraculo(
            contrato,
            codigo.replace(
                "import dependencias.Repositorio;", "import falsa.Repositorio;"
            ),
            tmp_path,
        )
        is not None
    )

    assert (
        JavaAdapter().validar_oraculo(
            contrato,
            codigo.replace("mock(Repositorio.class)", "mock(falsa.Repositorio.class)"),
            tmp_path,
        )
        is not None
    )


def test_un_error_de_analisis_sin_mensaje_no_aprueba_el_test(monkeypatch) -> None:
    """El guardrail falla cerrado incluso si una dependencia lanza un error vacío."""

    def fallar(codigo):
        raise ValueError()

    monkeypatch.setattr("qagent.lenguajes.java_oraculo.analizar_junit", fallar)
    error = validar_java({}, CODIGO)
    assert error is not None
    assert error.startswith("Oráculo inválido:")
