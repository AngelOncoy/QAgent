"""Flujo productivo con proveedores grabados y sandbox simulado, sin API ni Java host."""

import json
from copy import deepcopy

import pytest

from qagent.almacenamiento import AlmacenProyecto
from qagent.config import cargar_configuracion
from qagent.lenguajes import JavaAdapter
from qagent.lenguajes.base import ResultadoConstruccion
from qagent.llm import FakeLLMClient, RespuestaLLM
from qagent.llm.fake import MARCA_CONTRATO
from qagent.orchestrator import corrida
from qagent.orchestrator.estados import Estado
from qagent.orchestrator.mutacion import mutar_modulo
from qagent.orchestrator.orquestador import ResultadoCorrida, ResultadoObjetivo
from qagent.orchestrator.regresion import ejecutar_regresion
from qagent.sandbox.modelos import ResultadoSandbox
from qagent.sandbox.mutacion import MutacionFuncion, ResultadoMutacion
from tests.lenguajes.test_issue307_vigencia import IMAGEN, escribir

MODULO = "src/main/java/demo/A.java"
MODULO_U = "src/main/java/demo/U.java"
SELECCION = [
    {"ruta": MODULO, "funciones": ["A.f"], "endpoints": [], "criticas": []},
    {"ruta": MODULO_U, "funciones": ["U.sano"], "endpoints": [], "criticas": []},
]


def caso(esperado=4, *, inferido=True):
    return {
        "id": "normal",
        "entrada": {"x": 2} if inferido else {},
        "valor_esperado": esperado,
        "origen": "inferido" if inferido else "docstring",
        "categoria": "normal",
        **(
            {"evidencia": ["cuerpo", "dependencia:src/main/java/demo/B.java::B.g"]}
            if inferido
            else {}
        ),
    }


def preparar(raiz):
    escribir(
        raiz,
        MODULO,
        "package demo; public class A { public static int f(int x) { return B.g(x); } }",
    )
    escribir(
        raiz,
        "src/main/java/demo/B.java",
        """package demo; public class B {
      /** Devuelve el doble de x. @return x multiplicado por dos */
      public static int g(int x) { return x*2; }
    }""",
    )
    escribir(
        raiz,
        MODULO_U,
        "package demo; public class U { /** Devuelve siete. @return siete */ public static int sano() { return 7; } }",
    )
    escribir(
        raiz,
        "src/test/java/demo/EvidenciaTest.java",
        """package demo;
      import org.junit.jupiter.api.Test; import static org.junit.jupiter.api.Assertions.assertEquals;
      class EvidenciaTest { @Test void evidencia() { assertEquals(4,A.f(2)); } }""",
    )
    escribir(
        raiz,
        "pom.xml",
        '<project xmlns="http://maven.apache.org/POM/4.0.0"><modelVersion>4.0.0</modelVersion><groupId>demo</groupId><artifactId>vigencia</artifactId><version>1</version><properties><maven.compiler.release>21</maven.compiler.release></properties></project>',
    )
    return raiz


class ClienteGrabado(FakeLLMClient):
    """Conserva los casos declarados; registra llamadas sin gastar tokens."""

    def __init__(self):
        super().__init__(
            grabaciones={
                "A.java::A.f": [caso()],
                "U.java::U.sano": [caso(7, inferido=False)],
            }
        )
        self.llamadas = []

    def generar(self, prompt, rol="planner"):
        self.llamadas.append((rol, prompt))
        if rol != "generator":
            return super().generar(prompt, rol=rol)
        contrato = json.loads(prompt.split(MARCA_CONTRATO, 1)[1])
        nombre = contrato["objetivo"].split(".")[0]
        invocacion = "A.f(2)" if nombre == "A" else "U.sano()"
        esperado = contrato["casos"][0]["valor_esperado"]
        codigo = (
            "package demo; import org.junit.jupiter.api.Test; import static org.junit.jupiter.api.Assertions.assertEquals; "
            f"class {nombre}Test {{ @Test void test_normal() {{ assertEquals({esperado},{invocacion}); }} }}"
        )
        return RespuestaLLM(codigo, 0, 0, 0, "grabado-307")


def sandbox_simulado(*args, **kwargs):
    return ResultadoSandbox(
        0,
        "",
        "",
        junit_xml='<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="test_normal" classname="demo.ATest" time="0.01"/></testsuite>',
    )


@pytest.fixture
def proyecto(tmp_path, monkeypatch):
    preparar(tmp_path)
    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()
    cliente = ClienteGrabado()
    monkeypatch.setattr(corrida, "crear_cliente", lambda *a, **k: cliente)
    return tmp_path, almacen, cliente


def correr(raiz, **kwargs):
    return corrida.ejecutar_corrida(
        raiz,
        "humo",
        cargar_configuracion(simulado=True).config,
        None,
        simulado=True,
        preparar_imagen=lambda *a: IMAGEN,
        ejecutor=sandbox_simulado,
        validar_construccion=lambda *a, **k: ResultadoConstruccion(
            "aprobado", "aprobado", "Fixture", imagen_id=IMAGEN
        ),
        seleccion=deepcopy(SELECCION),
        **kwargs,
    )


def test_sin_cambios_omite_planner_y_b_cambiado_replanifica_a_no_u(proyecto):
    raiz, almacen, cliente = proyecto
    primera = correr(raiz)
    assert primera.aceptadas == 2 and primera.tokens == 0, primera
    plan_a = almacen.leer_plan_modulo(MODULO)
    referencias = deepcopy(plan_a["contratos"][0]["casos"][0]["evidencia"])
    cliente.llamadas.clear()
    control = correr(raiz)
    assert control.aceptadas == 2 and not [
        r for r, _ in cliente.llamadas if r == "planner"
    ]
    assert almacen.leer_plan_modulo(MODULO)["run_origen"] == primera.run_id
    escribir(
        raiz,
        "src/main/java/demo/B.java",
        """package demo; public class B {
      /** Devuelve el doble de x. @return x multiplicado por dos */
      public static int g(int x) { return x*3; }
    }""",
    )
    cliente.llamadas.clear()
    posterior = correr(raiz)
    assert posterior.aceptadas == 2 and posterior.tokens == 0
    assert len([p for r, p in cliente.llamadas if r == "planner"]) == 2
    assert almacen.leer_plan_modulo(MODULO)["run_origen"] == posterior.run_id
    assert almacen.leer_plan_modulo(MODULO_U)["run_origen"] == primera.run_id
    assert (
        almacen.leer_plan_modulo(MODULO)["contratos"][0]["casos"][0]["evidencia"]
        == referencias
    )


def test_regresion_sin_cambios_ejecuta_y_tras_borrado_de_evidencia_no_ejecuta(proyecto):
    raiz, _almacen, cliente = proyecto
    inicial = correr(raiz)
    assert inicial.aceptadas == 2
    imagenes, ejecuciones = [], []

    def ejecutar(*a, **k):
        ejecuciones.append(a)
        return sandbox_simulado()

    def imagen(*a):
        imagenes.append(a)
        return IMAGEN

    cliente.llamadas.clear()
    control = ejecutar_regresion(
        raiz,
        "reg",
        cargar_configuracion(simulado=True).config,
        preparar_imagen=imagen,
        ejecutor=ejecutar,
        seleccion=[deepcopy(SELECCION[0])],
    )
    assert control.aceptadas == 1 and len(ejecuciones) == 1
    assert not cliente.llamadas
    (raiz / "src/test/java/demo/EvidenciaTest.java").unlink()
    imagenes.clear()
    ejecuciones.clear()
    resultado = ejecutar_regresion(
        raiz,
        "reg",
        cargar_configuracion(simulado=True).config,
        preparar_imagen=imagen,
        ejecutor=ejecutar,
        seleccion=[deepcopy(SELECCION[0])],
    )
    assert resultado.requieren_corrida_nueva == 1 and resultado.aceptadas == 0
    assert not ejecuciones and not imagenes and not cliente.llamadas


def test_imagen_distinta_requiere_corrida_nueva_antes_de_ejecutar(proyecto):
    raiz, _, cliente = proyecto
    assert correr(raiz).aceptadas == 2
    cliente.llamadas.clear()

    def prohibido(*a, **k):
        pytest.fail("No debe ejecutar una prueba aprobada en otro entorno")

    resultado = ejecutar_regresion(
        raiz,
        "reg",
        cargar_configuracion(simulado=True).config,
        preparar_imagen=lambda *a: "sha256:" + "b" * 64,
        ejecutor=prohibido,
        seleccion=[deepcopy(SELECCION[0])],
    )
    assert resultado.requieren_corrida_nueva == 1 and resultado.aceptadas == 0
    assert not cliente.llamadas


def test_pit_reutiliza_solo_con_dependencias_pruebas_y_tiempo_iguales(proyecto):
    raiz, almacen, _ = proyecto
    assert correr(raiz).aceptadas == 2
    contrato = almacen.leer_plan_modulo(MODULO)["contratos"][0]
    modulo = next(
        m for m in JavaAdapter().analizar(raiz)["modulos"] if m["ruta"] == MODULO
    )
    from qagent.orchestrator.regresion import huellas_de_objetivos

    huellas = huellas_de_objetivos(raiz)
    llamadas = []

    def mutador(*a, **k):
        llamadas.append(a)
        return ResultadoMutacion(MODULO, {"A.f": MutacionFuncion("A.f", "ok", 100, 1)})

    def mutar(tiempo=60, codigo="class ATest {}"):
        objetivo = ResultadoObjetivo(
            "A.f", True, decision="accept", contrato=contrato, codigo=codigo
        )
        resultado = ResultadoCorrida(MODULO, Estado.FIN, None, [objetivo], [], {}, 0.0)
        mutar_modulo(
            raiz,
            IMAGEN,
            modulo,
            resultado,
            tiempo,
            mutador=mutador,
            almacen=almacen,
            run_id="20261121-000000-0307",
            huellas=huellas,
        )
        assert objetivo.mutacion["estado"] == "ok"
        return objetivo.mutacion

    assert not mutar().get("reutilizada") and len(llamadas) == 1
    assert mutar()["reutilizada"] and len(llamadas) == 1
    escribir(
        raiz,
        "src/main/java/demo/U.java",
        "package demo; public class U { public static int sano() { return 8; } }",
    )
    assert mutar()["reutilizada"] and len(llamadas) == 1
    escribir(
        raiz,
        "src/main/java/demo/B.java",
        "package demo; public class B { public static int g(int x) { return x*3; } }",
    )
    assert not mutar().get("reutilizada") and len(llamadas) == 2
    assert not mutar(tiempo=61).get("reutilizada") and len(llamadas) == 3
    assert (
        not mutar(tiempo=61, codigo="class OtraPrueba {}").get("reutilizada")
        and len(llamadas) == 4
    )
