"""Herencia y selección Maven sin compilar ni ejecutar Java en el anfitrión."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from qagent.lenguajes import JavaAdapter
from qagent.lenguajes.java_ejecucion import POM, REACTOR, TESTS, preparar_java
from qagent.sandbox.maven import contexto_dependencias, inspeccionar, separar_fuente
from qagent.sandbox.modelos import ErrorPreparacionSandbox


def escribir(raiz: Path, nombre: str, contenido: str) -> Path:
    """Crea solo fixtures de texto dentro del directorio de prueba."""
    ruta = raiz / nombre
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(contenido, encoding="utf-8")
    return ruta


def pom(cuerpo: str) -> str:
    """Envuelve un descriptor con un namespace Maven válido."""
    return (
        '<project xmlns="http://maven.apache.org/POM/4.0.0"><modelVersion>4.0.0</modelVersion>'
        + cuerpo
        + "</project>"
    )


@pytest.fixture
def reactor(tmp_path):
    """Reactor con padre local, módulo core y API que depende de core."""
    raiz, pruebas = tmp_path / "repo", tmp_path / "pruebas"
    escribir(
        raiz,
        "pom.xml",
        pom(
            "<groupId>demo</groupId><artifactId>raiz</artifactId><version>1</version><packaging>pom</packaging><properties><maven.compiler.release>21</maven.compiler.release></properties><modules><module>core</module><module>api</module></modules>"
        ),
    )
    padre = "<parent><groupId>demo</groupId><artifactId>raiz</artifactId><version>1</version></parent>"
    escribir(raiz, "core/pom.xml", pom(padre + "<artifactId>core</artifactId>"))
    escribir(
        raiz,
        "api/pom.xml",
        pom(
            padre
            + "<artifactId>api</artifactId><dependencies><dependency><groupId>demo</groupId><artifactId>core</artifactId><version>1</version></dependency></dependencies>"
        ),
    )
    escribir(
        raiz,
        "core/src/main/java/demo/Core.java",
        "package demo; public class Core { public static int sumar(int a, int b) { return a + b; } }",
    )
    escribir(
        raiz,
        "api/src/main/java/demo/Banco.java",
        "package demo; public class Banco { /** Devuelve a más b. */ public static int sumar(int a, int b) { return Core.sumar(a, b); } }",
    )
    escribir(raiz, "core/src/test/java/demo/ExistenteTest.java", "NO DEBE EJECUTARSE")
    escribir(
        pruebas,
        "api/src/test/java/demo/BancoTest.java",
        "package demo; import org.junit.jupiter.api.Test; import static org.junit.jupiter.api.Assertions.assertEquals; class BancoTest { @Test void sumar() { assertEquals(3, Banco.sumar(1, 2)); } }",
    )
    return raiz, pruebas


def test_reactor_compila_auxiliares_pero_solo_incluye_la_prueba_seleccionada(reactor):
    """Los descriptores originales y tests existentes permanecen intactos."""
    raiz, pruebas = reactor
    originales = {
        p.relative_to(raiz): p.read_bytes() for p in raiz.rglob("*") if p.is_file()
    }
    preparar_java(raiz, pruebas, "api/src/main/java/demo/Banco.java")
    assert all(
        (raiz / p).read_bytes() == contenido for p, contenido in originales.items()
    )
    for modulo in ("", "core", "api"):
        archivo = raiz / REACTOR / modulo / "pom.xml"
        arbol = ET.parse(archivo).getroot()
        assert (
            arbol.findtext("{*}build/{*}sourceDirectory")
            == "/work/proyecto/" + (modulo + "/" if modulo else "") + "src/main/java"
        )
        testdir = arbol.findtext("{*}build/{*}testSourceDirectory")
        assert testdir.endswith(TESTS)
        surefire = next(
            p
            for p in arbol.findall("{*}build/{*}plugins/{*}plugin")
            if p.findtext("{*}artifactId") == "maven-surefire-plugin"
        )
        assert surefire.findtext("{*}configuration/{*}failIfNoTests") == (
            "true" if modulo == "api" else "false"
        )
    assert (raiz / "api" / TESTS / "demo/BancoTest.java").is_file()
    assert not (raiz / "core" / TESTS).exists()
    assert (
        "NO DEBE EJECUTARSE"
        in (raiz / "core/src/test/java/demo/ExistenteTest.java").read_text()
    )
    print(
        "Maven: reactor temporal con padre y core->api; solo api recibe la prueba; originales intactos"
    )


def test_descarga_terceros_sin_pedir_artefactos_internos_remotos(reactor):
    """La copia de construcción omite core; el POM original lo conserva."""
    raiz, _ = reactor
    originales = inspeccionar(raiz).archivos
    transformados = contexto_dependencias(originales)
    assert b"<artifactId>core</artifactId>" in originales["api/pom.xml"]
    assert b"<artifactId>core</artifactId>" not in transformados["api/pom.xml"]
    assert transformados["core/pom.xml"] == originales["core/pom.xml"]
    assert (raiz / "api/pom.xml").read_bytes() == originales["api/pom.xml"]


@pytest.mark.parametrize(
    "version,interno", [("${project.version}", True), ("2", False)]
)
def test_preparacion_distingue_versiones_y_resuelve_coordenadas_del_proyecto(
    reactor, version, interno
):
    """Una versión externa con el mismo grupo y nombre debe seguir descargándose."""
    raiz, _ = reactor
    archivo = raiz / "api/pom.xml"
    texto = archivo.read_text(encoding="utf-8")
    texto = texto.replace(
        "<dependencies><dependency><groupId>demo</groupId>",
        "<dependencies><dependency><groupId>${project.groupId}</groupId>",
    )
    texto = texto.replace(
        "<artifactId>core</artifactId><version>1</version>",
        f"<artifactId>core</artifactId><version>{version}</version>",
    )
    archivo.write_text(texto, encoding="utf-8")
    preparados = contexto_dependencias(inspeccionar(raiz).archivos)
    arbol = ET.fromstring(preparados["api/pom.xml"])
    dependencia = arbol.find("{*}dependencies/{*}dependency")
    assert (dependencia is None) == interno
    if not interno:
        assert dependencia.findtext("{*}version") == "2"


def test_padre_remoto_se_conserva_sin_imponer_release_del_banco(tmp_path):
    """Maven resolverá la herencia; el preparador no la reemplaza por Java 21."""
    escribir(
        tmp_path,
        "pom.xml",
        pom(
            "<parent><groupId>org.example</groupId><artifactId>padre</artifactId><version>1</version><relativePath/></parent><artifactId>api</artifactId>"
        ),
    )
    pruebas = tmp_path / "tests"
    escribir(pruebas, "BancoTest.java", "class BancoTest {}")
    preparar_java(tmp_path, pruebas)
    arbol = ET.parse(tmp_path / POM).getroot()
    assert arbol.findtext("{*}parent/{*}artifactId") == "padre"
    assert arbol.find("{*}properties/{*}maven.compiler.release") is None


def test_java_version_declarada_no_se_reemplaza_por_release_del_banco(tmp_path):
    """Respeta una versión Java explícita cuando no hay release ni source."""
    escribir(
        tmp_path,
        "pom.xml",
        pom("<properties><java.version>17</java.version></properties>"),
    )
    pruebas = tmp_path / "tests"
    escribir(pruebas, "BancoTest.java", "class BancoTest {}")
    preparar_java(tmp_path, pruebas)
    arbol = ET.parse(tmp_path / POM).getroot()
    assert arbol.findtext("{*}properties/{*}maven.compiler.release") == "17"


def test_seleccion_de_modulo_no_declarado_se_rechaza(reactor):
    raiz, pruebas = reactor
    with pytest.raises(ErrorPreparacionSandbox, match="no pertenece"):
        preparar_java(raiz, pruebas, "otro/src/main/java/demo/Banco.java")


@pytest.mark.parametrize(
    "fuente",
    [
        "../api/src/main/java/Banco.java",
        "/api/src/main/java/Banco.java",
        "-opcion/src/main/java/Banco.java",
        "api;orden/src/main/java/Banco.java",
        "api/src/main/java/../Banco.java",
    ],
)
def test_rutas_de_modulo_no_se_interpolan_como_ordenes(fuente):
    with pytest.raises(ValueError):
        separar_fuente(fuente)


def test_comando_modular_offline_selecciona_reactor_y_ancestros():
    comando = JavaAdapter().comando_pruebas("api/src/main/java/demo/Banco.java")
    assert comando[3:] == ["qagent-java", "api/src/main/java/demo/Banco.java"]
    assert "--offline" in comando[2]
    assert '-pl "$seleccion" -am' in comando[2]
    assert "ejecutar_compilacion compile" in comando[2]
    assert "ejecutar_compilacion test-compile" in comando[2]
    assert " mvn test " not in comando[2]


def test_contexto_generator_devuelve_archivo_en_su_modulo(reactor):
    raiz, _ = reactor
    estructura = JavaAdapter().analizar(raiz)
    modulo = next(
        m
        for m in estructura["modulos"]
        if m["ruta"] == "api/src/main/java/demo/Banco.java"
    )
    f = modulo["funciones"][0]
    contrato = {
        "modulo": modulo["ruta"],
        "objetivo": f["nombre"],
        "firma": f["firma"],
        "tipo": "funcion",
    }
    assert (
        JavaAdapter().archivo_para_contrato(contrato, raiz)
        == "api/src/test/java/demo/BancoTest.java"
    )


def test_pit_prepara_solo_el_modulo_critico_y_conserva_originales(reactor):
    """PIT se omite en raíz/core y se habilita exclusivamente en api."""
    from qagent.sandbox.pit_preparacion import preparar_pit

    raiz, pruebas = reactor
    originales = {
        p.relative_to(raiz): p.read_bytes() for p in raiz.rglob("*") if p.is_file()
    }
    objetivos = preparar_pit(
        raiz, pruebas, "api/src/main/java/demo/Banco.java", ["Banco.sumar"]
    )
    assert objetivos == {"Banco.sumar": ("demo.Banco", "sumar")}
    for modulo in ("", "core", "api"):
        arbol = ET.parse(raiz / REACTOR / modulo / "pom.xml").getroot()
        pit = next(
            p
            for p in arbol.findall("{*}build/{*}plugins/{*}plugin")
            if p.findtext("{*}artifactId") == "pitest-maven"
        )
        assert pit.findtext("{*}configuration/{*}skip") == (
            "false" if modulo == "api" else "true"
        )
        assert not any(
            "qagentJacocoArgLine" in (p.findtext("{*}configuration/{*}argLine") or "")
            for p in arbol.findall(".//{*}plugin")
        )
        assert not any(
            p.find("{*}configuration/{*}argLine") is not None
            and not p.findtext("{*}configuration/{*}argLine")
            for p in arbol.findall(".//{*}plugin")
        )
    assert all(
        (raiz / p).read_bytes() == contenido for p, contenido in originales.items()
    )


def test_version_java_del_perfil_activo_se_conserva_al_preparar(tmp_path):
    """El perfil de descarga y compilación conserva Java 17, sin imponer 21."""
    escribir(
        tmp_path,
        "pom.xml",
        pom(
            "<profiles><profile><id>compat</id><properties><java.version>17</java.version></properties></profile></profiles>"
        ),
    )
    escribir(tmp_path, ".mvn/maven.config", "-Pcompat")
    pruebas = tmp_path / "tests"
    escribir(pruebas, "BancoTest.java", "class BancoTest {}")
    preparar_java(tmp_path, pruebas)
    arbol = ET.parse(tmp_path / POM).getroot()
    assert arbol.findtext("{*}properties/{*}maven.compiler.release") == "17"
