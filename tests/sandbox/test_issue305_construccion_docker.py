"""Construcción Java real sin red, antes de IA simulada y sin tocar originales."""

import copy
import threading
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from docker.errors import NotFound

from qagent.config import cargar_configuracion
from qagent.lenguajes.java_construccion import comprobar_construccion
from qagent.orchestrator import corrida
from qagent.sandbox.modelos import IMAGEN_JAVA, LimitesSandbox
from tests.agents.test_generator_java import preparar
from tests.lenguajes.test_issue305_construccion_java import MODULO
from tests.orchestrator.test_issue305_antes_de_ia import cliente_contado

pytestmark = pytest.mark.docker
NS = "{http://maven.apache.org/POM/4.0.0}"
LIMITES = LimitesSandbox(cpus=2, memoria="2g", timeout_s=120)


def escribir_pom(ruta, pom):
    """Serializa una fixture con namespace predeterminado, como exige Maven."""
    arbol = copy.deepcopy(pom)
    for nodo in arbol.iter():
        nodo.tag = nodo.tag.removeprefix(NS)
    arbol.set("xmlns", NS[1:-1])
    ET.ElementTree(arbol).write(ruta, encoding="utf-8", xml_declaration=True)


def pom_de_fixture(raiz, *, version="21", bloquear=False):
    receta = Path(__file__).parents[2] / "src/qagent/sandbox/java/calentamiento/pom.xml"
    pom = ET.fromstring(receta.read_text(encoding="utf-8"))
    pom.find(NS + "groupId").text = "fixture.qagent305"
    pom.find(NS + "artifactId").text = "banco"
    pom.find(NS + "properties/" + NS + "maven.compiler.release").text = version
    plugins = pom.find(NS + "build/" + NS + "plugins")
    for plugin in list(plugins):
        if plugin.findtext(NS + "artifactId") == "pitest-maven":
            plugins.remove(plugin)
        if bloquear and plugin.findtext(NS + "artifactId") == "maven-compiler-plugin":
            configuracion = ET.SubElement(plugin, NS + "configuration")
            ET.SubElement(configuracion, NS + "fork").text = "true"
            ET.SubElement(
                configuracion, NS + "executable"
            ).text = "/work/proyecto/esperar-compilador.sh"
    if bloquear:
        script = raiz / "esperar-compilador.sh"
        script.write_bytes(b"#!/bin/sh\nsleep 30\nexit 17\n")
        script.chmod(0o755)
    escribir_pom(raiz / "pom.xml", pom)
    return pom


@pytest.fixture
def proyecto(tmp_path):
    contrato = preparar(tmp_path)
    pom_de_fixture(tmp_path)
    antigua = tmp_path / "src/test/java/NoEjecutar.java"
    antigua.parent.mkdir(parents=True)
    antigua.write_text("ESTA PRUEBA NO DEBE COMPILARSE NI EJECUTARSE", encoding="utf-8")
    return tmp_path, contrato


@pytest.fixture
def contenedores_seguros(cliente_docker, monkeypatch):
    creados = []
    coleccion = type(cliente_docker.containers)
    ejecutar = coleccion.run

    def registrar(self, *a, **opciones):
        assert opciones["network_mode"] == "none"
        assert opciones["read_only"] and opciones["cap_drop"] == ["ALL"]
        assert opciones["security_opt"] == ["no-new-privileges"]
        contenedor = ejecutar(self, *a, **opciones)
        creados.append(contenedor.id)
        return contenedor

    monkeypatch.setattr(coleccion, "run", registrar)
    yield creados
    for identificador in creados:
        with pytest.raises(NotFound):
            cliente_docker.containers.get(identificador)


def originales_de(raiz):
    return {
        p.relative_to(raiz): p.read_bytes()
        for p in raiz.rglob("*")
        if p.is_file() and ".qagent" not in p.relative_to(raiz).parts
    }


@pytest.mark.parametrize(
    "defecto,categoria", [("fuente", "compilacion"), ("dependencia", "dependencias")]
)
def test_fallo_real_impide_llamadas_a_ia(
    proyecto, cliente_docker, monkeypatch, contenedores_seguros, defecto, categoria
):
    raiz, contrato = proyecto
    if defecto == "fuente":
        archivo = raiz / MODULO
        archivo.write_text(
            archivo.read_text(encoding="utf-8").replace(
                "return x * 2;", "return simboloInexistente;"
            ),
            encoding="utf-8",
        )
    else:
        pom = ET.parse(raiz / "pom.xml")
        dependencias = pom.getroot().find(NS + "dependencies")
        dependencia = ET.SubElement(dependencias, NS + "dependency")
        for nombre, valor in (
            ("groupId", "fixture.qagent305.ausente"),
            ("artifactId", "no-descargado"),
            ("version", "1"),
        ):
            ET.SubElement(dependencia, NS + nombre).text = valor
        escribir_pom(raiz / "pom.xml", pom.getroot())
    originales = originales_de(raiz)
    llamadas = []
    cliente_contado(monkeypatch, contrato, {"comprobada": False}, llamadas)

    def validar(ruta, imagen, modulos, limites, cancelado=None):
        return comprobar_construccion(
            ruta, imagen, modulos, LIMITES, cancelado, cliente=cliente_docker
        )

    resultado = corrida.ejecutar_corrida(
        raiz,
        "humo",
        cargar_configuracion(simulado=True).config,
        None,
        simulado=True,
        preparar_imagen=lambda r: IMAGEN_JAVA,
        validar_construccion=validar,
    )
    assert resultado.estado == corrida.FALLO and llamadas == [], resultado.motivo
    assert resultado.construccion["categoria"] == categoria, resultado.motivo
    assert resultado.tokens_reales == resultado.tokens == 0
    assert originales_de(raiz) == originales and contenedores_seguros
    print(
        f"#305: {defecto}; categoria={categoria}; Planner=0; Generator=0; tokens=0; originales intactos"
    )


def test_compatible_construye_antes_de_ia_y_omite_tests_existentes(
    proyecto, cliente_docker, monkeypatch, contenedores_seguros
):
    raiz, contrato = proyecto
    originales = originales_de(raiz)
    estado, llamadas = {"comprobada": False}, []
    cliente_contado(monkeypatch, contrato, estado, llamadas)

    def validar(ruta, imagen, modulos, limites, cancelado=None):
        resultado = comprobar_construccion(
            ruta, imagen, modulos, LIMITES, cancelado, cliente=cliente_docker
        )
        estado["comprobada"] = resultado.aprobado
        return resultado

    resultado = corrida.ejecutar_corrida(
        raiz,
        "humo",
        cargar_configuracion(simulado=True).config,
        None,
        simulado=True,
        preparar_imagen=lambda r: IMAGEN_JAVA,
        validar_construccion=validar,
    )
    assert resultado.aceptadas == 1, resultado.motivo
    assert (
        llamadas.index("planner") < llamadas.index("generator") and estado["comprobada"]
    )
    assert (
        resultado.tokens_reales == 0 and resultado.construccion["estado"] == "aprobado"
    )
    assert originales_de(raiz) == originales and not (raiz / "target").exists()
    assert len(contenedores_seguros) >= 1
    print(
        "#305: compatible; construccion aprobada antes del Planner; JUnit generado aprobado; tests existentes omitidos; tokens reales=0"
    )


def test_jdk_incompatible_no_cambia_version_del_proyecto(
    proyecto, cliente_docker, contenedores_seguros
):
    raiz, _ = proyecto
    pom_de_fixture(raiz, version="26")
    originales = originales_de(raiz)
    resultado = comprobar_construccion(
        raiz, IMAGEN_JAVA, [MODULO], LIMITES, cliente=cliente_docker
    )
    assert (
        not resultado.aprobado and resultado.categoria == "incompatibilidad_herramienta"
    ), resultado.log
    assert originales_de(raiz) == originales
    assert "26" in (raiz / "pom.xml").read_text(encoding="utf-8")
    print("#305: release 26 incompatible con JDK 25; no se modifico POM ni JDK; sin IA")


@pytest.mark.parametrize("interrupcion", ["timeout", "cancelado"])
def test_interrupcion_real_no_autoriza_ia_ni_guarda_aprobacion(
    proyecto, cliente_docker, contenedores_seguros, interrupcion, monkeypatch
):
    raiz, _ = proyecto
    pom_de_fixture(raiz, bloquear=True)
    originales = originales_de(raiz)
    matados = []
    coleccion = type(cliente_docker.containers)
    ejecutar = coleccion.run

    def observar(self, *a, **k):
        contenedor = ejecutar(self, *a, **k)
        matar = contenedor.kill

        def registrar_kill(*args, **opciones):
            matados.append(contenedor.id)
            return matar(*args, **opciones)

        monkeypatch.setattr(contenedor, "kill", registrar_kill)
        return contenedor

    monkeypatch.setattr(coleccion, "run", observar)
    evento = threading.Event()
    temporizador = (
        threading.Timer(2.5, evento.set) if interrupcion == "cancelado" else None
    )
    if temporizador:
        temporizador.start()
    try:
        resultado = comprobar_construccion(
            raiz,
            IMAGEN_JAVA,
            [MODULO],
            LimitesSandbox(
                cpus=2, memoria="2g", timeout_s=4 if interrupcion == "timeout" else 30
            ),
            evento.is_set,
            cliente=cliente_docker,
        )
    finally:
        if temporizador:
            temporizador.cancel()
    assert resultado.categoria == interrupcion and not resultado.aprobado, resultado.log
    assert matados, (
        "La interrupción debe matar un contenedor activo, no reclasificar un fallo anterior."
    )
    assert not list((raiz / ".qagent/cache/construccion_java").glob("*.json"))
    assert originales_de(raiz) == originales
    print(f"#305: {interrupcion}; contenedor eliminado; sin cache de aprobacion ni IA")


def test_reactor_construye_dependencia_y_cache_invalida_su_cambio(
    tmp_path, cliente_docker, contenedores_seguros
):
    pom = pom_de_fixture(tmp_path)
    pom.find(NS + "artifactId").text = "raiz"
    ET.SubElement(pom, NS + "packaging").text = "pom"
    modulos = ET.SubElement(pom, NS + "modules")
    for nombre in ("core", "app", "excluido"):
        ET.SubElement(modulos, NS + "module").text = nombre
        carpeta = tmp_path / nombre
        carpeta.mkdir()
        cuerpo = f"<project><modelVersion>4.0.0</modelVersion><parent><groupId>fixture.qagent305</groupId><artifactId>raiz</artifactId><version>1</version></parent><artifactId>{nombre}</artifactId>"
        if nombre == "app":
            cuerpo += "<dependencies><dependency><groupId>fixture.qagent305</groupId><artifactId>core</artifactId><version>1</version></dependency></dependencies>"
        (carpeta / "pom.xml").write_text(cuerpo + "</project>", encoding="utf-8")
    escribir_pom(tmp_path / "pom.xml", pom)
    core = tmp_path / "core/src/main/java/Core.java"
    core.parent.mkdir(parents=True)
    core.write_text(
        "public class Core { public static int doble(int x) {return x*2;} }",
        encoding="utf-8",
    )
    app = tmp_path / "app/src/main/java/Banco.java"
    app.parent.mkdir(parents=True)
    app.write_text(
        "public class Banco { public static int f(int x) {return Core.doble(x);} }",
        encoding="utf-8",
    )
    rota = tmp_path / "excluido/src/main/java/Rota.java"
    rota.parent.mkdir(parents=True)
    rota.write_text("public class Rota { ESTO NO COMPILA }", encoding="utf-8")
    antes = originales_de(tmp_path)
    primero = comprobar_construccion(
        tmp_path,
        IMAGEN_JAVA,
        ["app/src/main/java/Banco.java"],
        LIMITES,
        cliente=cliente_docker,
    )
    assert primero.aprobado, primero.log
    repetido = comprobar_construccion(
        tmp_path,
        IMAGEN_JAVA,
        ["app/src/main/java/Banco.java"],
        LIMITES,
        cliente=cliente_docker,
    )
    assert repetido.reutilizado and originales_de(tmp_path) == antes
    core.write_text(
        "public class Core { public static int doble(int x) {return noExiste;} }",
        encoding="utf-8",
    )
    despues = comprobar_construccion(
        tmp_path,
        IMAGEN_JAVA,
        ["app/src/main/java/Banco.java"],
        LIMITES,
        cliente=cliente_docker,
    )
    assert despues.categoria == "compilacion" and not despues.reutilizado, despues.log
    assert primero.huella != despues.huella
    print(
        "#305: reactor app + core compilan; excluido no se compila; cache reutiliza; cambiar core invalida y bloquea"
    )
