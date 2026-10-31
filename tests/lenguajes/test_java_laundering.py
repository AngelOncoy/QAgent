"""Assertion Laundering Java por AST: sin IA ni ejecución de los JUnit (#184)."""

import pytest

from qagent.lenguajes import JavaAdapter


def junit(cuerpo: str, imports: str = "", anotacion: str = "@Test") -> str:
    """Fuente JUnit controlada para probar diferencias, no para ejecutar Java."""
    return (
        "import org.junit.jupiter.api.Test;\nimport static org.junit.jupiter.api.Assertions.*;\n"
        + imports
        + "\nclass BancoTest { "
        + anotacion
        + " void test_caso() { "
        + cuerpo
        + " } }"
    )


BASE = junit("assertEquals(4, Banco.duplicar(2));")
THROWS = junit(
    "assertThrows(IllegalArgumentException.class, () -> Banco.duplicar(-1));"
)


@pytest.mark.parametrize(
    ("original", "reparado"),
    [
        (BASE, junit("Banco.duplicar(2);")),
        (BASE, junit("assertEquals(5, Banco.duplicar(2));")),
        (BASE, junit("assertNotNull(Banco.duplicar(2));")),
        (BASE, junit("assertTrue(true);")),
        (BASE, junit("assertEquals(4, Banco.duplicar(3));")),
        (BASE, junit("assertEquals(4, Otra.duplicar(2));")),
        (THROWS, junit("Banco.duplicar(-1);")),
        (THROWS, junit("try { Banco.duplicar(-1); } catch (Exception ignorada) {}")),
        (THROWS, junit("assertThrows(Exception.class, () -> Banco.duplicar(-1));")),
        (
            THROWS,
            junit(
                "assertThrows(IllegalArgumentException.class, () -> { throw new IllegalArgumentException(); });"
            ),
        ),
        (BASE, junit("if (false) { assertEquals(4, Banco.duplicar(2)); }")),
        (
            BASE,
            junit("Runnable diferida = () -> { assertEquals(4, Banco.duplicar(2)); };"),
        ),
        (
            BASE,
            junit(
                "assertEquals(4, Banco.duplicar(2));",
                anotacion="@Test @org.junit.jupiter.api.Disabled",
            ),
        ),
        (
            BASE,
            junit(
                "org.junit.jupiter.api.Assumptions.assumeTrue(false); assertEquals(4, Banco.duplicar(2));"
            ),
        ),
        (BASE, junit('assertEquals(4, Banco.duplicar(2)); fail("fallo ajeno");')),
        (
            junit("assertEquals(4.0, Banco.duplicar(2), 0.000001);"),
            junit("assertEquals(4.0, Banco.duplicar(2), 100.0);"),
        ),
        (
            junit(
                "assertEquals(4, Banco.duplicar(2)); assertEquals(4, Banco.duplicar(2));"
            ),
            BASE,
        ),
        (BASE, BASE.replace("org.junit.jupiter.api.Assertions", "falso.Assertions")),
    ],
)
def test_detecta_cada_debilitamiento_y_evasion(original: str, reparado: str) -> None:
    """Cada transformación peligrosa produce una diferencia concreta y rechazo."""
    comparacion = JavaAdapter().comparar_aserciones(original, reparado)
    assert comparacion.es_laundering is True
    assert comparacion.diferencias
    assert "Assertion Laundering detectado" in comparacion.resumen


@pytest.mark.parametrize(
    ("original", "reparado"),
    [
        (BASE, BASE),
        (
            THROWS,
            THROWS.replace("() -> Banco.duplicar(-1)", "() -> { Banco.duplicar(-1); }"),
        ),
        (
            THROWS,
            THROWS.replace(
                "IllegalArgumentException.class",
                "java.lang.IllegalArgumentException.class",
            ),
        ),
        (
            junit("assertEquals(4.0, Banco.duplicar(2), 0.000001);"),
            junit("assertEquals(4.0, Banco.duplicar(2), 0.000000001);"),
        ),
        (BASE, BASE.replace("assertEquals(4,", "assertEquals( 4 , /* comentario */")),
        (BASE, junit("int resultado = Banco.duplicar(2); assertEquals(4, resultado);")),
        (
            junit(
                "int esperado = 4; int salida = Banco.duplicar(2); assertEquals(esperado, salida);"
            ),
            junit("int valor = Banco.duplicar(2); assertEquals(4, valor);"),
        ),
        (
            junit('assertEquals(4, Banco.duplicar(2), "mensaje anterior");'),
            junit('assertEquals(4, Banco.duplicar(2), "mensaje corregido");'),
        ),
        (
            junit(
                "assertEquals(4, Banco.duplicar(2)); assertEquals(6, Banco.duplicar(3));"
            ),
            junit(
                "assertEquals(6, Banco.duplicar(3)); assertEquals(4, Banco.duplicar(2));"
            ),
        ),
        (
            junit("assertEquals(4.0, Banco.duplicar(2));"),
            junit("assertEquals(4.00, Banco.duplicar(2));"),
        ),
    ],
)
def test_no_confunde_formato_mensajes_alias_y_orden_con_laundering(
    original: str, reparado: str
) -> None:
    """Las reparaciones que conservan la comprobación no provocan falsos positivos."""
    comparacion = JavaAdapter().comparar_aserciones(original, reparado)
    assert comparacion.es_laundering is False, comparacion.resumen
    assert comparacion.diferencias == ()


def test_literal_grande_no_se_redondea_al_compararlo() -> None:
    """La precisión del contexto Decimal no puede ocultar un esperado modificado."""
    original = junit(
        "assertEquals(123456789012345678901234567891L, Banco.duplicar(2));"
    )
    cambiado = original.replace("7891L", "7892L")
    assert JavaAdapter().comparar_aserciones(original, cambiado).es_laundering


def test_sintaxis_invalida_no_produce_una_comparacion_aprobada() -> None:
    """Un AST inválido no se presenta como ausencia de laundering."""
    with pytest.raises(SyntaxError):
        JavaAdapter().comparar_aserciones(
            BASE, BASE.replace("assertEquals(4,", "assertEquals(4 ")
        )
