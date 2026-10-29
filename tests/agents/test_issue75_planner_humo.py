"""#75: el Planner en Humo pide y acepta un solo caso normal por objetivo."""

from __future__ import annotations

from pathlib import Path

from qagent import contracts
from qagent.agents import PlannerAgent
from qagent.agents.planner import contrato_humo
from qagent.analysis import analizar_proyecto
from qagent.llm import FakeLLMClient, TokenTracker

RAIZ = Path(__file__).resolve().parents[2]
HUELLA = "a" * 64

MODULO = {
    "ruta": "calc.py",
    "huella": HUELLA,
    "funciones": [
        {
            "nombre": "dividir",
            "firma": "(a: float, b: float) -> float",
            "docstring": "Divide a entre b; lanza ZeroDivisionError si b es 0.",
        },
        {
            "nombre": "validar",
            "firma": "(x: int) -> None",
            "docstring": "Lanza ValueError si x es negativo.",
        },
    ],
}

CASOS = {
    # La excepción viene primero: Humo debe saltarla y quedarse con el caso normal.
    "calc.py::dividir": [
        {
            "id": "division_cero",
            "entrada": {"a": 1, "b": 0},
            "excepcion": "ZeroDivisionError",
            "origen": "docstring",
        },
        {
            "id": "division_normal",
            "entrada": {"a": 6, "b": 3},
            "valor_esperado": 2.0,
            "origen": "docstring",
        },
        {
            "id": "division_negativa",
            "entrada": {"a": -6, "b": 3},
            "valor_esperado": -2.0,
            "origen": "docstring",
        },
    ],
    # Solo hay un caso de error: en Humo no hay un caso normal posible.
    "calc.py::validar": [
        {
            "id": "negativo",
            "entrada": {"x": -1},
            "excepcion": "ValueError",
            "origen": "docstring",
        }
    ],
}


def planner(perfil: str | None, casos=CASOS) -> PlannerAgent:
    return PlannerAgent(
        FakeLLMClient(grabaciones=casos),
        TokenTracker(),
        es_simulado=True,
        perfil=perfil,
    )


def test_en_humo_cada_funcion_tiene_un_solo_caso_normal() -> None:
    agente = planner("humo")

    plan = agente.planificar(MODULO)

    [contrato] = plan
    contracts.validar(contracts.PLANNER_V3, contrato)
    assert contrato["objetivo"] == "dividir"
    assert [c["id"] for c in contrato["casos"]] == ["division_normal"]
    assert "excepcion" not in contrato["casos"][0]


def test_los_casos_de_mas_se_dejan_fuera_con_un_aviso() -> None:
    agente = planner("humo")

    agente.planificar(MODULO)

    [aviso] = agente.avisos
    assert "dividir" in aviso
    assert "'division_normal'" in aviso
    assert "division_cero" in aviso and "division_negativa" in aviso


def test_sin_caso_normal_deducible_el_objetivo_queda_omitido() -> None:
    agente = planner("humo")

    agente.planificar(MODULO)

    assert "no hay un caso normal deducible" in agente.omitidas["validar"]
    assert not any("validar" in d for d in agente.descartados)


def test_fuera_de_humo_se_conservan_todos_los_casos() -> None:
    agente = planner("std")

    plan = agente.planificar(MODULO)

    casos = {c["objetivo"]: len(c["casos"]) for c in plan}
    assert casos == {"dividir": 3, "validar": 1}
    assert agente.avisos == []


def test_el_prompt_de_humo_es_mas_corto() -> None:
    corto = PlannerAgent._crear_prompt_humo(MODULO)
    largo = PlannerAgent._crear_prompt(MODULO)

    assert len(corto) < len(largo)
    assert "UN caso normal" in corto
    # Las reglas del oráculo se mantienen.
    assert "SOLO de firma, tipos o docstring" in corto
    assert "omite la función" in corto


def _modulo_api() -> dict:
    [modulo] = analizar_proyecto(RAIZ / "bench_api")["modulos"]
    return modulo


def test_en_humo_cada_endpoint_tiene_un_caso_con_la_respuesta_exitosa() -> None:
    modulo = _modulo_api()
    declarados = {e["objetivo"]: e["status_code"] for e in modulo["endpoints"]}
    agente = planner("humo", casos=None)

    plan = agente.planificar_endpoints(modulo)

    assert {c["objetivo"] for c in plan} == set(declarados)
    for contrato in plan:
        contracts.validar(contracts.PLANNER_V3, contrato)
        [caso] = contrato["casos"]
        assert caso["valor_esperado"]["status_code"] == declarados[contrato["objetivo"]]
    # Humo no pide los casos de error que faltan (422, 404...).
    assert not any("falta un caso" in a for a in agente.avisos)
    assert any(
        "POST /items" in a and "Humo usa un solo caso" in a for a in agente.avisos
    )


def test_el_prompt_de_endpoints_de_humo_es_mas_corto() -> None:
    modulo = _modulo_api()
    endpoints = {e["objetivo"]: e for e in modulo["endpoints"]}
    fuente = (RAIZ / "bench_api" / "api_mvp.py").read_text(encoding="utf-8")

    corto = PlannerAgent._crear_prompt_endpoints_humo(modulo, endpoints)
    largo = PlannerAgent._crear_prompt_endpoints(modulo, endpoints, fuente)

    assert len(corto) < len(largo)
    assert "UNA petición válida por endpoint" in corto


def test_contrato_humo_toma_el_primer_caso_normal_de_una_spec_completa() -> None:
    funcion = {"tipo": "funcion", "casos": CASOS["calc.py::dividir"]}
    endpoint = {
        "tipo": "endpoint",
        "casos": [
            {"id": "invalido", "valor_esperado": {"status_code": 422}},
            {"id": "creado", "valor_esperado": {"status_code": 201}},
        ],
    }

    assert [c["id"] for c in contrato_humo(funcion)["casos"]] == ["division_normal"]
    assert [c["id"] for c in contrato_humo(endpoint)["casos"]] == ["creado"]
    assert (
        contrato_humo({"tipo": "funcion", "casos": CASOS["calc.py::validar"]}) is None
    )
    # No modifica la spec original.
    assert len(funcion["casos"]) == 3
