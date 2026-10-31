"""Diagnósticos JUnit Java #182: fixtures sintéticas y XML real previo, sin JVM."""

from pathlib import Path
from xml.sax.saxutils import quoteattr

import pytest

from qagent.lenguajes import JavaAdapter
from qagent.sandbox.informe_pytest import LIMITE_TRAZA, JUnitInvalido, resumir_ejecucion
from qagent.sandbox.modelos import LimitesSandbox, ResultadoSandbox

FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures/java/junit5-fallos-controlados.xml"
)


def test_informe_real_del_promedio_obtenido_en_docker() -> None:
    """Reproduce el fallo real del banco sin necesitar Docker ni ejecutar Java."""
    ruta = FIXTURE.with_name("junit5-sandbox-promedio.xml")
    informe = JavaAdapter().interpretar_resultados(ruta.read_text(encoding="utf-8"))
    assert informe["total"] == informe["fallaron"] == 1
    assert informe["errores"] == informe["pasaron"] == informe["omitidos"] == 0
    [caso] = informe["casos"]
    assert (caso["esperado"], caso["obtenido"]) == ("2.5", "2.0")
    assert (caso["archivo"], caso["linea"]) == ("BancoControladoTest.java", 5)


def _xml(mensaje: str, traza: str = "") -> str:
    """Construye una comparación sintética sin afirmar ejecución real de JUnit."""
    return (
        '<testsuite><testcase classname="ejemplo.BancoTest" name="caso">'
        f'<failure type="org.opentest4j.AssertionFailedError" message={quoteattr(mensaje)}>{traza}</failure>'
        "</testcase></testsuite>"
    )


def test_fixture_separa_estados_y_ubica_la_prueba() -> None:
    """El reporte conserva fallo, error y omisión y elige el marco de la clase de prueba."""
    resultado = JavaAdapter().interpretar_resultados(
        FIXTURE.read_text(encoding="utf-8")
    )
    assert (
        resultado["pasaron"],
        resultado["fallaron"],
        resultado["errores"],
        resultado["omitidos"],
    ) == (1, 1, 1, 1)
    correcto, fallo, error, omitido = resultado["casos"]
    assert correcto["esperado"] is correcto["obtenido"] is None
    assert (fallo["esperado"], fallo["obtenido"], fallo["operador"]) == (
        "2.5",
        "2.0",
        "==",
    )
    assert fallo["tipo_error"] == "org.opentest4j.AssertionFailedError"
    assert (fallo["archivo"], fallo["linea"]) == ("BancoTest.java", 24)
    assert fallo["pila"][0]["archivo"] == "AssertionFailureBuilder.java"
    assert error["tipo_error"] == "java.lang.IllegalStateException"
    assert error["esperado"] is error["obtenido"] is None
    assert (error["archivo"], error["linea"]) == ("BancoTest.java", 35)
    assert omitido["mensaje"] == "No habilitado"


@pytest.mark.parametrize(
    ("mensaje", "esperado", "obtenido"),
    [
        ("expected: <3> but was: <2>", "3", "2"),
        (
            "Mensaje personalizado ==> expected: <true> but was: <false>",
            "true",
            "false",
        ),
        ("expected: <[1, 2]> but was: <[1, 3]>", "[1, 2]", "[1, 3]"),
        ("expected: <null> but was: <texto>", "null", "texto"),
        ("expected: <a\nb> but was: <c\nd>", "a\nb", "c\nd"),
    ],
)
def test_comparaciones_conservan_texto_sin_evaluarlo(
    mensaje: str, esperado: str, obtenido: str
) -> None:
    """Números, booleanos, null, listas y textos multilínea siguen siendo strings."""
    [caso] = JavaAdapter().interpretar_resultados(_xml(mensaje))["casos"]
    assert caso["esperado"] == esperado
    assert caso["obtenido"] == obtenido


@pytest.mark.parametrize(
    "mensaje",
    [
        "Resultado inesperado",
        "expected: not equal but was: 2",
        "expected: <a> but was: <b> but was: <c>",
    ],
)
def test_comparacion_desconocida_o_ambigua_no_inventa_valores(mensaje: str) -> None:
    """Un formato no reconocido conserva el diagnóstico sin deducir una aserción."""
    [caso] = JavaAdapter().interpretar_resultados(_xml(mensaje))["casos"]
    assert caso["mensaje"] == mensaje
    assert caso["esperado"] is caso["obtenido"] is caso["operador"] is None


def test_assertthrows_que_no_lanza() -> None:
    """La falta de una excepción se presenta como la reporta JUnit, sin ejecutar nada."""
    mensaje = "Expected java.lang.IllegalArgumentException to be thrown, but nothing was thrown."
    [caso] = JavaAdapter().interpretar_resultados(_xml(mensaje))["casos"]
    assert caso["esperado"] == "se lanza java.lang.IllegalArgumentException"
    assert caso["obtenido"] == "no se lanzó ninguna excepción"
    assert caso["operador"] == "throws"


def test_marcos_sin_linea_y_clases_internas() -> None:
    """Native/Unknown Source no reciben líneas inventadas; la clase interna usa su fuente."""
    xml = _xml(
        "falló",
        "at ejemplo.BancoTest$Interna.caso(BancoTest.java:18)\nat java.base/java.lang.Method.invoke(Unknown Source)\nat Sistema.nativa(Native Method)",
    )
    xml = xml.replace(
        'classname="ejemplo.BancoTest"', 'classname="ejemplo.BancoTest$Interna"'
    )
    [caso] = JavaAdapter().interpretar_resultados(xml)["casos"]
    assert (caso["archivo"], caso["linea"]) == ("BancoTest.java", 18)
    assert len(caso["pila"]) == 1
    assert "Unknown Source" in caso["traza"]


def test_traza_larga_esta_acotada() -> None:
    """Se limita la traza y los marcos sin abrir las fuentes que menciona el informe."""
    traza = "\n".join(
        f"at ejemplo.BancoTest.caso(BancoTest.java:{i + 1})" for i in range(1000)
    )
    [caso] = JavaAdapter().interpretar_resultados(_xml("falló", traza))["casos"]
    assert len(caso["pila"]) <= 128
    assert len(caso["traza"]) < LIMITE_TRAZA + 100


@pytest.mark.parametrize(
    "xml",
    [
        "<testsuites/>",
        "<testsuite/>",
        '<testsuite time="NaN"><testcase/></testsuite>',
        '<testsuite><testcase time="Infinity"/></testsuite>',
        '<testsuite time="-1"><testcase/></testsuite>',
        '<testsuite time="desconocido"><testcase/></testsuite>',
        "<testsuite><grupo><testcase/></grupo></testsuite>",
        "<testsuite><testcase><failure/><error/></testcase></testsuite>",
        "<testsuite><testcase><failure/><skipped/></testcase></testsuite>",
    ],
)
def test_informe_inconsistente_no_es_exito(xml: str) -> None:
    """Duraciones inválidas, cero casos y estados incompatibles se rechazan."""
    with pytest.raises(JUnitInvalido):
        JavaAdapter().interpretar_resultados(xml)


def test_resumen_comun_conserva_diagnosticos_java() -> None:
    """El resumen usado por Reviewer recibe casos enriquecidos sin alterar sus totales."""
    resultado = ResultadoSandbox(
        1, "JUnit terminó con fallos", "", junit_xml=FIXTURE.read_text(encoding="utf-8")
    )
    resumen = resumir_ejecucion(
        resultado,
        imagen="qagent-sandbox:java",
        comando=["mvn", "test"],
        limites=LimitesSandbox(),
        interpretar=JavaAdapter().interpretar_resultados,
    )
    assert resumen["exit_code"] == 1
    assert resumen["totales"] == {
        "total": 4,
        "pasaron": 1,
        "fallaron": 1,
        "errores": 1,
        "omitidos": 1,
    }
    assert resumen["casos"][1]["obtenido"] == "2.0"
