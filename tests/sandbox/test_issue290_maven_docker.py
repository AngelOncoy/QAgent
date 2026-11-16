"""Reactor Maven real sin red: herencia, módulo auxiliar y una prueba seleccionada."""

from pathlib import Path

import pytest

from qagent.config import cargar_configuracion
from qagent.lenguajes import JavaAdapter
from qagent.lenguajes.java_revision import clasificar_java
from qagent.sandbox.ejecucion import ejecutar_comando_pruebas
from qagent.sandbox.imagen import _imagen_existe
from qagent.sandbox.modelos import IMAGEN_JAVA

pytestmark = pytest.mark.docker


def _escribir(raiz: Path, nombre: str, texto: str) -> None:
    destino = raiz / nombre
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(texto, encoding="utf-8")


def _pom(cuerpo: str) -> str:
    return (
        '<project xmlns="http://maven.apache.org/POM/4.0.0"><modelVersion>4.0.0</modelVersion>'
        + cuerpo
        + "</project>"
    )


@pytest.mark.parametrize("defecto", [False, True])
def test_reactor_offline_compila_dependencia_y_solo_ejecuta_prueba_elegida(
    cliente_docker, tmp_path, defecto
):
    """El mismo proyecto aprueba o detecta el defecto sin ejecutar sus tests existentes."""
    if not _imagen_existe(cliente_docker, IMAGEN_JAVA):
        pytest.skip("Falta la imagen base Java.")
    raiz, pruebas = tmp_path / "reactor", tmp_path / "generada"
    _escribir(
        raiz,
        "pom.xml",
        _pom(
            "<groupId>qagent.fixture290</groupId><artifactId>raiz</artifactId><version>1</version><packaging>pom</packaging><properties><maven.compiler.release>21</maven.compiler.release></properties><modules><module>core</module><module>api</module></modules>"
        ),
    )
    padre = "<parent><groupId>qagent.fixture290</groupId><artifactId>raiz</artifactId><version>1</version></parent>"
    _escribir(raiz, "core/pom.xml", _pom(padre + "<artifactId>core</artifactId>"))
    _escribir(
        raiz,
        "api/pom.xml",
        _pom(
            padre
            + "<artifactId>api</artifactId><dependencies><dependency><groupId>qagent.fixture290</groupId><artifactId>core</artifactId><version>1</version></dependency></dependencies>"
        ),
    )
    _escribir(
        raiz,
        "core/src/main/java/demo/Core.java",
        "package demo; public class Core { public static int sumar(int a, int b) { return a+b; } }",
    )
    extra = "+1" if defecto else ""
    _escribir(
        raiz,
        "api/src/main/java/demo/Banco.java",
        "package demo; public class Banco { /** Devuelve la suma de a y b. */ public static int sumar(int a, int b) { return Core.sumar(a,b)"
        + extra
        + "; } }",
    )
    for modulo in ("core", "api"):
        _escribir(
            raiz,
            f"{modulo}/src/test/java/demo/ExistenteTest.java",
            "ESTO NO DEBE COMPILARSE NI EJECUTARSE",
        )
    _escribir(
        pruebas,
        "api/src/test/java/demo/BancoTest.java",
        "package demo; import org.junit.jupiter.api.Test; import static org.junit.jupiter.api.Assertions.assertEquals; class BancoTest { @Test void sumaDeclarada() { assertEquals(3, Banco.sumar(1,2)); } }",
    )
    originales = {
        p.relative_to(raiz): p.read_bytes() for p in raiz.rglob("*") if p.is_file()
    }
    adaptador = JavaAdapter()
    modulo = "api/src/main/java/demo/Banco.java"
    config = cargar_configuracion(simulado=True).config
    resultado = ejecutar_comando_pruebas(
        IMAGEN_JAVA,
        adaptador.comando_pruebas(modulo),
        raiz,
        pruebas,
        leer_cobertura=adaptador.leer_cobertura,
        archivo_informe=adaptador.entorno_sandbox().informe,
        preparar=adaptador.preparador_sandbox(modulo),
        leer_informe=adaptador.lector_informe_sandbox(),
        limites=config.limites_sandbox("java"),
        cliente=cliente_docker,
    )
    assert resultado.junit_xml is not None, resultado.stdout + resultado.stderr
    informe = adaptador.interpretar_resultados(resultado.junit_xml)
    assert informe["total"] == 1
    assert informe["fallaron"] == int(defecto)
    assert resultado.exit_code == int(defecto), resultado.stdout + resultado.stderr
    clasificacion = clasificar_java(resultado)
    assert (clasificacion.tipo if clasificacion else None) == (
        "fallo_asercion" if defecto else None
    )
    cobertura = adaptador.cobertura_de_objetivo(
        resultado.coverage, modulo, "Banco.sumar"
    )
    assert cobertura["lineas"] == 100.0
    assert all(
        (raiz / p).read_bytes() == contenido for p, contenido in originales.items()
    )
    print(
        f"Maven reactor: padre local, core->api; casos=1; fallos={informe['fallaron']}; JaCoCo={cobertura['lineas']}%; originales intactos; sin red; 0 tokens"
    )
