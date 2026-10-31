"""JUnit y JaCoCo reales sobre el banco TA-01, con pruebas controladas (#182)."""

import os
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from qagent.config import cargar_configuracion
from qagent.lenguajes import JavaAdapter
from qagent.lenguajes.java_cobertura import cobertura_de_metodo
from qagent.lenguajes.java_revision import clasificar_java
from qagent.sandbox.ejecucion import ejecutar_comando_pruebas
from qagent.sandbox.imagen import _imagen_existe
from qagent.sandbox.modelos import IMAGEN_JAVA

pytestmark = pytest.mark.docker
RAIZ = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("etapa", ["proyecto", "prueba"])
def test_compilacion_real_distingue_proyecto_y_prueba(cliente_docker, tmp_path, etapa):
    """Un símbolo inexistente se atribuye a su fase real, sin tocar el banco original."""
    if not _imagen_existe(cliente_docker, IMAGEN_JAVA):
        pytest.skip("Falta qagent-sandbox:java.")
    proyecto = tmp_path / "banco"
    shutil.copytree(RAIZ / "bench_java/src", proyecto / "src")
    shutil.copyfile(
        RAIZ / "src/qagent/sandbox/java/calentamiento/pom.xml", proyecto / "pom.xml"
    )
    fuente = proyecto / "src/main/java/org/qagent/bench/BancoCorrecto.java"
    if etapa == "proyecto":
        fuente.write_text(
            fuente.read_text(encoding="utf-8").replace(
                "return total;", "return simboloInexistente;"
            ),
            encoding="utf-8",
        )
    pruebas = tmp_path / "pruebas"
    pruebas.mkdir()
    llamada = (
        "BancoCorrecto.noExiste()"
        if etapa == "prueba"
        else "BancoCorrecto.sumarPrecios(java.util.List.of(10.0, 20.0))"
    )
    (pruebas / "BancoControladoTest.java").write_text(
        "package org.qagent.bench; import org.junit.jupiter.api.Test; "
        "import static org.junit.jupiter.api.Assertions.*; class BancoControladoTest { "
        "@Test void contrato() { assertEquals(30.0, " + llamada + "); } }",
        encoding="utf-8",
    )
    adaptador = JavaAdapter()
    config = cargar_configuracion(simulado=True).config
    resultado = ejecutar_comando_pruebas(
        IMAGEN_JAVA,
        adaptador.comando_pruebas("src/main/java/org/qagent/bench/BancoCorrecto.java"),
        proyecto,
        pruebas,
        leer_cobertura=adaptador.leer_cobertura,
        archivo_informe=adaptador.entorno_sandbox().informe,
        preparar=adaptador.preparador_sandbox(),
        leer_informe=adaptador.lector_informe_sandbox(),
        limites=config.limites_sandbox("java"),
        cliente=cliente_docker,
    )
    assert resultado.exit_code != 0
    assert resultado.junit_xml is None
    clasificacion = clasificar_java(resultado)
    assert clasificacion.tipo == ("entorno" if etapa == "proyecto" else "error_test")
    assert clasificacion.motivo_sin_veredicto == (
        "error_compilacion_proyecto" if etapa == "proyecto" else None
    )
    print(
        f"Compilación real {etapa}: {clasificacion.tipo}; motivo={clasificacion.motivo_sin_veredicto}"
    )


@pytest.mark.parametrize(
    ("clase", "metodo", "asercion", "fallos"),
    [
        (
            "BancoCorrecto",
            "sumarPrecios",
            "assertEquals(30.0, BancoCorrecto.sumarPrecios(List.of(10.0, 20.0)));",
            0,
        ),
        (
            "BancoDefectuoso",
            "calcularPromedio",
            "assertEquals(2.5, BancoDefectuoso.calcularPromedio(List.of(2, 3)));",
            1,
        ),
    ],
)
def test_junit_y_jacoco_reales_del_banco(
    cliente_docker, tmp_path: Path, clase: str, metodo: str, asercion: str, fallos: int
) -> None:
    """Compila el banco en Docker y ejecuta solo la prueba recibida, sin generación automática.

    El POM usa las herramientas ya almacenadas en la imagen para evitar descargas.
    El banco de producción se copia sin alterar sus implementaciones. La prueba
    defectuosa espera el valor del Javadoc y debe fallar con 2.0 frente a 2.5.
    """
    if not _imagen_existe(cliente_docker, IMAGEN_JAVA):
        pytest.skip("Falta qagent-sandbox:java; no se ha validado ejecución Java real.")
    proyecto = tmp_path / "proyecto"
    shutil.copytree(RAIZ / "bench_java/src", proyecto / "src")
    receta = RAIZ / "src/qagent/sandbox/java/calentamiento/pom.xml"
    shutil.copyfile(receta, proyecto / "pom.xml")
    originales = {
        p.relative_to(proyecto): p.read_bytes()
        for p in proyecto.rglob("*")
        if p.is_file()
    }
    pruebas = tmp_path / "generada"
    pruebas.mkdir()
    (pruebas / "recibida.java").write_text(
        "package org.qagent.bench;\nimport java.util.List;\nimport org.junit.jupiter.api.Test;\n"
        "import static org.junit.jupiter.api.Assertions.assertEquals;\n"
        "public class BancoControladoTest { @Test void comportamiento() {"
        + asercion
        + "} }\n",
        encoding="utf-8",
    )
    adaptador = JavaAdapter()
    grabados = {}

    def leer_cobertura(salida: Path):
        """Recoge XML real para evidencias antes de que el sandbox limpie la salida."""
        archivo = salida / "jacoco.xml"
        if archivo.is_file():
            grabados["jacoco"] = archivo.read_text(encoding="utf-8")
        return adaptador.leer_cobertura(salida)

    def leer_informe(salida: Path):
        """Agrega las suites reales usando el lector del adaptador."""
        xml = adaptador.lector_informe_sandbox()(salida)
        if xml is not None:
            grabados["junit"] = xml
        return xml

    modulo = "src/main/java/org/qagent/bench/" + clase + ".java"
    config = cargar_configuracion(simulado=True).config
    assert config is not None
    resultado = ejecutar_comando_pruebas(
        IMAGEN_JAVA,
        adaptador.comando_pruebas(modulo),
        proyecto,
        pruebas,
        leer_cobertura=leer_cobertura,
        archivo_informe=adaptador.entorno_sandbox().informe,
        preparar=adaptador.preparador_sandbox(),
        leer_informe=leer_informe,
        limites=config.limites_sandbox("java"),
        cliente=cliente_docker,
    )
    salida = resultado.stdout + resultado.stderr
    assert resultado.exit_code == fallos, salida
    assert not resultado.timed_out and not resultado.oom_killed, salida
    assert resultado.junit_xml is not None, salida
    informe = adaptador.interpretar_resultados(resultado.junit_xml)
    assert informe["total"] == 1, (
        "No deben ejecutarse las once pruebas preexistentes del banco."
    )
    assert informe["fallaron"] == fallos
    assert informe["errores"] == informe["omitidos"] == 0
    if fallos:
        [caso] = informe["casos"]
        assert caso["esperado"] == "2.5"
        assert caso["obtenido"] == "2.0"
        assert caso["tipo_error"] == "org.opentest4j.AssertionFailedError"
    cobertura = cobertura_de_metodo(resultado.coverage, modulo, clase + "." + metodo)
    assert cobertura is not None, salida
    assert cobertura["lineas"] > 0
    assert resultado.limites.memoria == "4g"
    assert resultado.limites.timeout_s == 300
    assert all(
        (proyecto / relativa).read_bytes() == contenido
        for relativa, contenido in originales.items()
    )
    assert not (proyecto / ".qagent-junit.xml").exists()
    print(
        f"Java real: {clase}.{metodo}; casos={informe['total']}, fallos={fallos}, cobertura={cobertura}, memoria={resultado.limites.memoria}, {resultado.duracion_s} s"
    )
    if fallos and os.environ.get("QAGENT_GRABAR_JAVA") == "1":
        destino = RAIZ / "tests/fixtures/java"
        raiz = ET.fromstring(grabados["junit"])
        for suite in raiz.findall("testsuite"):
            for propiedades in list(suite.findall("properties")):
                suite.remove(propiedades)  # Evita conservar propiedades del entorno.
        ET.ElementTree(raiz).write(
            destino / "junit5-sandbox-promedio.xml",
            encoding="utf-8",
            xml_declaration=True,
        )
        (destino / "jacoco-sandbox-promedio.xml").write_text(
            grabados["jacoco"], encoding="utf-8", newline=""
        )
        print(
            "Informes reales JUnit/JaCoCo del promedio guardados para pruebas sin Docker."
        )
