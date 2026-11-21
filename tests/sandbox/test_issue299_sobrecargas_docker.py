"""JUnit y PIT reales distinguen firmas, sin red ni cambios en originales (#299)."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from qagent.agents.generator import GeneratorAgent
from qagent.lenguajes import JavaAdapter
from qagent.llm import TokenTracker
from qagent.sandbox.ejecucion import ejecutar_comando_pruebas
from qagent.sandbox.modelos import IMAGEN_JAVA, LimitesSandbox
from qagent.sandbox.mutacion import OK
from tests.agents.test_generator_java import ClienteJUnitGrabado
from tests.lenguajes.test_issue299_sobrecargas import FUENTE, codigo, preparar

pytestmark = pytest.mark.docker


@pytest.mark.parametrize(
    "texto,defectuosa",
    [
        (False, False),
        (False, True),
        (True, False),
        (True, True),
        ("array", False),
        ("varargs", False),
    ],
)
def test_junit_solo_prueba_la_sobrecarga_elegida(
    cliente_docker, tmp_path, texto, defectuosa
):
    proyecto = tmp_path / "proyecto"
    fuente = FUENTE
    if defectuosa:
        fuente = (
            fuente.replace("return x;", 'return "incorrecto";')
            if texto
            else fuente.replace("return x * 2;", "return x * 3;")
        )
    objetivo = "Banco.f(java.lang.String)" if texto else "Banco.f(int)"
    if isinstance(texto, str):
        fuente = """package ejemplo; public class Banco {
/** Devuelve la longitud de x. */ public static int f(int[] x) { return x.length; }
/** Devuelve la longitud de x. */ public static int f(String... x) { return x.length; }
}"""
        objetivo = (
            "Banco.f(int[])" if texto == "array" else "Banco.f(java.lang.String[])"
        )
    contrato = preparar(proyecto, objetivo, fuente)
    originales = {
        p.relative_to(proyecto): p.read_bytes()
        for p in proyecto.rglob("*")
        if p.is_file()
    }
    tracker = TokenTracker()
    codigo_test = codigo('"hola"', '"hola"') if texto else codigo()
    if isinstance(texto, str):
        entrada = [1, 2] if texto == "array" else ["a", "b"]
        expresion = "new int[]{1,2}" if texto == "array" else 'new String[]{"a","b"}'
        contrato["casos"][0].update(entrada={"x": entrada}, valor_esperado=2)
        codigo_test = codigo(expresion, "2")
    generado = GeneratorAgent(
        ClienteJUnitGrabado(codigo_test),
        tracker,
        es_simulado=True,
        ruta_proyecto=proyecto,
    ).generar(contrato, 1, None)
    adaptador = JavaAdapter()
    assert adaptador.validar_oraculo(contrato, generado["codigo"], proyecto) is None
    pruebas = tmp_path / "pruebas"
    archivo = pruebas / generado["archivo"]
    archivo.parent.mkdir(parents=True)
    archivo.write_text(generado["codigo"], encoding="utf-8")
    resultado = ejecutar_comando_pruebas(
        IMAGEN_JAVA,
        adaptador.comando_pruebas(contrato["modulo"]),
        proyecto,
        pruebas,
        leer_cobertura=adaptador.leer_cobertura,
        archivo_informe=adaptador.entorno_sandbox().informe,
        limites=LimitesSandbox(cpus=2, memoria="2g", timeout_s=120),
        cliente=cliente_docker,
        preparar=adaptador.preparador_sandbox(),
        leer_informe=adaptador.lector_informe_sandbox(),
    )
    informe = adaptador.interpretar_resultados(resultado.junit_xml or "")
    assert informe["total"] == 1, resultado.stdout + resultado.stderr
    assert informe["errores"] == informe["omitidos"] == 0
    assert informe["fallaron"] == int(defectuosa)
    from qagent.lenguajes.java_cobertura import cobertura_de_metodo

    assert (
        cobertura_de_metodo(resultado.coverage, contrato["modulo"], objetivo)["lineas"]
        == 100.0
    )
    otro = "Banco.f(int)" if texto else "Banco.f(java.lang.String)"
    if isinstance(texto, str):
        otro = "Banco.f(java.lang.String[])" if texto == "array" else "Banco.f(int[])"
    assert (
        cobertura_de_metodo(resultado.coverage, contrato["modulo"], otro)["lineas"]
        == 0.0
    )
    assert {
        p.relative_to(proyecto): p.read_bytes()
        for p in proyecto.rglob("*")
        if p.is_file()
    } == originales
    assert tracker.total_tokens == 0
    print(
        f"#299 JUnit: {objetivo}; defecto={defectuosa}; fallos={informe['fallaron']}; cobertura elegida=100%, otra=0%; originales intactos; tokens=0"
    )


def test_pit_no_muta_la_otra_firma(cliente_docker, tmp_path):
    proyecto = tmp_path / "proyecto"
    contrato = preparar(proyecto)
    receta = (
        Path(__file__).resolve().parents[2]
        / "src/qagent/sandbox/java/calentamiento/pom.xml"
    )
    pom = ET.fromstring(receta.read_text(encoding="utf-8"))
    plugins = pom.find("{*}build/{*}plugins")
    for plugin in list(plugins):
        if plugin.findtext("{*}artifactId") == "pitest-maven":
            plugins.remove(plugin)
    ET.ElementTree(pom).write(
        proyecto / "pom.xml", encoding="utf-8", xml_declaration=True
    )
    originales = {
        p.relative_to(proyecto): p.read_bytes()
        for p in proyecto.rglob("*")
        if p.is_file()
    }
    pruebas = tmp_path / "pruebas"
    pruebas.mkdir()
    (pruebas / "BancoTest.java").write_text(codigo(), encoding="utf-8")
    informes = []
    resultado = JavaAdapter().ejecutar_mutacion(
        IMAGEN_JAVA,
        proyecto,
        pruebas,
        contrato["modulo"],
        ["Banco.f(int)"],
        cliente=cliente_docker,
        al_informe=informes.append,
    )
    funcion = resultado.funciones["Banco.f(int)"]
    assert funcion.estado == OK, str(funcion.mensaje) + resultado.salida
    assert funcion.detectados > 0
    assert len(informes) == 1
    mutantes = ET.fromstring(informes[0])
    assert {n.findtext("methodDescription") for n in mutantes} == {"(I)I"}
    assert {n.findtext("mutatedMethod") for n in mutantes} == {"f"}
    assert {
        p.relative_to(proyecto): p.read_bytes()
        for p in proyecto.rglob("*")
        if p.is_file()
    } == originales
    print(
        f"#299 PIT: mutantes={len(mutantes)}; solo (I)I; puntuacion={funcion.puntuacion}; originales intactos"
    )
