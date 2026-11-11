"""Planner: contrato inferido para funciones sin docstring (#275, ADR-016)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from qagent import contracts
from qagent.agents.planner import PlannerAgent
from qagent.analysis.inferencia import ContextoInferencia
from qagent.llm import RespuestaLLM, TokenTracker

MODULO = {
    "ruta": "calc.py",
    "huella": "b" * 64,
    "funciones": [
        {"nombre": "producto", "firma": "(a, b)", "docstring": None, "llama_a": []},
        {
            "nombre": "doble",
            "firma": "(x)",
            "docstring": "Devuelve el doble de x.",
            "llama_a": [],
        },
    ],
}

CONTEXTO = ContextoInferencia(
    modulo="calc.py",
    nombre="producto",
    codigo="def producto(a, b):\n    return a * b",
    tests=(("tests/test_calc.py::test_producto", "assert producto(2, 3) == 6"),),
)


def _caso(**cambios: Any) -> dict[str, Any]:
    caso = {
        "id": "producto_basico",
        "entrada": {"a": 2, "b": 3},
        "valor_esperado": 6,
        "origen": "inferido",
        "evidencia": ["test_existente:tests/test_calc.py::test_producto"],
        "categoria": "normal",
    }
    return {**caso, **cambios}


class ClienteSecuencia:
    """Devuelve una respuesta por llamada, en orden (la última se repite)."""

    def __init__(self, *respuestas: Any) -> None:
        self.respuestas = [
            r if isinstance(r, str) else json.dumps(r) for r in respuestas
        ]
        self.prompts: list[str] = []

    def generar(self, prompt: str, rol: str = "generator") -> RespuestaLLM:
        indice = min(len(self.prompts), len(self.respuestas) - 1)
        self.prompts.append(prompt)
        return RespuestaLLM(
            contenido=self.respuestas[indice],
            tokens_entrada=10,
            tokens_salida=5,
            costo_usd=0.0,
            modelo="modelo-prueba",
        )


def _proveedor(modulo: str, nombre: str) -> ContextoInferencia | None:
    return CONTEXTO if nombre == "producto" else None


def _planner(cliente: ClienteSecuencia, **opciones: Any) -> PlannerAgent:
    opciones.setdefault("proveedor_inferencia", _proveedor)
    return PlannerAgent(cliente, TokenTracker(), **opciones)


def test_infiere_una_funcion_sin_docstring_con_evidencia() -> None:
    cliente = ClienteSecuencia([], [{"objetivo": "producto", "casos": [_caso()]}])
    planner = _planner(cliente)

    plan = planner.planificar(MODULO)

    [contrato] = plan
    assert contrato["objetivo"] == "producto"
    assert contracts.es_contrato_inferido(contrato)
    assert contrato["casos"][0]["origen"] == "inferido"
    assert contracts.es_valido(contracts.PLANNER_V3, contrato)
    assert "producto" not in planner.omitidas
    assert any("sin docstring" in aviso for aviso in planner.avisos)


def test_el_prompt_de_inferencia_lleva_el_contexto_y_no_las_funciones_documentadas() -> (
    None
):
    cliente = ClienteSecuencia([], [])
    _planner(cliente).planificar(MODULO)

    assert len(cliente.prompts) == 2
    inferencia = cliente.prompts[1]
    assert "return a * b" in inferencia
    assert "tests/test_calc.py::test_producto" in inferencia
    assert "doble" not in inferencia  # tiene docstring: no entra a la inferencia
    assert "No ejecutes ni importes nada" in inferencia


def test_evidencia_que_no_se_entrego_descarta_el_caso() -> None:
    caso = _caso(evidencia=["test_existente:otro.py::test_inventado"])
    cliente = ClienteSecuencia([], [{"objetivo": "producto", "casos": [caso]}])
    planner = _planner(cliente)

    assert planner.planificar(MODULO) == []
    assert "producto" in planner.omitidas
    assert "inferencia estática tampoco" in planner.omitidas["producto"]
    assert any("no se entregaron" in d for d in planner.descartados)


def test_un_caso_inferido_sin_evidencia_es_invalido() -> None:
    caso = _caso()
    del caso["evidencia"]
    cliente = ClienteSecuencia([], [{"objetivo": "producto", "casos": [caso]}])
    planner = _planner(cliente)

    assert planner.planificar(MODULO) == []
    assert "producto" in planner.omitidas


def test_sin_proveedor_se_omite_como_antes() -> None:
    cliente = ClienteSecuencia([])
    planner = PlannerAgent(cliente, TokenTracker())

    assert planner.planificar(MODULO) == []
    assert len(cliente.prompts) == 1
    assert "producto" in planner.omitidas
    assert "inferencia" not in planner.omitidas["producto"]


def test_sin_contexto_legible_sigue_omitida() -> None:
    cliente = ClienteSecuencia([])
    planner = _planner(cliente, proveedor_inferencia=lambda m, n: None)

    assert planner.planificar(MODULO) == []
    assert (
        len(cliente.prompts) == 1
    )  # no hay nada que inferir: no se gasta otra llamada
    assert "producto" in planner.omitidas


def test_respuesta_de_inferencia_malformada_no_tumba_la_corrida() -> None:
    cliente = ClienteSecuencia([], "esto no es JSON")
    planner = _planner(cliente)

    assert planner.planificar(MODULO) == []
    assert "producto" in planner.omitidas
    assert any("inferencia: respuesta no válida" in a for a in planner.avisos)


def test_el_tope_de_funciones_inferidas_deja_el_resto_omitido() -> None:
    modulo = {
        **MODULO,
        "funciones": [
            {"nombre": "producto", "firma": "(a, b)", "docstring": None},
            {"nombre": "suma", "firma": "(a, b)", "docstring": None},
        ],
    }
    cliente = ClienteSecuencia([], [{"objetivo": "producto", "casos": [_caso()]}])
    planner = _planner(
        cliente,
        max_inferidas=1,
        proveedor_inferencia=lambda m, n: CONTEXTO,
    )

    plan = planner.planificar(modulo)

    assert [c["objetivo"] for c in plan] == ["producto"]
    assert "tope de 1 funciones" in planner.omitidas["suma"]


def test_origen_inferido_no_vale_fuera_de_la_inferencia() -> None:
    """Si el modelo lo declara en la primera pasada, no hay contexto que lo respalde."""
    primera = [{"objetivo": "doble", "casos": [_caso(id="doble_caso")]}]
    cliente = ClienteSecuencia(primera, [])
    planner = _planner(cliente)

    planner.planificar(MODULO)

    assert "doble" in planner.omitidas  # tiene docstring y el origen no es válido
    assert any("solo vale en la fase de inferencia" in d for d in planner.descartados)


def _contrato(caso: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "3",
        "lenguaje": "python",
        "framework_pruebas": "pytest",
        "modulo": "calc.py",
        "huella": "b" * 64,
        "tipo": "funcion",
        "objetivo": "producto",
        "firma": "(a, b)",
        "critical": False,
        "llama_a": [],
        "casos": [caso],
    }


def test_el_schema_exige_evidencia_solo_con_origen_inferido() -> None:
    assert contracts.es_valido(contracts.PLANNER_V3, _contrato(_caso()))

    sin_evidencia = _caso()
    del sin_evidencia["evidencia"]
    assert not contracts.es_valido(contracts.PLANNER_V3, _contrato(sin_evidencia))

    vacia = _caso(evidencia=[])
    assert not contracts.es_valido(contracts.PLANNER_V3, _contrato(vacia))

    con_otro_origen = _caso(origen="docstring")
    assert not contracts.es_valido(contracts.PLANNER_V3, _contrato(con_otro_origen))


def test_contratos_anteriores_siguen_siendo_validos() -> None:
    caso = {
        "id": "caso_1",
        "entrada": {"a": 1, "b": 2},
        "valor_esperado": 2,
        "origen": "docstring",
    }

    contrato = _contrato(caso)

    assert contracts.es_valido(contracts.PLANNER_V3, contrato)
    assert not contracts.es_contrato_inferido(contrato)


@pytest.mark.parametrize("categoria", ["normal", "limite"])
def test_un_limite_inferido_con_evidencia_se_acepta(categoria: str) -> None:
    caso = _caso(categoria=categoria)
    cliente = ClienteSecuencia([], [{"objetivo": "producto", "casos": [caso]}])

    plan = _planner(cliente).planificar(MODULO)

    assert plan[0]["casos"][0]["categoria"] == categoria
