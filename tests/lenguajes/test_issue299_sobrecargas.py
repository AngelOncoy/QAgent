"""Regresiones de identidad, oráculo, persistencia y métricas por firma (#299)."""

import json
from pathlib import Path

import pytest

from qagent import contracts
from qagent.agents.generator import GeneratorAgent
from qagent.almacenamiento.proyecto import id_de_spec
from qagent.lenguajes import JavaAdapter
from qagent.lenguajes.java_cobertura import cobertura_de_metodo
from qagent.lenguajes.java_firmas import indexar_metodos
from qagent.lenguajes.java_generacion import contexto_java
from qagent.lenguajes.java_inferencia import ProveedorInferenciaJava
from qagent.lenguajes.treesitter import obtener_parser
from qagent.llm import TokenTracker
from tests.agents.test_generator_java import ClienteJUnitGrabado

FUENTE = """package ejemplo;
public class Banco {
    /** Devuelve el doble de x. */
    public static int f(int x) { return x * 2; }
    /** Devuelve x sin cambios. */
    public static String f(String x) { return x; }
    /** Devuelve uno. */
    public static int sano() { return 1; }
}
"""


def preparar(
    tmp_path: Path, objetivo: str = "Banco.f(int)", fuente: str = FUENTE
) -> dict:
    """Construye fuentes y contrato con esperado documentado independiente del cuerpo."""
    archivo = tmp_path / "src/main/java/ejemplo/Banco.java"
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_text(fuente, encoding="utf-8")
    (tmp_path / "pom.xml").write_text(
        """<project xmlns="http://maven.apache.org/POM/4.0.0">
<modelVersion>4.0.0</modelVersion><groupId>ejemplo</groupId><artifactId>sobrecargas</artifactId><version>1</version>
<properties><maven.compiler.release>25</maven.compiler.release></properties></project>""",
        encoding="utf-8",
    )
    [modulo] = JavaAdapter().analizar(tmp_path)["modulos"]
    funcion = next(f for f in modulo["funciones"] if f["nombre"] == objetivo)
    texto = "java.lang.String" in objetivo
    return {
        "version": "3",
        "lenguaje": "java",
        "framework_pruebas": "junit5",
        "tipo": "funcion",
        "modulo": modulo["ruta"],
        "huella": modulo["huella"],
        "objetivo": objetivo,
        "firma": funcion["firma"],
        "critical": True,
        "casos": [
            {
                "id": "normal",
                "origen": "docstring",
                "descripcion": "Respeta el Javadoc",
                "entrada": {"x": "hola" if texto else 2},
                "valor_esperado": "hola" if texto else 4,
            }
        ],
    }


def codigo(argumento: str = "2", esperado: str = "4") -> str:
    """Prueba JUnit directa; ni entradas ni aserciones se deducen ejecutando Java."""
    return f"""package ejemplo;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
class BancoTest {{ @Test void test_normal() {{ assertEquals({esperado}, Banco.f({argumento})); }} }}"""


def test_conserva_tres_objetivos_incluso_en_una_linea(tmp_path):
    preparar(tmp_path, fuente=FUENTE.replace("\n", " "))
    estructura = JavaAdapter().analizar(tmp_path)
    assert estructura["errores"] == []
    nombres = [f["nombre"] for f in estructura["modulos"][0]["funciones"]]
    assert nombres == ["Banco.f(int)", "Banco.f(java.lang.String)", "Banco.sano"]
    assert estructura["resumen"]["total_funciones_publicas"] == 3


@pytest.mark.parametrize(
    "objetivo,argumento,esperado",
    [("Banco.f(int)", "2", "4"), ("Banco.f(java.lang.String)", '"hola"', '"hola"')],
)
def test_generator_guardrail_y_contrato_aislan_cada_firma(
    tmp_path, objetivo, argumento, esperado
):
    contrato = preparar(tmp_path, objetivo)
    contracts.validar_versionado("planner_contract", contrato)
    tracker = TokenTracker()
    generado = GeneratorAgent(
        ClienteJUnitGrabado(codigo(argumento, esperado)),
        tracker,
        es_simulado=True,
        ruta_proyecto=tmp_path,
    ).generar(contrato, 1, None)
    assert generado["objetivo"] == objetivo
    assert JavaAdapter().validar_oraculo(contrato, generado["codigo"], tmp_path) is None
    assert tracker.total_tokens == 0


@pytest.mark.parametrize(
    "argumento", ['"2"', "2L", "2.0", "(int) 2L", "Integer.valueOf(2)", "null"]
)
def test_rechaza_otra_sobrecarga_o_conversion_ambigua(tmp_path, argumento):
    contrato = preparar(tmp_path)
    assert (
        JavaAdapter().validar_oraculo(contrato, codigo(argumento), tmp_path) is not None
    )


def test_historico_se_lee_por_firma_sin_reescribirlo(tmp_path):
    contrato = preparar(tmp_path)
    contrato["objetivo"] = "Banco.f"
    anterior = json.dumps(contrato)
    contracts.validar_versionado("planner_contract", contrato)
    assert contexto_java(contrato, tmp_path)["identidad_metodo"] == "Banco.f(int)"
    assert JavaAdapter().validar_oraculo(contrato, codigo("2L"), tmp_path) is not None
    assert json.dumps(contrato) == anterior


def test_identidad_no_depende_del_nombre_del_parametro(tmp_path):
    preparar(tmp_path)
    adaptador = JavaAdapter()
    assert set(adaptador.huellas_de_archivo(FUENTE, "Banco.java")) == set(
        adaptador.huellas_de_archivo(FUENTE.replace("int x", "int dato"), "Banco.java")
    )
    ids = [
        id_de_spec("Banco.java", n)
        for n in (
            "Banco.f(int)",
            "Banco.f(int[])",
            "Banco.f(java.lang.String)",
            "Banco.f(java.lang.String[])",
        )
    ]
    assert len(set(ids)) == 4
    assert id_de_spec("Banco.java", "Banco.sano") == "Banco_java__Banco_sano"


def test_arrays_varargs_anidadas_y_sobrescritura(tmp_path):
    fuente = """class Padre { public int f(int x) {return x;} }
class Hija extends Padre { @Override public int f(int x) {return x;}
 public int f(String x) {return 1;}
 static class Interna { public void g(int a[]) {} public void g(String... a) {} }
 public int sano() { class Local {public void g() {}} return 1;} }"""
    (tmp_path / "Hija.java").write_text(fuente, encoding="utf-8")
    nombres = [
        f["nombre"] for f in JavaAdapter().analizar(tmp_path)["modulos"][0]["funciones"]
    ]
    assert set(nombres) == {
        "Padre.f",
        "Hija.f(int)",
        "Hija.f(java.lang.String)",
        "Hija.Interna.g(int[])",
        "Hija.Interna.g(java.lang.String[])",
        "Hija.sano",
    }
    assert set(
        indexar_metodos(obtener_parser("java").parse(fuente.encode()).root_node)
    ) == set(nombres)


def test_inferencia_separa_cuerpos_sin_javadoc(tmp_path):
    preparar(
        tmp_path,
        fuente=FUENTE.replace("/** Devuelve el doble de x. */", "").replace(
            "/** Devuelve x sin cambios. */", ""
        ),
    )
    modulos = JavaAdapter().analizar(tmp_path)["modulos"]
    proveedor = ProveedorInferenciaJava(tmp_path, modulos)
    entero = proveedor.contexto(modulos[0]["ruta"], "Banco.f(int)")
    texto = proveedor.contexto(modulos[0]["ruta"], "Banco.f(java.lang.String)")
    assert entero is not None and texto is not None and entero != texto


def test_firmas_ilegales_se_informan_individualmente(tmp_path):
    fuente = """class Banco { public void f(int[] a) {} public void f(int... b) {}
public int sano() { return 1; } }"""
    (tmp_path / "Banco.java").write_text(fuente, encoding="utf-8")
    estructura = JavaAdapter().analizar(tmp_path)
    assert [f["nombre"] for f in estructura["modulos"][0]["funciones"]] == [
        "Banco.sano"
    ]
    assert len(estructura["errores"]) == 2
    assert all(
        e["tipo"] == "FirmaJavaNoAdmitida" and "public void f" in e["mensaje"]
        for e in estructura["errores"]
    )


def test_specs_de_sobrecargas_no_se_sobrescriben(tmp_path):
    from qagent.almacenamiento import AlmacenProyecto

    entero = preparar(tmp_path)
    texto = preparar(tmp_path, "Banco.f(java.lang.String)")
    almacen = AlmacenProyecto(tmp_path)
    spec_entero = almacen.guardar_spec(entero, "20261120-000000-0299")
    spec_texto = almacen.guardar_spec(texto, "20261120-000000-0299")
    assert spec_entero["id"] != spec_texto["id"]
    assert almacen.leer_spec(spec_entero["id"])["contrato"] == entero
    assert almacen.leer_spec(spec_texto["id"])["contrato"] == texto


def test_cada_sobrecarga_conserva_sus_llamadas_en_una_misma_linea(tmp_path):
    fuente = """class Banco { public static int f(int x) {return a();} public static int f(String x) {return b();} public static int a(){return 1;} public static int b(){return 2;} }"""
    (tmp_path / "Banco.java").write_text(fuente, encoding="utf-8")
    funciones = {
        f["nombre"]: f
        for f in JavaAdapter().analizar(tmp_path)["modulos"][0]["funciones"]
    }
    assert funciones["Banco.f(int)"]["llama_a"] == ["Banco.java::Banco.a"]
    assert funciones["Banco.f(java.lang.String)"]["llama_a"] == ["Banco.java::Banco.b"]


def test_jacoco_selecciona_descriptor_y_nunca_suma_otras_firmas():
    cobertura = {
        "files": {
            "src/main/java/ejemplo/Banco.java": {
                "functions": {
                    "Banco.f(I)I": {
                        "descriptor": "(I)I",
                        "summary": {
                            "percent_covered": 100.0,
                            "percent_branches_covered": None,
                        },
                    },
                    "Banco.f(Ljava/lang/String;)Ljava/lang/String;": {
                        "descriptor": "(Ljava/lang/String;)Ljava/lang/String;",
                        "summary": {
                            "percent_covered": 0.0,
                            "percent_branches_covered": None,
                        },
                    },
                }
            }
        }
    }
    modulo = "src/main/java/ejemplo/Banco.java"
    assert cobertura_de_metodo(cobertura, modulo, "Banco.f(int)")["lineas"] == 100.0
    assert (
        cobertura_de_metodo(cobertura, modulo, "Banco.f(java.lang.String)")["lineas"]
        == 0.0
    )
    assert cobertura_de_metodo(cobertura, modulo, "Banco.f") is None


def test_herencia_no_invoca_otra_sobrecarga_con_entrada_igual(tmp_path):
    fuente = """package ejemplo;
class Padre { public static String f(String x) {return "hola";} }
public class Banco extends Padre {
/** Devuelve hola para cualquier objeto. */ public static String f(Object x) {return "hola";}
}"""
    contrato = preparar(tmp_path, "Banco.f", fuente)
    contrato["casos"][0].update(entrada={"x": "hola"}, valor_esperado="hola")
    assert (
        JavaAdapter().validar_oraculo(contrato, codigo('"hola"', '"hola"'), tmp_path)
        is not None
    )
    contrato["casos"][0]["entrada"] = {"x": None}
    assert (
        JavaAdapter().validar_oraculo(
            contrato, codigo("(java.lang.Object) null", '"hola"'), tmp_path
        )
        is None
    )


def test_tipo_vecino_no_se_asume_java_lang(tmp_path):
    contrato = preparar(tmp_path, "Banco.f(java.lang.String)")
    (tmp_path / "src/main/java/ejemplo/String.java").write_text(
        "package ejemplo; public class String {}", encoding="utf-8"
    )
    error = JavaAdapter().validar_oraculo(
        contrato, codigo('"hola"', '"hola"'), tmp_path
    )
    assert error is not None and "declaración vecina" in error


def test_endpoints_spring_sobrecargados_conservan_manejador_exacto(tmp_path):
    fuente = """import org.springframework.web.bind.annotation.*;
@RestController public class Banco {
@GetMapping("/entero") public int f(@RequestParam int x) {return x;}
@GetMapping("/texto") public String f(@RequestParam String x) {return x;}
public int sano() {return 1;}
}"""
    (tmp_path / "Banco.java").write_text(fuente, encoding="utf-8")
    [modulo] = JavaAdapter().analizar(tmp_path)["modulos"]
    assert {e["manejador"] for e in modulo["endpoints"]} == {
        "Banco.f(int)",
        "Banco.f(java.lang.String)",
    }
    assert [f["nombre"] for f in modulo["funciones"]] == ["Banco.sano"]


@pytest.mark.parametrize(
    "objetivo,tipo,entrada,expresion",
    [
        ("Banco.f(int[])", "int[]", [1, 2], "new int[]{1,2}"),
        (
            "Banco.f(java.lang.String[])",
            "String...",
            ["a", "b"],
            'new String[]{"a","b"}',
        ),
    ],
)
def test_arrays_y_varargs_se_invocan_con_array_exacto(
    tmp_path, objetivo, tipo, entrada, expresion
):
    fuente = """package ejemplo; public class Banco {
public static int f(int[] x) { return x.length; }
public static int f(String... x) { return x.length; }
}"""
    contrato = preparar(tmp_path, objetivo, fuente)
    contrato["casos"][0].update(entrada={"x": entrada}, valor_esperado=2)
    assert tipo in contrato["firma"]
    assert (
        JavaAdapter().validar_oraculo(contrato, codigo(expresion, "2"), tmp_path)
        is None
    )
    assert (
        JavaAdapter().validar_oraculo(contrato, codigo("null", "2"), tmp_path)
        is not None
    )


def test_null_exige_tipo_exacto_y_no_admite_cast_numerico(tmp_path):
    contrato = preparar(tmp_path, "Banco.f(java.lang.String)")
    contrato["casos"][0].update(entrada={"x": None}, valor_esperado=None)
    prueba = (
        codigo()
        .replace("assertEquals", "assertNull")
        .replace("4, Banco.f(2)", "Banco.f((java.lang.String) null)")
    )
    assert JavaAdapter().validar_oraculo(contrato, prueba, tmp_path) is None
    assert (
        JavaAdapter().validar_oraculo(
            contrato, prueba.replace("(java.lang.String) null", "null"), tmp_path
        )
        is not None
    )
    assert (
        JavaAdapter().validar_oraculo(
            contrato,
            prueba.replace("(java.lang.String) null", "(Object) null"),
            tmp_path,
        )
        is not None
    )


def test_import_explicito_define_identidad_sin_elegir_por_nombre_simple(tmp_path):
    fuente = """import otro.String; public class Banco {
public static int f(String x) {return 1;}
public static int f(java.lang.String x) {return 2;}
public static int sano() {return 3;}}
"""
    (tmp_path / "Banco.java").write_text(fuente, encoding="utf-8")
    nombres = [
        f["nombre"] for f in JavaAdapter().analizar(tmp_path)["modulos"][0]["funciones"]
    ]
    assert nombres == [
        "Banco.f(otro.String)",
        "Banco.f(java.lang.String)",
        "Banco.sano",
    ]


def test_alias_con_tipo_object_no_suplanta_sobrecarga_string(tmp_path):
    fuente = FUENTE.replace(
        "public static int sano()",
        'public static String f(Object x) {return "hola";} public static int sano()',
    )
    contrato = preparar(tmp_path, "Banco.f(java.lang.String)", fuente)
    prueba = (
        codigo('"hola"', '"hola"')
        .replace(
            "@Test void test_normal() {",
            '@Test void test_normal() { Object dato = "hola";',
        )
        .replace('Banco.f("hola")', "Banco.f(dato)")
    )
    assert JavaAdapter().validar_oraculo(contrato, prueba, tmp_path) is not None
    assert (
        JavaAdapter().validar_oraculo(
            contrato, prueba.replace("Object dato", "String dato"), tmp_path
        )
        is None
    )
