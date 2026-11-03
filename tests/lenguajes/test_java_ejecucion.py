"""Preparación y comandos Java #182, sin lanzar Maven, Java ni Docker."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from qagent.lenguajes import JavaAdapter
from qagent.lenguajes.java_ejecucion import (
    POM,
    TARGET,
    TESTS,
    preparar_java,
    recoger_junit,
)
from qagent.sandbox.modelos import ErrorPreparacionSandbox

MODULO = "src/main/java/ejemplo/Banco.java"
POM_BASE = """<project xmlns="http://maven.apache.org/POM/4.0.0">
<modelVersion>4.0.0</modelVersion><groupId>ejemplo</groupId><artifactId>banco</artifactId><version>1</version>
<dependencies><dependency><groupId>org.ejemplo</groupId><artifactId>dependencia</artifactId><version>1.2</version></dependency></dependencies>
<build><plugins><plugin><groupId>org.apache.maven.plugins</groupId><artifactId>maven-compiler-plugin</artifactId><version>3.13.0</version><configuration><parameters>true</parameters></configuration></plugin>
<plugin><groupId>org.apache.maven.plugins</groupId><artifactId>maven-surefire-plugin</artifactId><version>3.5.2</version><configuration><argLine>-Dpropiedad=original</argLine><excludes><exclude>**/*</exclude></excludes></configuration></plugin>
</plugins></build></project>"""
CODIGO = """package ejemplo;
import org.junit.jupiter.api.Test;
public class BancoGeneradoTest {
  @Test void suma() { org.junit.jupiter.api.Assertions.assertEquals(3, Banco.sumar(1, 2)); }
}
"""


def crear_proyecto(tmp_path: Path) -> tuple[Path, Path]:
    """Crea una copia sintética y una única prueba recibida, sin ejecutar sus fuentes."""
    copia = tmp_path / "copia"
    archivo = copia / MODULO
    archivo.parent.mkdir(parents=True)
    archivo.write_text(
        "package ejemplo; public class Banco {public static int sumar(int a,int b) {return a+b;}}",
        encoding="utf-8",
    )
    (copia / "pom.xml").write_text(POM_BASE, encoding="utf-8")
    antigua = copia / "src/test/java/AntiguaTest.java"
    antigua.parent.mkdir(parents=True)
    antigua.write_text("class AntiguaTest {}", encoding="utf-8")
    pruebas = tmp_path / "pruebas"
    pruebas.mkdir()
    (pruebas / "recibida.java").write_text(CODIGO, encoding="utf-8")
    return copia, pruebas


@pytest.fixture
def proyecto(tmp_path: Path) -> tuple[Path, Path]:
    """Proyecto controlado compartido por las pruebas de preparación."""
    return crear_proyecto(tmp_path)


def test_preparacion_conserva_originales_y_aisla_las_salidas(proyecto) -> None:
    """Solo crea archivos reservados y conserva dependencias y configuración útil del usuario."""
    copia, pruebas = proyecto
    originales = {p: p.read_bytes() for p in copia.rglob("*") if p.is_file()}
    preparar_java(copia, pruebas)
    assert all(p.read_bytes() == contenido for p, contenido in originales.items())
    assert (copia / TESTS / "ejemplo/BancoGeneradoTest.java").read_text(
        encoding="utf-8"
    ) == CODIGO
    assert (copia / TESTS / "ejemplo/BancoGeneradoTest.java").read_bytes() == (
        pruebas / "recibida.java"
    ).read_bytes()
    texto = (copia / POM).read_text(encoding="utf-8")
    assert "<project " in texto  # Maven rechaza ns0:project.
    pom = ET.fromstring(texto)
    assert pom.findtext("{*}build/{*}directory") == "/work/proyecto/" + TARGET
    assert pom.findtext("{*}build/{*}testSourceDirectory") == "/work/proyecto/" + TESTS
    assert pom.findtext("{*}dependencies/{*}dependency/{*}artifactId") == "dependencia"
    plugins = {
        p.findtext("{*}artifactId"): p
        for p in pom.findall("{*}build/{*}plugins/{*}plugin")
    }
    assert (
        plugins["maven-compiler-plugin"].findtext("{*}configuration/{*}parameters")
        == "true"
    )
    surefire = plugins["maven-surefire-plugin"].find("{*}configuration")
    assert surefire.findtext("{*}test") == "ejemplo.BancoGeneradoTest"
    assert surefire.findtext("{*}reportsDirectory") == "/out/junit-raw"
    assert (
        surefire.findtext("{*}argLine") == "@{qagentJacocoArgLine} -Dpropiedad=original"
    )
    assert surefire.find("{*}excludes") is None
    assert surefire.findtext("{*}testFailureIgnore") == "false"
    jacoco = plugins["jacoco-maven-plugin"]
    assert jacoco.findtext("{*}configuration/{*}dataFile") == "/out/jacoco.exec"
    assert jacoco.findtext("{*}configuration/{*}propertyName") == "qagentJacocoArgLine"
    assert jacoco.find("{*}executions") is None


def test_comando_offline_separa_etapas_y_recoge_cobertura() -> None:
    """La fuente va como argumento independiente; la cobertura se intenta aun si JUnit falla."""
    comando = JavaAdapter().comando_pruebas(MODULO, "junit5")
    assert comando[:2] == ["sh", "-c"]
    script = comando[2]
    assert comando[3:] == ["qagent-java", MODULO]
    assert MODULO not in script
    assert "--offline" in script
    assert "-Dmaven.repo.local=/opt/qagent/m2" in script
    assert "QAGENT_JAVA_ETAPA=proyecto" in script
    assert "QAGENT_JAVA_ETAPA=prueba" in script
    assert script.index("ejecutar_maven compile") < script.index(
        "ejecutar_maven test-compile"
    )
    assert script.index("estado_test=$?") < script.index(":report")
    assert "cp /out/jacoco-report/jacoco.xml /out/jacoco.xml" in script
    assert script.rstrip().endswith('exit "$estado_test"')


@pytest.mark.parametrize(
    "modulo",
    [
        "Banco.java",
        "../Banco.java",
        "/src/main/java/Banco.java",
        "src/main/java/../Banco.java",
        "src/main/java/p;echo/Banco.java",
        "C:/Banco.java",
    ],
)
def test_comando_rechaza_rutas_incompatibles(modulo: str) -> None:
    """No convierte rutas ajenas al diseño Maven en un comando ambiguo."""
    with pytest.raises(ValueError):
        JavaAdapter().comando_pruebas(modulo)


def test_framework_incompatible_se_rechaza() -> None:
    """El adaptador no acepta pytest o Vitest para ejecutar una prueba Java."""
    with pytest.raises(ValueError):
        JavaAdapter().comando_pruebas(MODULO, "pytest")


@pytest.mark.parametrize("nombre", [POM, TESTS, TARGET])
def test_reservados_existentes_no_se_sobrescriben(proyecto, nombre: str) -> None:
    """Las rutas temporales preexistentes provocan un error de preparación del proyecto."""
    copia, pruebas = proyecto
    (copia / nombre).write_text("existente", encoding="utf-8")
    with pytest.raises(ErrorPreparacionSandbox, match="ETAPA=proyecto"):
        preparar_java(copia, pruebas)
    assert (copia / nombre).read_text(encoding="utf-8") == "existente"


@pytest.mark.parametrize(
    "insercion",
    ["<parent/>", "<modules><module>otro</module></modules>", "<modelVersion>"],
)
def test_pom_no_admitido_se_identifica_como_proyecto(proyecto, insercion: str) -> None:
    """Herencia, multimódulo o XML inválido no se atribuyen al código generado."""
    copia, pruebas = proyecto
    (copia / "pom.xml").write_text(
        POM_BASE.replace("</project>", insercion + "</project>"), encoding="utf-8"
    )
    with pytest.raises(ErrorPreparacionSandbox, match="ETAPA=proyecto"):
        preparar_java(copia, pruebas)


def test_no_reescribe_version_junit_existente(proyecto) -> None:
    """Una dependencia JUnit 5 ya declarada conserva su versión del proyecto."""
    copia, pruebas = proyecto
    texto = POM_BASE.replace(
        "</dependencies>",
        "<dependency><groupId>org.junit.jupiter</groupId><artifactId>junit-jupiter</artifactId><version>5.11.4</version><scope>test</scope></dependency></dependencies>",
    )
    (copia / "pom.xml").write_text(texto, encoding="utf-8")
    preparar_java(copia, pruebas)
    pom = ET.parse(copia / POM).getroot()
    dependencias = [
        d
        for d in pom.findall("{*}dependencies/{*}dependency")
        if d.findtext("{*}groupId") == "org.junit.jupiter"
    ]
    assert len(dependencias) == 1
    assert dependencias[0].findtext("{*}version") == "5.11.4"


def test_prueba_invalida_no_se_repara_y_queda_para_test_compile(proyecto) -> None:
    """El preparador conserva la sintaxis inválida para reportarla como fallo de prueba."""
    copia, pruebas = proyecto
    codigo = "class BancoGeneradoTest { void error( {"
    (pruebas / "recibida.java").write_text(codigo, encoding="utf-8")
    preparar_java(copia, pruebas)
    [destino] = (copia / TESTS).rglob("*.java")
    assert destino.read_text(encoding="utf-8") == codigo


@pytest.mark.parametrize("cantidad", [0, 2])
def test_exige_una_sola_fuente_de_prueba(proyecto, cantidad: int) -> None:
    """No ejecuta accidentalmente varias fuentes recibidas ni las pruebas anteriores del proyecto."""
    copia, pruebas = proyecto
    if cantidad == 0:
        (pruebas / "recibida.java").unlink()
    else:
        (pruebas / "otra.java").write_text(CODIGO, encoding="utf-8")
    with pytest.raises(ErrorPreparacionSandbox, match="ETAPA=prueba"):
        preparar_java(copia, pruebas)


def test_recoge_surefire_sin_perder_fallos(tmp_path: Path) -> None:
    """Agrega solo reportes de esta salida y conserva el fallo en el formato común."""
    salida = tmp_path / "out"
    informes = salida / "junit-raw"
    informes.mkdir(parents=True)
    (informes / "TEST-A.xml").write_text(
        '<testsuite><testcase name="paso"/></testsuite>', encoding="utf-8"
    )
    (informes / "TEST-B.xml").write_text(
        '<testsuite><testcase name="fallo"><failure message="expected: &lt;3&gt; but was: &lt;2&gt;"/></testcase></testsuite>',
        encoding="utf-8",
    )
    xml = recoger_junit(salida)
    resultado = JavaAdapter().interpretar_resultados(xml)
    assert resultado["total"] == 2
    assert resultado["fallaron"] == 1
    assert resultado["casos"][1]["obtenido"] == "2"


def test_sin_informe_o_xml_invalido_no_inventa_exito(tmp_path: Path) -> None:
    """El lector conserva la ausencia de datos para que el Reviewer la clasifique."""
    assert recoger_junit(tmp_path) is None
    informes = tmp_path / "junit-raw"
    informes.mkdir()
    (informes / "TEST-roto.xml").write_text("<testsuite>", encoding="utf-8")
    assert recoger_junit(tmp_path) is None
