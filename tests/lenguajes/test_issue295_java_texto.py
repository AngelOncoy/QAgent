"""Regresión String/CharSequence de #295: análisis estático, sin Java ni IA real."""

from copy import deepcopy

import pytest

from qagent import contracts
from qagent.lenguajes.java_laundering import comparar_java
from qagent.lenguajes.java_oraculo import validar_java

# Recuperado de commons-lang, corrida 20261117-001029-96fb. No depende de
# la carpeta local del repositorio externo ni ejecuta su implementación.
CONTRATO = {
    "version": "3",
    "lenguaje": "java",
    "framework_pruebas": "junit5",
    "modulo": "src/main/java/org/apache/commons/lang3/CharSequenceUtils.java",
    "huella": "72969fbeea9c3023ec675733f4a226a822e6b4f0fbd2fd818c3785c2ac77945a",
    "tipo": "funcion",
    "objetivo": "CharSequenceUtils.subSequence",
    "firma": "public static CharSequence subSequence(final CharSequence cs, final int start)",
    "critical": True,
    "llama_a": [],
    "casos": [
        {
            "id": "subsequence_normal_desde_indice",
            "entrada": {"cs": "abcde", "start": 2},
            "valor_esperado": "cde",
            "origen": "docstring",
            "categoria": "normal",
        }
    ],
}


def prueba(cuerpo: str) -> str:
    """Una clase JUnit con el nombre y paquete del objetivo original."""
    return f"""package org.apache.commons.lang3;
import org.junit.jupiter.api.Assertions;
import org.junit.jupiter.api.Test;
class CharSequenceUtilsTest {{
    @Test void test_subsequence_normal_desde_indice() {{
        {cuerpo}
    }}
}}
"""


DECLARACION = (
    'final CharSequence resultado = CharSequenceUtils.subSequence("abcde", 2);'
)
IGUALDAD = 'Assertions.assertEquals("cde", resultado.toString());'
CODIGO_ORIGINAL = prueba(
    DECLARACION + '\nAssertions.assertEquals("cde", String.valueOf(resultado));'
)


def test_regresion_del_rechazo_original() -> None:
    """La comparación exacta guardada debe poder llegar al sandbox."""
    contracts.validar_versionado(contracts.FAMILIA_PLANNER, CONTRATO)
    assert validar_java(CONTRATO, CODIGO_ORIGINAL) is None


@pytest.mark.parametrize("retorno", ["String", "CharSequence", "StringBuilder"])
@pytest.mark.parametrize("no_nulo", [False, True])
def test_conversion_textual_exacta(retorno: str, no_nulo: bool) -> None:
    """La igualdad conserva contenido; assertNotNull solo puede complementarla."""
    contrato = deepcopy(CONTRATO)
    contrato["firma"] = contrato["firma"].replace(
        "static CharSequence", f"static {retorno}"
    )
    cuerpo = DECLARACION.replace("final CharSequence", f"final {retorno}")
    if no_nulo:
        cuerpo += "\nAssertions.assertNotNull(resultado);"
    assert validar_java(contrato, prueba(cuerpo + "\n" + IGUALDAD)) is None


@pytest.mark.parametrize("inicio,esperado", [(0, "abcde"), (2, "cde"), (5, "")])
def test_indices_validos_y_contenido_vacio(inicio: int, esperado: str) -> None:
    """El esperado sigue siendo el del contrato para cada índice, incluido el final."""
    contrato = deepcopy(CONTRATO)
    contrato["casos"][0]["entrada"]["start"] = inicio
    contrato["casos"][0]["valor_esperado"] = esperado
    cuerpo = DECLARACION.replace(", 2)", f", {inicio})")
    cuerpo += f'\nAssertions.assertEquals("{esperado}", resultado.toString());'
    assert validar_java(contrato, prueba(cuerpo)) is None


def test_null_se_comprueba_sin_conversion() -> None:
    """Un resultado nulo se comprueba directamente, no como el texto null."""
    contrato = deepcopy(CONTRATO)
    contrato["casos"][0]["entrada"]["cs"] = None
    contrato["casos"][0]["valor_esperado"] = None
    cuerpo = "Assertions.assertNull(CharSequenceUtils.subSequence(null, 2));"
    assert validar_java(contrato, prueba(cuerpo)) is None


@pytest.mark.parametrize(
    "excepcion", ["IndexOutOfBoundsException", "IllegalStateException"]
)
def test_excepcion_debe_coincidir_con_el_contrato(excepcion: str) -> None:
    """No se acepta sustituir la excepción declarada por otra."""
    contrato = deepcopy(CONTRATO)
    caso = contrato["casos"][0]
    caso.pop("valor_esperado")
    caso["entrada"]["start"] = 20
    caso["excepcion"] = "IndexOutOfBoundsException"
    cuerpo = (
        f"Assertions.assertThrows({excepcion}.class, "
        '() -> CharSequenceUtils.subSequence("abcde", 20));'
    )
    error = validar_java(contrato, prueba(cuerpo))
    assert (error is None) == (excepcion == caso["excepcion"])


@pytest.mark.parametrize(
    "asercion",
    [
        "Assertions.assertNotNull(resultado);",
        'Assertions.assertEquals("incorrecto", resultado.toString());',
        'Assertions.assertEquals("cde", resultado.toString().trim());',
        'Assertions.assertEquals("cde", resultado.toString().toLowerCase());',
        'Assertions.assertEquals("cde", "cde");',
        'Assertions.assertEquals("cde", resultado);',
    ],
)
def test_rechaza_comparacion_debilitada_o_no_demostrable(asercion: str) -> None:
    """Ni existencia, coerciones, igualdad de objetos ni tautologías prueban contenido."""
    assert validar_java(CONTRATO, prueba(DECLARACION + asercion)) is not None


@pytest.mark.parametrize(
    "asercion",
    [
        "Assertions.assertNotNull(resultado);",
        'Assertions.assertEquals("incorrecto", resultado.toString());',
    ],
)
def test_anti_laundering_conserva_igualdad_y_esperado(asercion: str) -> None:
    """Un reintento no puede borrar la igualdad ni cambiar su expectativa."""
    original = prueba(DECLARACION + IGUALDAD)
    reparado = prueba(DECLARACION + asercion)
    assert comparar_java(original, reparado).es_laundering


def test_valueof_no_confunde_null_con_su_texto() -> None:
    """String.valueOf(null) no demuestra contenido textual igual a null."""
    contrato = deepcopy(CONTRATO)
    contrato["casos"][0]["valor_esperado"] = "null"
    codigo = CODIGO_ORIGINAL.replace('assertEquals("cde",', 'assertEquals("null",')
    assert validar_java(contrato, codigo) is not None


@pytest.mark.parametrize("retorno", ["int", "Object", "char[]", "otro.CharSequence"])
def test_no_convierte_tipos_ajenos_a_texto(retorno: str) -> None:
    contrato = deepcopy(CONTRATO)
    contrato["firma"] = contrato["firma"].replace(
        "static CharSequence", f"static {retorno}"
    )
    assert validar_java(contrato, CODIGO_ORIGINAL) is not None


@pytest.mark.parametrize(
    "apoyo",
    [
        'Assertions.assertNotNull("literal");',
        'Assertions.assertNotNull(CharSequenceUtils.subSequence("abcde", 2));',
        "Assertions.assertNotNull(resultado, Otra.mensaje());",
    ],
)
def test_no_nulo_no_puede_comprobar_otro_resultado(apoyo: str) -> None:
    assert validar_java(CONTRATO, prueba(DECLARACION + apoyo + IGUALDAD)) is not None


def test_texto_null_requiere_no_nulo_sobre_la_misma_evaluacion() -> None:
    contrato = deepcopy(CONTRATO)
    contrato["casos"][0]["valor_esperado"] = "null"
    igualdad = 'Assertions.assertEquals("null", String.valueOf(resultado));'
    apoyo = "Assertions.assertNotNull(resultado);"
    assert validar_java(contrato, prueba(DECLARACION + apoyo + igualdad)) is None
    assert validar_java(contrato, prueba(DECLARACION + igualdad + apoyo)) is not None


@pytest.mark.parametrize(
    "declaracion",
    [
        "import falso.String;",
        "import\tfalso.String;",
        "import falso./* oculto */String;",
    ],
)
def test_import_no_puede_sustituir_string(declaracion: str) -> None:
    codigo = CODIGO_ORIGINAL.replace(
        "import org.junit.jupiter.api.Test;",
        "import org.junit.jupiter.api.Test; " + declaracion,
    )
    assert validar_java(CONTRATO, codigo) is not None


def test_alias_de_conversion_y_nombre_completo() -> None:
    cuerpo = (
        DECLARACION
        + '\nString texto = java.lang.String.valueOf(resultado); Assertions.assertEquals("cde", texto);'
    )
    assert validar_java(CONTRATO, prueba(cuerpo)) is None


def test_sin_resultado_o_entrada_distinta_no_hay_oraculo() -> None:
    assert validar_java(CONTRATO, prueba(DECLARACION)) is not None
    assert validar_java(CONTRATO, CODIGO_ORIGINAL.replace(", 2)", ", 1)")) is not None


@pytest.mark.parametrize(
    "obtenido", ["resultado.toString()", "String.valueOf(resultado)"]
)
def test_null_esperado_no_admite_conversion(obtenido: str) -> None:
    contrato = deepcopy(CONTRATO)
    contrato["casos"][0]["valor_esperado"] = None
    codigo = prueba(DECLARACION + f"Assertions.assertEquals(null, {obtenido});")
    assert validar_java(contrato, codigo) is not None


def test_string_directo_y_nombre_completo_de_charsequence() -> None:
    contrato = deepcopy(CONTRATO)
    contrato["firma"] = contrato["firma"].replace(
        "static CharSequence", "static String"
    )
    codigo = prueba(DECLARACION + 'Assertions.assertEquals("cde", resultado);')
    assert validar_java(contrato, codigo) is None
    contrato["firma"] = CONTRATO["firma"].replace(
        "static CharSequence", "static java.lang.CharSequence"
    )
    assert validar_java(contrato, CODIGO_ORIGINAL) is None


def test_no_nulo_debe_preceder_a_la_conversion_guardada() -> None:
    cuerpo = (
        DECLARACION
        + "String texto = resultado.toString(); Assertions.assertNotNull(resultado);"
        + 'Assertions.assertEquals("cde", texto);'
    )
    assert validar_java(CONTRATO, prueba(cuerpo)) is not None
