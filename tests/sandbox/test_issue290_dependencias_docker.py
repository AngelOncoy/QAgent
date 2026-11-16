"""Descarga Maven real y ejecución offline de proyectos externos representativos."""

from pathlib import Path

import pytest

from qagent.config import cargar_configuracion
from qagent.lenguajes import JavaAdapter
from qagent.sandbox.ejecucion import ejecutar_comando_pruebas
from qagent.sandbox.imagen import _imagen_existe, preparar_imagen
from qagent.sandbox.modelos import IMAGEN_JAVA
from tests.lenguajes.test_issue290_maven_ejecucion import escribir, pom

pytest_plugins = ("tests.lenguajes.test_issue290_maven_ejecucion",)
pytestmark = pytest.mark.docker

TERCERO = """<dependency><groupId>org.apache.commons</groupId>
<artifactId>commons-lang3</artifactId><version>3.17.0</version></dependency>"""


def _comprobar(cliente, raiz: Path, pruebas: Path, modulo: str) -> None:
    """Descarga con red en build y verifica una sola prueba dentro del sandbox offline."""
    originales = {
        p.relative_to(raiz): p.read_bytes() for p in raiz.rglob("*") if p.is_file()
    }
    imagen = preparar_imagen(raiz, cliente, avanzar=print, imagen=IMAGEN_JAVA)
    assert imagen != IMAGEN_JAVA
    adaptador = JavaAdapter()
    resultado = ejecutar_comando_pruebas(
        imagen,
        adaptador.comando_pruebas(modulo),
        raiz,
        pruebas,
        preparar=adaptador.preparador_sandbox(modulo),
        leer_informe=adaptador.lector_informe_sandbox(),
        archivo_informe=adaptador.entorno_sandbox().informe,
        leer_cobertura=adaptador.leer_cobertura,
        limites=cargar_configuracion(simulado=True).config.limites_sandbox("java"),
        cliente=cliente,
    )
    assert resultado.exit_code == 0, resultado.stdout + resultado.stderr
    assert resultado.junit_xml is not None
    informe = adaptador.interpretar_resultados(resultado.junit_xml)
    assert informe["total"] == 1
    assert informe["fallaron"] == 0
    assert all((raiz / p).read_bytes() == texto for p, texto in originales.items())
    print(
        "Maven externo: dependencias preparadas; 1 JUnit aprobado sin red; originales intactos; 0 tokens"
    )


def test_padre_publico_y_perfil_java17_descargan_y_ejecutan_sin_red(
    cliente_docker, tmp_path
):
    """Padre Apache público, dependencia ajena al banco y perfil explícito Java 17."""
    if not _imagen_existe(cliente_docker, IMAGEN_JAVA):
        pytest.skip("Falta la imagen base Java.")
    raiz, pruebas = tmp_path / "externo", tmp_path / "pruebas"
    escribir(
        raiz,
        "pom.xml",
        pom(
            "<parent><groupId>org.apache</groupId><artifactId>apache</artifactId><version>35</version><relativePath/></parent>"
            "<artifactId>qagent-fixture290-externo</artifactId><version>1</version>"
            "<profiles><profile><id>compat</id><properties><maven.compiler.release>17</maven.compiler.release></properties></profile></profiles>"
            "<dependencies>" + TERCERO + "</dependencies>"
        ),
    )
    escribir(raiz, ".mvn/maven.config", "-Pcompat")
    escribir(
        raiz,
        "src/main/java/demo/Banco.java",
        "package demo; public class Banco { /** Longitud del texto. */ public static int longitud(String s) { return org.apache.commons.lang3.StringUtils.length(s); } }",
    )
    escribir(
        pruebas,
        "BancoTest.java",
        'package demo; import org.junit.jupiter.api.Test; import static org.junit.jupiter.api.Assertions.assertEquals; class BancoTest { @Test void longitud() throws Exception { assertEquals(2, Banco.longitud("ab")); try (var in = Banco.class.getResourceAsStream("Banco.class")) { assertEquals(61, java.nio.ByteBuffer.wrap(in.readAllBytes()).getShort(6)); } } }',
    )
    _comprobar(cliente_docker, raiz, pruebas, "src/main/java/demo/Banco.java")


def test_reactor_con_dependencia_publica_descarga_sin_buscar_core_remoto(
    cliente_docker, reactor
):
    """La preparación descarga Commons; core se compila localmente dentro del reactor."""
    if not _imagen_existe(cliente_docker, IMAGEN_JAVA):
        pytest.skip("Falta la imagen base Java.")
    raiz, pruebas = reactor
    archivo = raiz / "core/pom.xml"
    archivo.write_text(
        archivo.read_text(encoding="utf-8").replace(
            "</project>", "<dependencies>" + TERCERO + "</dependencies></project>"
        ),
        encoding="utf-8",
    )
    escribir(
        raiz,
        "core/src/main/java/demo/Core.java",
        "package demo; public class Core { public static int sumar(int a, int b) { return a + b + org.apache.commons.lang3.math.NumberUtils.INTEGER_ZERO; } }",
    )
    _comprobar(cliente_docker, raiz, pruebas, "api/src/main/java/demo/Banco.java")
