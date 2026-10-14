"""Pruebas de GeneratorAgent sin utilizar una API real."""

from __future__ import annotations

import ast

import pytest

from pyagent import contracts
from pyagent.agents.generator import ErrorRespuestaGenerator, GeneratorAgent
from pyagent.llm import RespuestaLLM, TokenTracker

CONTRATO = {
    "version": "2",
    "modulo": "calculadora.py",
    "huella": "a" * 64,
    "tipo": "funcion",
    "objetivo": "duplicar",
    "firma": "(x: int) -> int",
    "critical": False,
    "llama_a": [],
    "casos": [
        {
            "id": "duplica_positivo",
            "entrada": {"x": 2},
            "valor_esperado": 4,
            "origen": "docstring",
        }
    ],
}

CONTRATO_ENDPOINT = {
    "version": "2",
    "modulo": "api_mvp.py",
    "huella": "b" * 64,
    "tipo": "endpoint",
    "objetivo": "POST /items",
    "manejador": "crear_item",
    "aplicacion": "app",
    "dependencias": [{"funcion": "obtener_repositorio", "reemplazo": "Repositorio"}],
    "firma": "(datos: ItemEntrada, repo=Depends(obtener_repositorio)) -> Item",
    "critical": False,
    "llama_a": [],
    "casos": [
        {
            "id": "crear_item",
            "entrada": {
                "metodo": "POST",
                "ruta": "/items",
                "json": {"nombre": "lapiz", "precio": 2.5},
            },
            "valor_esperado": {
                "status_code": 201,
                "json_contiene": {"nombre": "lapiz", "precio": 2.5},
            },
            "origen": "response_model",
        }
    ],
}

CODIGO = """\
from calculadora import duplicar


def test_duplica_positivo():
    assert duplicar(2) == 4
"""


class ClienteGrabado:
    """Cliente que devuelve código controlado."""

    def __init__(self, contenido: str) -> None:
        self.contenido = contenido
        self.llamadas: list[tuple[str, str]] = []

    def generar(self, prompt: str, rol: str = "generator") -> RespuestaLLM:
        self.llamadas.append((prompt, rol))
        return RespuestaLLM(
            contenido=self.contenido,
            tokens_entrada=80,
            tokens_salida=30,
            costo_usd=0.01,
            modelo="modelo-prueba",
        )


def test_generator_devuelve_generated_test_valido() -> None:
    cliente = ClienteGrabado(CODIGO)
    generator = GeneratorAgent(cliente, TokenTracker())

    resultado = generator.generar(CONTRATO, intento=1, feedback=None)

    assert contracts.es_valido(contracts.GENERATED_TEST, resultado)
    assert resultado["objetivo"] == "duplicar"
    assert resultado["intento"] == 1
    assert resultado["casos_cubiertos"] == ["duplica_positivo"]
    ast.parse(resultado["codigo"])


def test_generator_conserva_el_valor_esperado() -> None:
    cliente = ClienteGrabado(CODIGO)
    generator = GeneratorAgent(cliente, TokenTracker())

    resultado = generator.generar(CONTRATO, 1, None)

    assert "assert duplicar(2) == 4" in resultado["codigo"]


def test_generator_incluye_feedback_en_reintento() -> None:
    cliente = ClienteGrabado(CODIGO)
    generator = GeneratorAgent(cliente, TokenTracker())

    generator.generar(
        CONTRATO,
        intento=2,
        feedback="SyntaxError: se esperaba ':' en la línea 4.",
    )

    prompt, rol = cliente.llamadas[0]
    assert rol == "generator"
    assert "intento 2" in prompt
    assert "SyntaxError" in prompt
    assert "se esperaba ':'" in prompt


def test_generator_elimina_cerca_markdown() -> None:
    cliente = ClienteGrabado(f"```python\n{CODIGO}```")
    generator = GeneratorAgent(cliente, TokenTracker())

    resultado = generator.generar(CONTRATO, 1, None)

    assert not resultado["codigo"].startswith("```")
    ast.parse(resultado["codigo"])


def test_generator_registra_tokens() -> None:
    tracker = TokenTracker()
    generator = GeneratorAgent(ClienteGrabado(CODIGO), tracker)

    generator.generar(CONTRATO, 1, None)

    [llamada] = tracker.llamadas
    assert llamada.agente == "generator"
    assert llamada.tokens_entrada == 80
    assert llamada.tokens_salida == 30


def test_generator_rechaza_respuesta_vacia() -> None:
    generator = GeneratorAgent(ClienteGrabado(""), TokenTracker())

    with pytest.raises(ErrorRespuestaGenerator, match="vacío"):
        generator.generar(CONTRATO, 1, None)


def test_generator_rechaza_codigo_que_no_pasa_ast_parse() -> None:
    generator = GeneratorAgent(ClienteGrabado("def test_invalido(\n"), TokenTracker())

    with pytest.raises(ErrorRespuestaGenerator, match="Python inválido"):
        generator.generar(CONTRATO, 1, None)


def test_prompt_indica_como_importar_el_objetivo() -> None:
    cliente = ClienteGrabado(CODIGO)
    contrato = {**CONTRATO, "modulo": "bench/banco_mvp.py"}

    GeneratorAgent(cliente, TokenTracker()).generar(contrato, 1, None)

    assert "from bench.banco_mvp import duplicar" in cliente.llamadas[0][0]


def test_feedback_largo_se_recorta_al_final() -> None:
    cliente = ClienteGrabado(CODIGO)
    feedback = "x" * 10_000 + "ImportError: al final"

    GeneratorAgent(cliente, TokenTracker()).generar(CONTRATO, 2, feedback)

    prompt = cliente.llamadas[0][0]
    assert "ImportError: al final" in prompt
    assert len(prompt) < 5_000


def test_prompt_endpoint_exige_testclient_y_overrides_seguros() -> None:
    cliente = ClienteGrabado(CODIGO)

    GeneratorAgent(cliente, TokenTracker()).generar(CONTRATO_ENDPOINT, 1, None)

    prompt = cliente.llamadas[0][0]
    assert "fastapi.testclient.TestClient" in prompt
    assert "from api_mvp import app, obtener_repositorio, Repositorio" in prompt
    assert "app.dependency_overrides[funcion] = reemplazo" in prompt
    assert "limpia el diccionario" in prompt
    assert "Nunca reemplaces el manejador" in prompt
    assert "response.status_code" in prompt
    assert "response.json()" in prompt
