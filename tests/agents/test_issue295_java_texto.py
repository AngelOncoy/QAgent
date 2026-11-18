"""Generator real y oráculo Java con respuesta grabada, cero tokens (#295)."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from qagent.agents.generator import GeneratorAgent
from qagent.lenguajes import JavaAdapter
from qagent.llm import TokenTracker
from tests.agents.test_generator_java import ClienteJUnitGrabado
from tests.lenguajes.test_issue295_java_texto import (
    CODIGO_ORIGINAL,
    CONTRATO,
    DECLARACION,
    IGUALDAD,
    prueba,
)


def preparar_texto(raiz: Path, implementacion: str = "correcta") -> dict:
    """Fixture mínima independiente de Commons Lang; solo escribe fuentes Java."""
    cuerpo = {
        "correcta": "return cs == null ? null : cs.subSequence(start, cs.length());",
        "builder": "return cs == null ? null : new StringBuilder(cs.subSequence(start, cs.length()));",
        "defectuosa": 'return "incorrecto";',
        "nula": "return null;",
    }[implementacion]
    archivo = raiz / CONTRATO["modulo"]
    archivo.parent.mkdir(parents=True)
    archivo.write_text(
        "package org.apache.commons.lang3; public class CharSequenceUtils {"
        "/** Devuelve la subsecuencia desde start, o null si cs es null. */"
        + CONTRATO["firma"]
        + " {"
        + cuerpo
        + "}}",
        encoding="utf-8",
    )
    (raiz / "pom.xml").write_text(
        '<project xmlns="http://maven.apache.org/POM/4.0.0"><modelVersion>4.0.0</modelVersion>'
        "<groupId>ejemplo</groupId><artifactId>texto</artifactId><version>1</version>"
        "<properties><maven.compiler.release>21</maven.compiler.release></properties></project>",
        encoding="utf-8",
    )
    contrato = deepcopy(CONTRATO)
    contrato["huella"] = JavaAdapter().analizar(raiz)["modulos"][0]["huella"]
    return contrato


CODIGO_CANONICO = prueba(
    DECLARACION + "Assertions.assertNotNull(resultado);" + IGUALDAD
)


def casos_de_borde(contrato: dict) -> str:
    """Casos documentados fijos, no calculados ejecutando la implementación."""
    entradas = [
        ("inicio", "abcde", 0, "abcde"),
        ("vacio", "abcde", 5, ""),
        ("nulo", None, 0, None),
        ("texto_null", "null", 0, "null"),
        ("indice_invalido", "abcde", 20, None),
    ]
    contrato["casos"] = []
    metodos = []
    for nombre, entrada, inicio, esperado in entradas:
        caso = {
            "id": nombre,
            "entrada": {"cs": entrada, "start": inicio},
            "origen": "docstring",
            "categoria": "limite",
        }
        llamada = f"CharSequenceUtils.subSequence({json.dumps(entrada)}, {inicio})"
        if nombre == "indice_invalido":
            caso.update(excepcion="IndexOutOfBoundsException", categoria="error")
            cuerpo = f"Assertions.assertThrows(IndexOutOfBoundsException.class, () -> {llamada});"
        else:
            caso["valor_esperado"] = esperado
            cuerpo = f"CharSequence r = {llamada};"
            if esperado is None:
                cuerpo += "Assertions.assertNull(r);"
            else:
                cuerpo += f"Assertions.assertNotNull(r); Assertions.assertEquals({json.dumps(esperado)}, String.valueOf(r));"
        contrato["casos"].append(caso)
        metodos.append(f"@Test void test_{nombre}() {{ {cuerpo} }}")
    return (
        "package org.apache.commons.lang3; import org.junit.jupiter.api.Test; "
        "import org.junit.jupiter.api.Assertions; class CharSequenceUtilsTest {"
        + "\n".join(metodos)
        + "}"
    )


def test_varios_casos_textuales_conservan_contrato(tmp_path: Path) -> None:
    contrato = preparar_texto(tmp_path)
    codigo = casos_de_borde(contrato)
    generado = GeneratorAgent(
        ClienteJUnitGrabado(codigo),
        TokenTracker(),
        es_simulado=True,
        ruta_proyecto=tmp_path,
    ).generar(contrato, 1, None)
    assert JavaAdapter().validar_oraculo(contrato, generado["codigo"], tmp_path) is None


@pytest.mark.parametrize("codigo", [CODIGO_ORIGINAL, CODIGO_CANONICO])
def test_generacion_y_validacion_textual_integradas(
    tmp_path: Path, codigo: str
) -> None:
    contrato = preparar_texto(tmp_path)
    cliente = ClienteJUnitGrabado(codigo)
    tracker = TokenTracker()
    generado = GeneratorAgent(
        cliente, tracker, es_simulado=True, ruta_proyecto=tmp_path
    ).generar(contrato, 1, None)
    assert generado["codigo"] == codigo
    assert JavaAdapter().validar_oraculo(contrato, generado["codigo"], tmp_path) is None
    assert tracker.total_tokens == 0
    assert "assertNotNull(resultado)" in cliente.prompts[0]
    assert "assertNull(resultado)" in cliente.prompts[0]
    assert "resultado.toString()" in cliente.prompts[0]
    assert not (tmp_path / "src/test").exists()
