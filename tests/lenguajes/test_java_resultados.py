"""Verifica la lectura de JUnit XML sin ejecutar Java, Docker ni la red (EN-19)."""

from pathlib import Path

import pytest

from qagent.lenguajes import JavaAdapter
from qagent.sandbox.informe_pytest import LIMITE_XML, JUnitInvalido


def test_interpreta_estados_junit() -> None:
    """Espera un éxito, un fallo, un error y una omisión con sus trazas intactas."""
    xml = """<testsuite name="Banco" time="0.5" timestamp="2026-10-28T01:46:25">
    <testcase classname="BancoTest" name="correcto" time="0.1"/>
    <testcase classname="BancoTest" name="defecto" time="0.2">
      <failure message="expected: &lt;2.5&gt; but was: &lt;2.0&gt;"
               type="org.opentest4j.AssertionFailedError">at BancoTest.defecto(BancoTest.java:20)</failure>
    </testcase>
    <testcase classname="BancoTest" name="tecnico" time="0.1">
      <error message="Dependencia no disponible" type="java.lang.IllegalStateException">at BancoTest.tecnico(BancoTest.java:30)</error>
    </testcase>
    <testcase classname="BancoTest" name="omitido"><skipped message="No habilitado"/></testcase>
    </testsuite>"""
    resultado = JavaAdapter().interpretar_resultados(xml)
    assert {
        k: resultado[k] for k in ("total", "pasaron", "fallaron", "errores", "omitidos")
    } == {
        "total": 4,
        "pasaron": 1,
        "fallaron": 1,
        "errores": 1,
        "omitidos": 1,
    }
    assert resultado["duracion_s"] == 0.5
    assert resultado["inicio"] == "2026-10-28T01:46:25"
    assert [c["resultado"] for c in resultado["casos"]] == [
        "paso",
        "fallo",
        "error",
        "omitido",
    ]
    fallo = resultado["casos"][1]
    assert fallo["mensaje"] == "expected: <2.5> but was: <2.0>"
    assert fallo["traza"] == "at BancoTest.defecto(BancoTest.java:20)"
    # #182: se muestran los valores literales del diagnóstico, no se usan como oráculo.
    assert fallo["esperado"] == "2.5"
    assert fallo["obtenido"] == "2.0"
    assert fallo["tipo_error"] == "org.opentest4j.AssertionFailedError"
    assert fallo["archivo"] == "BancoTest.java"
    assert fallo["linea"] == 20


def test_agrega_suites_planas() -> None:
    """Dos suites Surefire producen dos casos y la suma de sus duraciones."""
    xml = """<testsuites>
    <testsuite name="A" time="0.1"><testcase classname="A" name="a"/></testsuite>
    <testsuite name="B" time="0.2"><testcase classname="B" name="b"/></testsuite>
    </testsuites>"""
    resultado = JavaAdapter().interpretar_resultados(xml)
    assert resultado["total"] == resultado["pasaron"] == 2
    assert resultado["duracion_s"] == pytest.approx(0.3)
    assert [c["ruta"] for c in resultado["casos"]] == ["A", "B"]


@pytest.mark.parametrize(
    "xml",
    [
        "",
        "<testsuite>",
        "<otraRaiz/>",
        '<!DOCTYPE x [<!ENTITY a "texto">]><testsuite/>',
        '<testsuite><testsuite><testcase name="duplicado"/></testsuite></testsuite>',
        "<testsuites><otro/></testsuites>",
    ],
)
def test_rechaza_informes_invalidos(xml: str) -> None:
    """XML inválido o inseguro debe lanzar JUnitInvalido, nunca éxito silencioso."""
    with pytest.raises(JUnitInvalido):
        JavaAdapter().interpretar_resultados(xml)


def test_rechaza_xml_demasiado_grande() -> None:
    """Un informe que supera el límite común no debe procesarse."""
    with pytest.raises(JUnitInvalido, match="demasiado grande"):
        JavaAdapter().interpretar_resultados(
            "<testsuite>" + " " * LIMITE_XML + "</testsuite>"
        )


def test_lee_fixture_de_ejecucion_real_del_banco() -> None:
    """Los informes Surefire de TA-01 contienen los once casos ejecutados.

    La fixture conserva suites y casos de una ejecución real; se retiraron las
    propiedades del entorno. Su lectura no requiere Maven ni ejecuta las pruebas.
    """
    ruta = (
        Path(__file__).resolve().parents[1] / "fixtures" / "java" / "junit5-banco.xml"
    )
    resultado = JavaAdapter().interpretar_resultados(ruta.read_text(encoding="utf-8"))
    assert resultado["total"] == resultado["pasaron"] == 11
    assert resultado["fallaron"] == resultado["errores"] == resultado["omitidos"] == 0
    assert len({(c["ruta"], c["nombre"]) for c in resultado["casos"]}) == 11
    assert sum(c["ruta"].endswith("BancoCorrectoTest") for c in resultado["casos"]) == 8
    assert (
        sum(c["ruta"].endswith("BancoDefectuosoTest") for c in resultado["casos"]) == 3
    )
