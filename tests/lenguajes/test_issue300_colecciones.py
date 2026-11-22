"""Misma capacidad en Planner, contexto del Generator y guardrail, sin ejecutar Java."""

from copy import deepcopy

import pytest

from qagent.lenguajes import JavaAdapter
from qagent.lenguajes.java_colecciones import compatible_coleccion, expresion_coleccion
from qagent.lenguajes.java_generacion import contexto_java, prompt_java
from qagent.lenguajes.java_laundering import comparar_java
from qagent.lenguajes.java_planificacion import REGLAS_PLANIFICACION_JAVA, _compatible
from tests.agents.test_generator_java import preparar


def proyecto(
    raiz,
    tipo,
    esperado,
    *,
    parametro="",
    entrada=None,
    doc="Devuelve los elementos en orden de iteración documentado; null si corresponde.",
):
    fuente = f"package ejemplo; import java.util.*; public class Banco {{ /** {doc} @return {doc} */ public static {tipo} valores({parametro}) {{ return null; }} }}"
    contrato = preparar(raiz, fuente, "Banco.valores")
    contrato["casos"][0].update(
        entrada=[] if entrada is None else entrada, valor_esperado=deepcopy(esperado)
    )
    funcion = JavaAdapter().analizar(raiz)["modulos"][0]["funciones"][0]
    return contrato, funcion


def prueba(cuerpo, imports="import java.util.*;"):
    return f"package ejemplo; {imports} import org.junit.jupiter.api.Test; import static org.junit.jupiter.api.Assertions.*; class BancoTest {{ @Test void test_positivo() {{ {cuerpo} }} }}"


@pytest.mark.parametrize(
    "tipo,valor",
    [
        ("List<String>", ["uno", "uno", "dos"]),
        ("Set<String>", ["uno", "dos"]),
        ("java.util.Set<java.lang.String>", []),
        ("List<String>", [None]),
        ("Set<String>", [None]),
        ("List<String>", ["uno", None, "uno"]),
        ("Set<String>", ["uno", None]),
        ("Set<Integer>", [1, 2]),
        ("Set<Long>", [1, 2**60]),
        ("List<Boolean>", [True, False, True]),
        ("List<Byte>", [-128, 127]),
        ("List<Short>", [-32768, 32767]),
        ("List<Character>", ["'", "\n", "\x00", "á"]),
        ("Set<Double>", [1.0, 0.1]),
        ("Set<Float>", [1.5, 2.5]),
        ("List<List<Integer>>", [[1, 2], [], [1, 2]]),
        ("Set<List<Integer>>", [[1, 2], [2, 1]]),
        ("List<Set<String>>", [["a", "b"], ["c"]]),
        ("Set<Set<String>>", [["a", "b"], ["c"]]),
        ("Collection<String>", ["a", "b", "a"]),
        ("java.lang.Iterable<List<Integer>>", [[1, 2], []]),
        ("List<String>", None),
        ("Set<String>", None),
        ("Iterable<String>", None),
    ],
)
def test_capacidad_compartida_y_forma_canonica_demostrable(tmp_path, tipo, valor):
    contrato, funcion = proyecto(tmp_path, tipo, valor)
    assert _compatible(tipo, valor)
    assert (
        REGLAS_PLANIFICACION_JAVA.motivo_oraculo_funcion(funcion, contrato["casos"][0])
        is None
    )
    contexto = contexto_java(contrato, tmp_path)
    representacion = contexto["colecciones_verificables"][0]
    expresion = representacion["esperado_java"]
    asercion = representacion["asercion"]
    codigo = prueba(
        f"{asercion}({expresion},Banco.valores());"
        if valor is not None
        else "assertNull(Banco.valores());"
    )
    assert JavaAdapter().validar_oraculo(contrato, codigo, tmp_path) is None
    assert "colecciones_verificables" in prompt_java(contrato, 1, None, tmp_path)


@pytest.mark.parametrize(
    "tipo,valor",
    [
        ("Set<String>", ["a", "a"]),
        ("Set<Set<String>>", [["a", "b"], ["b", "a"]]),
        ("Set<String>", [None, None]),
        ("Map<String,Integer>", {"a": 1}),
        ("List<Object>", ["a"]),
        ("List<CharSequence>", ["a"]),
        ("List<int[]>", [[1]]),
        ("Set<?>", ["a"]),
        ("Set", []),
        ("List<Collection<String>>", [["a"]]),
        ("Iterable<Set<String>>", [["a"]]),
        ("java.util.Iterable<String>", ["a"]),
        ("otro.Set<String>", ["a"]),
        ("List<Double>", [float("inf")]),
        ("List<Float>", [-0.0]),
        ("List<Character>", ["😀"]),
    ],
)
def test_no_ofrece_contenido_que_no_pueda_validar(tmp_path, tipo, valor):
    contrato, funcion = proyecto(tmp_path, tipo, valor)
    assert not compatible_coleccion(tipo, valor)
    assert not _compatible(tipo, valor)
    assert (
        REGLAS_PLANIFICACION_JAVA.motivo_oraculo_funcion(funcion, contrato["casos"][0])
        is not None
    )
    with pytest.raises(ValueError):
        contexto_java(contrato, tmp_path)


@pytest.mark.parametrize("tipo", ["Set<String>", "List<String>"])
def test_orden_y_duplicados_no_se_confunden(tmp_path, tipo):
    contrato, _ = proyecto(tmp_path, tipo, ["uno", "dos"])
    fabrica = tipo.split("<")[0]
    codigo = prueba(f'assertEquals({fabrica}.of("dos","uno"),Banco.valores());')
    assert (
        JavaAdapter().validar_oraculo(contrato, codigo, tmp_path) is None
    ) == tipo.startswith("Set")


@pytest.mark.parametrize(
    "cuerpo",
    [
        'assertEquals(Set.of("otro"),Banco.valores());',
        'assertEquals(List.of("uno"),Banco.valores());',
        'assertEquals(Set.of("uno"),Otra.valores());',
        'assertEquals(Set.of("uno"),Banco.valores("extra"));',
        'assertSame(Set.of("uno"),Banco.valores());',
        'assertIterableEquals(Set.of("uno"),Banco.valores());',
        'assertEquals(Set.of("uno"),Set.of("uno"));',
        'assertEquals(Set.of("uno"),new HashSet<>(Banco.valores()));',
        'assertTrue(Banco.valores().contains("uno"));',
        "assertNotNull(Banco.valores());",
        'assertEquals(new HashSet<>(Arrays.asList("uno","uno")),Banco.valores());',
    ],
)
def test_rechaza_esperado_sujeto_identidad_o_comprobacion_debilitada(tmp_path, cuerpo):
    contrato, _ = proyecto(tmp_path, "Set<String>", ["uno"])
    assert JavaAdapter().validar_oraculo(contrato, prueba(cuerpo), tmp_path) is not None


@pytest.mark.parametrize(
    "tipo,codigo",
    [
        ("List<Long>", "List.of(1)"),
        ("List<Integer>", "List.of(1L)"),
        ("Set<Double>", "Set.of(1)"),
        ("Set<Float>", "Set.of(1.0d)"),
        ("List<Character>", 'List.of("a")'),
        ("Set<Byte>", "Set.of((byte)257)"),
    ],
)
def test_tipo_boxed_del_elemento_no_se_adivina(tmp_path, tipo, codigo):
    valor = ["a"] if "Character" in tipo else [1]
    contrato, _ = proyecto(tmp_path, tipo, valor)
    assert (
        JavaAdapter().validar_oraculo(
            contrato, prueba(f"assertEquals({codigo},Banco.valores());"), tmp_path
        )
        is not None
    )


@pytest.mark.parametrize(
    "tipo,fabrica", [("List<String>", "List"), ("Set<String>", "Set")]
)
def test_of_no_admite_null_pero_la_forma_nulable_si(tmp_path, tipo, fabrica):
    contrato, _ = proyecto(tmp_path, tipo, [None])
    assert (
        JavaAdapter().validar_oraculo(
            contrato,
            prueba(f"assertEquals({fabrica}.of(null),Banco.valores());"),
            tmp_path,
        )
        is not None
    )
    expresion = expresion_coleccion(tipo, [None])
    assert (
        JavaAdapter().validar_oraculo(
            contrato, prueba(f"assertEquals({expresion},Banco.valores());"), tmp_path
        )
        is None
    )


def test_inputs_de_set_conservan_semantica_y_no_aceptan_lista_o_elemento_distinto(
    tmp_path,
):
    contrato, funcion = proyecto(
        tmp_path,
        "List<String>",
        ["ok"],
        parametro="Set<String> datos",
        entrada={"datos": ["a", "b"]},
    )
    assert not REGLAS_PLANIFICACION_JAVA.es_caso_trivial(funcion, contrato["casos"][0])
    correcto = 'assertEquals(List.of("ok"),Banco.valores(Set.of("b","a")));'
    assert JavaAdapter().validar_oraculo(contrato, prueba(correcto), tmp_path) is None
    for cambio in ['List.of("a","b")', 'Set.of("a","c")']:
        assert (
            JavaAdapter().validar_oraculo(
                contrato, prueba(correcto.replace('Set.of("b","a")', cambio)), tmp_path
            )
            is not None
        )


@pytest.mark.parametrize(
    "imports",
    [
        "import falso.Set; import java.util.*;",
        "import\tfalso.Set; import java.util.*;",
        "import falso./* oculto */Set; import java.util.*;",
        "import java.util.*; import falso.*;",
    ],
)
def test_factory_homonima_no_se_confunde_con_java_util(tmp_path, imports):
    contrato, _ = proyecto(tmp_path, "Set<String>", ["uno"])
    assert (
        JavaAdapter().validar_oraculo(
            contrato,
            prueba('assertEquals(Set.of("uno"),Banco.valores());', imports),
            tmp_path,
        )
        is not None
    )


def test_source_type_homonimo_se_rechaza_en_analisis_y_contexto(tmp_path):
    contrato, _ = proyecto(tmp_path, "Set<String>", ["uno"])
    ruta = tmp_path / contrato["modulo"]
    ruta.write_text(
        ruta.read_text(encoding="utf-8").replace(
            "import java.util.*;", "import otro.Set;"
        ),
        encoding="utf-8",
    )
    funcion = JavaAdapter().analizar(tmp_path)["modulos"][0]["funciones"][0]
    assert (
        REGLAS_PLANIFICACION_JAVA.motivo_oraculo_funcion(funcion, contrato["casos"][0])
        is not None
    )
    with pytest.raises(ValueError, match="colección no verificable"):
        contexto_java(contrato, tmp_path)


def test_laundering_solo_permite_permutar_set_no_lista():
    for tipo in ["Set", "List"]:
        original = prueba(f'assertEquals({tipo}.of("a","b"),Banco.valores());')
        permutada = original.replace('"a","b"', '"b","a"')
        assert comparar_java(original, permutada).es_laundering == (tipo == "List")
        assert comparar_java(original, original.replace('"a"', '"c"')).es_laundering
        assert comparar_java(
            original,
            original.replace(tipo + ".of", "Arrays.asList")
            if tipo == "Set"
            else original.replace("List.of", "Set.of"),
        ).es_laundering


def test_collection_no_inventa_orden_no_declarado(tmp_path):
    contrato, funcion = proyecto(
        tmp_path,
        "Collection<String>",
        ["a", "b"],
        doc="Devuelve a y b sin orden garantizado.",
    )
    assert (
        "orden de iteración documentado"
        in REGLAS_PLANIFICACION_JAVA.motivo_oraculo_funcion(
            funcion, contrato["casos"][0]
        )
    )


@pytest.mark.parametrize(
    "tipo,valor,expresion",
    [
        ("List<String>", [None], "Arrays.asList(null)"),
        ("Set<String>", [None], "new HashSet<>(Arrays.asList(null))"),
        ("List<Double>", [0.0], "List.of(-0.0d)"),
        ("List<Float>", [0.0], "List.of(-0.0f)"),
    ],
)
def test_formas_que_no_representan_el_valor_json_se_rechazan(
    tmp_path, tipo, valor, expresion
):
    contrato, _ = proyecto(tmp_path, tipo, valor)
    assert (
        JavaAdapter().validar_oraculo(
            contrato, prueba(f"assertEquals({expresion},Banco.valores());"), tmp_path
        )
        is not None
    )


@pytest.mark.parametrize("familia", ["List", "Set"])
def test_sobrecargas_list_y_set_conservan_tipo_exacto(tmp_path, familia):
    fuente = """package ejemplo; import java.util.List; import java.util.Set; public class Banco {
      /** Devuelve el conjunto uno. @return conjunto uno */
      public static Set<String> valores(List<String> x) { return Set.of("uno"); }
      /** Devuelve el conjunto uno. @return conjunto uno */
      public static Set<String> valores(Set<String> x) { return Set.of("uno"); }
    }"""
    contrato = preparar(tmp_path, fuente, f"Banco.valores(java.util.{familia})")
    contrato["casos"][0].update(entrada={"x": ["uno"]}, valor_esperado=["uno"])
    codigo = prueba(f'assertEquals(Set.of("uno"),Banco.valores({familia}.of("uno")));')
    assert JavaAdapter().validar_oraculo(contrato, codigo, tmp_path) is None
    otra = "Set" if familia == "List" else "List"
    assert (
        JavaAdapter().validar_oraculo(
            contrato,
            codigo.replace(f"valores({familia}.of", f"valores({otra}.of"),
            tmp_path,
        )
        is not None
    )


@pytest.mark.parametrize("tipo", ["Collection<String>", "Iterable<String>"])
def test_sobrecargas_de_interfaces_no_prometen_resolucion_ambigua(tipo):
    funcion = {
        "nombre": "Banco.valores(java.util.Collection)",
        "parametros": [{"nombre": "x", "tipo": tipo}],
    }
    assert REGLAS_PLANIFICACION_JAVA.es_caso_trivial(
        funcion, {"entrada": {"x": ["uno"]}}
    )


def test_varargs_de_colecciones_no_se_ofrece():
    funcion = {"parametros": [{"nombre": "x", "tipo": "Set<String>..."}]}
    assert REGLAS_PLANIFICACION_JAVA.es_caso_trivial(
        funcion, {"entrada": {"x": [["uno"]]}}
    )


def test_variable_java_no_sustituye_la_fabrica_calificada(tmp_path):
    contrato, _ = proyecto(tmp_path, "Set<String>", ["uno"])
    codigo = prueba(
        'String java="oculto"; assertEquals(java.util.Set.of("uno"),Banco.valores());'
    )
    assert JavaAdapter().validar_oraculo(contrato, codigo, tmp_path) is not None


@pytest.mark.parametrize(
    "nombre,valor",
    [
        ("Banco.valores(Set)", ["uno"]),
        ("Banco.valores(java.util.Set)", ["uno", None]),
    ],
)
def test_sobrecarga_no_ofrece_fabrica_con_despacho_sin_demostrar(nombre, valor):
    funcion = {"nombre": nombre, "parametros": [{"nombre": "x", "tipo": "Set<String>"}]}
    assert REGLAS_PLANIFICACION_JAVA.es_caso_trivial(funcion, {"entrada": {"x": valor}})
