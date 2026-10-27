"""Regresión de la issue #145: oráculos de funciones que devuelven tuplas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from qagent import contracts
from qagent.agents.generator import GeneratorAgent
from qagent.agents.planner import PlannerAgent
from qagent.agents.reviewer import ReviewerAgent
from qagent.analysis import analizar_proyecto, comparar_aserciones
from qagent.llm import RespuestaLLM, TokenTracker
from qagent.llm.fake import generar_test_desde_contrato
from qagent.sandbox import ResultadoSandbox


def _caso(
    valor: Any,
    *,
    tipo: str | None = "tuple",
    origen: str = "docstring",
) -> dict[str, Any]:
    caso = {
        "id": "dimensiones",
        "entrada": {"alto": 4, "ancho": 3},
        "valor_esperado": valor,
        "origen": origen,
    }
    if tipo is not None:
        caso["tipo_valor_esperado"] = tipo
    return caso


def _contrato(
    caso: dict[str, Any], *, firma: str = "(alto: int, ancho: int) -> tuple[int, int]"
) -> dict[str, Any]:
    return {
        "version": "2",
        "modulo": "dimensiones.py",
        "huella": "a" * 64,
        "tipo": "funcion",
        "objetivo": "alto_y_ancho",
        "firma": firma,
        "critical": False,
        "llama_a": [],
        "casos": [caso],
    }


class ClienteGrabado:
    """Cliente determinista para probar Planner sin red ni API real."""

    def __init__(self, contenido: str) -> None:
        self.contenido = contenido
        self.prompts: list[str] = []

    def generar(self, prompt: str, rol: str = "planner") -> RespuestaLLM:
        self.prompts.append(prompt)
        return RespuestaLLM(
            contenido=self.contenido,
            tokens_entrada=1,
            tokens_salida=1,
            costo_usd=0.0,
            modelo="simulado-issue-145",
        )


class EjecutorAprobado:
    """Sandbox sustituido que registra si Reviewer llegó a ejecutar el test."""

    def __init__(self) -> None:
        self.llamadas = 0

    def __call__(
        self, imagen: str, proyecto: Path, tests: Path, modulo: str
    ) -> ResultadoSandbox:
        self.llamadas += 1
        return ResultadoSandbox(0, "1 passed", "", duracion_s=0.01)


@pytest.mark.parametrize("valor", [[], [4], [4, 3], [-4, "ancho", True]])
def test_contrato_admite_metadata_de_tupla(valor: list[Any]) -> None:
    contrato = _contrato(_caso(valor))

    assert contracts.es_valido(contracts.PLANNER, contrato)


def test_contrato_anterior_sin_metadata_conserva_lista() -> None:
    caso = _caso([4, 3], tipo=None)
    contrato = _contrato(caso, firma="(alto: int, ancho: int) -> list[int]")

    assert contracts.es_valido(contracts.PLANNER, contrato)
    assert contracts.valor_esperado_python(caso) == [4, 3]
    assert isinstance(contracts.valor_esperado_python(caso), list)


@pytest.mark.parametrize("tipo", ["list", "set", "", 1])
def test_contrato_rechaza_metadata_de_tipo_invalida(tipo: Any) -> None:
    assert not contracts.es_valido(
        contracts.PLANNER, _contrato(_caso([4, 3], tipo=tipo))
    )


def test_contrato_rechaza_metadata_de_tupla_con_valor_no_array() -> None:
    assert not contracts.es_valido(contracts.PLANNER, _contrato(_caso(4)))


def test_contrato_v3_conserva_metadata_al_normalizar() -> None:
    normalizado = contracts.normalizar_planner(_contrato(_caso([4, 3])))

    assert normalizado["version"] == "3"
    assert normalizado["casos"][0]["tipo_valor_esperado"] == "tuple"
    assert contracts.es_valido(contracts.PLANNER_V3, normalizado)


def test_endpoint_no_admite_metadata_python_de_tupla() -> None:
    contrato = {
        "version": "2",
        "modulo": "api.py",
        "huella": "a" * 64,
        "tipo": "endpoint",
        "objetivo": "GET /dimensiones",
        "manejador": "dimensiones",
        "aplicacion": "app",
        "dependencias": [],
        "firma": "() -> list[int]",
        "critical": False,
        "casos": [
            {
                "id": "dimensiones",
                "entrada": {"metodo": "GET", "ruta": "/dimensiones"},
                "valor_esperado": {"status_code": 200, "json": [4, 3]},
                "tipo_valor_esperado": "tuple",
                "origen": "docstring",
            }
        ],
    }

    assert not contracts.es_valido(contracts.PLANNER, contrato)


def test_contrato_v3_no_aplica_metadata_python_a_typescript() -> None:
    contrato = {
        **_contrato(_caso([4, 3])),
        "version": "3",
        "lenguaje": "typescript",
        "framework_pruebas": "vitest",
    }

    assert not contracts.es_valido(contracts.PLANNER_V3, contrato)


@pytest.mark.parametrize(
    "firma",
    [
        "(alto: int, ancho: int) -> tuple[int, int]",
        "(alto: int, ancho: int) -> typing.Tuple[int, int]",
    ],
)
def test_planner_preserva_tupla_documentada(firma: str) -> None:
    modulo = {
        "ruta": "dimensiones.py",
        "huella": "a" * 64,
        "funciones": [
            {
                "nombre": "alto_y_ancho",
                "firma": firma,
                "retorno": firma.split("->", 1)[1].strip(),
                "docstring": "Ejemplo: alto_y_ancho(4, 3) -> (4, 3)",
                "llama_a": [],
            }
        ],
    }
    propuesta = [{"objetivo": "alto_y_ancho", "casos": [_caso([4, 3], tipo=None)]}]

    [contrato] = PlannerAgent(
        ClienteGrabado(json.dumps(propuesta)), TokenTracker(), es_simulado=True
    ).planificar(modulo)

    assert contrato["casos"][0]["tipo_valor_esperado"] == "tuple"
    assert contracts.valor_esperado_python(contrato["casos"][0]) == (4, 3)


def test_planner_no_inventa_valores_desde_el_tipo_tupla() -> None:
    modulo = {
        "ruta": "dimensiones.py",
        "huella": "a" * 64,
        "funciones": [
            {
                "nombre": "alto_y_ancho",
                "firma": "(alto: int, ancho: int) -> tuple[int, int]",
                "retorno": "tuple[int, int]",
                "docstring": "Devuelve una tupla con alto y ancho.",
                "llama_a": [],
            }
        ],
    }
    propuesta = [
        {
            "objetivo": "alto_y_ancho",
            "casos": [_caso([4, 3], tipo=None, origen="tipo")],
        }
    ]
    planner = PlannerAgent(
        ClienteGrabado(json.dumps(propuesta)), TokenTracker(), es_simulado=True
    )

    assert planner.planificar(modulo) == []
    assert "alto_y_ancho" in planner.omitidas


def test_planner_reconoce_tupla_literal_documentada_sin_anotacion() -> None:
    modulo = {
        "ruta": "dimensiones.py",
        "huella": "a" * 64,
        "funciones": [
            {
                "nombre": "alto_y_ancho",
                "firma": "(alto: int, ancho: int)",
                "docstring": "Ejemplo: alto_y_ancho(4, 3) -> (4, 3)",
                "llama_a": [],
            }
        ],
    }
    propuesta = [{"objetivo": "alto_y_ancho", "casos": [_caso([4, 3], tipo=None)]}]

    [contrato] = PlannerAgent(
        ClienteGrabado(json.dumps(propuesta)), TokenTracker(), es_simulado=True
    ).planificar(modulo)

    assert contrato["casos"][0]["tipo_valor_esperado"] == "tuple"


def test_planner_rechaza_tupla_que_contradice_el_docstring() -> None:
    modulo = {
        "ruta": "dimensiones.py",
        "huella": "a" * 64,
        "funciones": [
            {
                "nombre": "alto_y_ancho",
                "firma": "(alto: int, ancho: int) -> tuple[int, int]",
                "retorno": "tuple[int, int]",
                "docstring": "Ejemplo: alto_y_ancho(4, 3) -> (4, 3)",
                "llama_a": [],
            }
        ],
    }
    propuesta = [{"objetivo": "alto_y_ancho", "casos": [_caso([4, 4], tipo=None)]}]
    planner = PlannerAgent(
        ClienteGrabado(json.dumps(propuesta)), TokenTracker(), es_simulado=True
    )

    assert planner.planificar(modulo) == []
    assert "alto_y_ancho" in planner.omitidas


def test_planner_no_convierte_una_lista_documentada_en_tupla() -> None:
    modulo = {
        "ruta": "dimensiones.py",
        "huella": "a" * 64,
        "funciones": [
            {
                "nombre": "alto_y_ancho",
                "firma": "(alto: int, ancho: int) -> list[int]",
                "retorno": "list[int]",
                "docstring": "Ejemplo: alto_y_ancho(4, 3) -> [4, 3]",
                "llama_a": [],
            }
        ],
    }
    propuesta = [{"objetivo": "alto_y_ancho", "casos": [_caso([4, 3], tipo=None)]}]

    [contrato] = PlannerAgent(
        ClienteGrabado(json.dumps(propuesta)), TokenTracker(), es_simulado=True
    ).planificar(modulo)

    assert "tipo_valor_esperado" not in contrato["casos"][0]
    assert contracts.valor_esperado_python(contrato["casos"][0]) == [4, 3]


def test_generator_simulado_genera_comparacion_exacta_con_tupla() -> None:
    codigo = generar_test_desde_contrato(_contrato(_caso([4, 3])))

    assert "assert alto_y_ancho(alto=4, ancho=3) == (4, 3)" in codigo
    assert "list(" not in codigo


def test_generator_simulado_conserva_comparacion_con_lista_antigua() -> None:
    codigo = generar_test_desde_contrato(
        _contrato(
            _caso([4, 3], tipo=None), firma="(alto: int, ancho: int) -> list[int]"
        )
    )

    assert "assert alto_y_ancho(alto=4, ancho=3) == [4, 3]" in codigo


@pytest.mark.parametrize(
    ("valor", "literal"),
    [([], "()"), ([4], "(4,)"), ([-4, "ancho", True], "(-4, 'ancho', True)")],
)
def test_generator_simulado_representa_formas_de_tupla(
    valor: list[Any], literal: str
) -> None:
    codigo = generar_test_desde_contrato(_contrato(_caso(valor)))

    assert f"== {literal}" in codigo


def test_prompt_generator_explica_semantica_sin_debilitar_asercion() -> None:
    codigo = (
        "from dimensiones import alto_y_ancho\n\n"
        "def test_dimensiones():\n"
        "    assert alto_y_ancho(alto=4, ancho=3) == (4, 3)\n"
    )
    cliente = ClienteGrabado(codigo)

    GeneratorAgent(cliente, TokenTracker()).generar(_contrato(_caso([4, 3])), 1, None)

    prompt = cliente.prompts[0]
    assert '"tipo_valor_esperado": "tuple"' in prompt
    assert "literal tupla" in prompt
    assert "list()" in prompt


@pytest.mark.parametrize(
    ("codigo", "es_valido"),
    [
        ("resultado = alto_y_ancho(4, 3)\nassert resultado == (4, 3)\n", True),
        ("resultado = alto_y_ancho(4, 3)\nassert resultado == [4, 3]\n", False),
        ("resultado = alto_y_ancho(4, 3)\nassert resultado == (4, 4)\n", False),
        ("resultado = alto_y_ancho(4, 3)\nassert len(resultado) == 2\n", False),
        ("resultado = alto_y_ancho(4, 3)\nassert resultado[0] == 4\n", False),
        ("resultado = alto_y_ancho(4, 3)\nassert resultado != (4, 3)\n", False),
        ("otra = (4, 3)\nassert otra == (4, 3)\n", False),
    ],
)
def test_reviewer_valida_semantica_y_contexto_de_tupla(
    codigo: str, es_valido: bool
) -> None:
    problema = ReviewerAgent._validar_oraculo(_contrato(_caso([4, 3])), codigo)

    assert (problema is None) is es_valido


def test_reviewer_conserva_validacion_exacta_de_lista() -> None:
    contrato = _contrato(
        _caso([4, 3], tipo=None), firma="(alto: int, ancho: int) -> list[int]"
    )

    assert (
        ReviewerAgent._validar_oraculo(
            contrato,
            "resultado = alto_y_ancho(4, 3)\nassert resultado == [4, 3]\n",
        )
        is None
    )
    assert ReviewerAgent._validar_oraculo(
        contrato,
        "resultado = alto_y_ancho(4, 3)\nassert resultado == (4, 3)\n",
    )


def test_reviewer_conserva_is_none_como_oraculo_exacto() -> None:
    contrato = _contrato(
        {
            "id": "limpia",
            "entrada": {},
            "valor_esperado": None,
            "origen": "tipo",
        },
        firma="() -> None",
    )

    assert (
        ReviewerAgent._validar_oraculo(
            contrato,
            "resultado = alto_y_ancho()\nassert resultado is None\n",
        )
        is None
    )


def test_intento_invalido_no_se_vuelve_referencia_de_laundering(tmp_path: Path) -> None:
    contrato = _contrato(_caso([4, 3]))
    ejecutor = EjecutorAprobado()
    reviewer = ReviewerAgent(
        TokenTracker(), tmp_path, "imagen-prueba", ejecutor=ejecutor
    )
    codigo_lista = "resultado = alto_y_ancho(4, 3)\nassert resultado == [4, 3]\n"
    codigo_tupla = "resultado = alto_y_ancho(4, 3)\nassert resultado == (4, 3)\n"
    primero = {
        "version": "1",
        "objetivo": "alto_y_ancho",
        "intento": 1,
        "codigo": codigo_lista,
        "casos_cubiertos": ["dimensiones"],
    }
    segundo = {**primero, "intento": 2, "codigo": codigo_tupla}

    revision_1 = reviewer.revisar(contrato, primero, None)
    revision_2 = reviewer.revisar(contrato, segundo, primero)

    assert revision_1["decision"] == "retry"
    assert revision_1["laundering_detectado"] is False
    assert revision_2["decision"] == "accept"
    assert revision_2["laundering_detectado"] is False
    assert ejecutor.llamadas == 1


def test_flujo_estatico_completo_aprueba_tupla_en_primer_intento(
    tmp_path: Path,
) -> None:
    """AST → Planner → contrato → Generator → Reviewer, todo local y sin ejecutar usuario."""
    (tmp_path / "dimensiones.py").write_text(
        "def alto_y_ancho(alto: int, ancho: int) -> tuple[int, int]:\n"
        '    """Ejemplo: alto_y_ancho(4, 3) -> (4, 3)"""\n'
        "    return (alto, ancho)\n",
        encoding="utf-8",
    )
    [modulo] = analizar_proyecto(tmp_path)["modulos"]
    propuesta = [{"objetivo": "alto_y_ancho", "casos": [_caso([4, 3], tipo=None)]}]
    [contrato] = PlannerAgent(
        ClienteGrabado(json.dumps(propuesta)), TokenTracker(), es_simulado=True
    ).planificar(modulo)
    codigo = generar_test_desde_contrato(contrato)
    generado = {
        "version": "1",
        "objetivo": "alto_y_ancho",
        "intento": 1,
        "codigo": codigo,
        "casos_cubiertos": ["dimensiones"],
    }
    ejecutor = EjecutorAprobado()
    revision = ReviewerAgent(
        TokenTracker(), tmp_path, "imagen-prueba", ejecutor=ejecutor
    ).revisar(contrato, generado, None)

    assert contrato["casos"][0]["tipo_valor_esperado"] == "tuple"
    assert "== (4, 3)" in codigo
    assert revision["decision"] == "accept"
    assert revision["laundering_detectado"] is False
    assert revision["intento"] == 1
    assert ejecutor.llamadas == 1


@pytest.mark.parametrize(
    "debil",
    [
        "resultado = alto_y_ancho(4, 3)\nassert len(resultado) == 2\n",
        "resultado = alto_y_ancho(4, 3)\nassert resultado[0] == 4\n",
        "resultado = alto_y_ancho(4, 3)\nassert resultado is not None\n",
    ],
)
def test_laundering_sigue_rechazando_aserciones_debilitadas(debil: str) -> None:
    fuerte = "resultado = alto_y_ancho(4, 3)\nassert resultado == (4, 3)\n"

    assert comparar_aserciones(fuerte, debil).es_laundering


def test_laundering_acepta_tupla_exacta_sin_cambios() -> None:
    codigo = "resultado = alto_y_ancho(4, 3)\nassert resultado == (4, 3)\n"

    assert not comparar_aserciones(codigo, codigo).es_laundering


def test_laundering_detecta_cambio_de_tupla_a_lista() -> None:
    tupla = "resultado = alto_y_ancho(4, 3)\nassert resultado == (4, 3)\n"
    lista = "resultado = alto_y_ancho(4, 3)\nassert resultado == [4, 3]\n"

    assert comparar_aserciones(tupla, lista).es_laundering
