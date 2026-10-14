"""Pruebas del Planner de endpoints FastAPI (HU-27). Sin red y sin API real."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qagent import contracts
from qagent.agents.planner import (
    ErrorRespuestaPlanner,
    PlannerAgent,
    estados_permitidos,
    ruta_coincide,
)
from qagent.analysis import analizar_proyecto
from qagent.llm import FakeLLMClient, RespuestaLLM, TokenTracker

RAIZ_REPO = Path(__file__).resolve().parents[2]
BANCO_API = RAIZ_REPO / "bench_api"


class ClienteGrabado:
    """Cliente que devuelve una respuesta fija y guarda el prompt."""

    def __init__(self, respuesta: object) -> None:
        self.contenido = (
            respuesta if isinstance(respuesta, str) else json.dumps(respuesta)
        )
        self.prompts: list[str] = []

    def generar(self, prompt: str, rol: str = "generator") -> RespuestaLLM:
        self.prompts.append(prompt)
        return RespuestaLLM(self.contenido, 300, 120, 0.0, "modelo-x")


@pytest.fixture(scope="module")
def modulo_api() -> dict:
    return analizar_proyecto(BANCO_API)["modulos"][0]


@pytest.fixture(scope="module")
def fuente_api() -> str:
    return (BANCO_API / "api_mvp.py").read_text(encoding="utf-8")


def planner(respuesta: object) -> tuple[PlannerAgent, ClienteGrabado, TokenTracker]:
    cliente = ClienteGrabado(respuesta)
    tracker = TokenTracker()
    return PlannerAgent(cliente, tracker), cliente, tracker


def caso(id_, metodo, ruta, estado, origen="status_code", **extra):
    entrada = {"metodo": metodo, "ruta": ruta}
    entrada.update(extra.pop("entrada", {}))
    return {
        "id": id_,
        "entrada": entrada,
        "valor_esperado": {"status_code": estado, **extra},
        "origen": origen,
    }


# --- Criterio 6: con la IA simulada, un contrato válido por endpoint del banco ---
def test_ia_simulada_planifica_los_6_endpoints_del_banco(modulo_api, fuente_api):
    agente = PlannerAgent(FakeLLMClient(), TokenTracker(), es_simulado=True)

    plan = agente.planificar_endpoints(modulo_api, fuente_api)

    assert [c["objetivo"] for c in plan] == [
        "GET /salud",
        "POST /items",
        "GET /items",
        "GET /items/{item_id}",
        "DELETE /items/{item_id}",
        "GET /descuento",
    ]
    for contrato in plan:
        contracts.validar(contracts.PLANNER, contrato)
        assert contrato["tipo"] == "endpoint"
        assert contrato["aplicacion"] == "app"
    assert agente.descartados == []
    por_objetivo = {c["objetivo"]: c for c in plan}
    assert por_objetivo["POST /items"]["manejador"] == "crear_item"
    assert por_objetivo["POST /items"]["dependencias"] == [
        {"funcion": "obtener_repositorio", "reemplazo": "Repositorio"}
    ]
    assert por_objetivo["GET /descuento"]["llama_a"] == [
        "api_mvp.py::calcular_descuento"
    ]
    estados = {
        c["id"]: c["valor_esperado"]["status_code"]
        for c in por_objetivo["GET /items/{item_id}"]["casos"]
    }
    assert estados["obtener_inexistente"] == 404  # el bug 1 de bugs.md


def test_ia_simulada_cubre_los_minimos_salvo_lo_que_no_declara(modulo_api, fuente_api):
    agente = PlannerAgent(FakeLLMClient(), TokenTracker(), es_simulado=True)
    agente.planificar_endpoints(modulo_api, fuente_api)
    # GET /items no recibe datos ni lanza errores: con su 200 basta.
    assert agente.avisos == []


# --- Criterio 1: el prompt lleva lo declarado y solo el código de cada ruta ------
def test_prompt_con_lo_declarado_los_modelos_y_el_codigo_de_cada_ruta(
    modulo_api, fuente_api
):
    agente, cliente, _ = planner([])
    agente.planificar_endpoints(modulo_api, fuente_api)
    [prompt] = cliente.prompts

    assert '"objetivo": "DELETE /items/{item_id}"' in prompt
    assert '"status_code": 204' in prompt
    assert '"nombre": "ItemEntrada"' in prompt and '"gt": 0' in prompt
    assert "def borrar_item(" in prompt  # código de la ruta
    assert "class Repositorio" not in prompt  # el resto del archivo no va
    assert "app.include_router" not in prompt


def test_una_sola_llamada_por_modulo_con_sus_tokens_registrados(modulo_api, fuente_api):
    agente, cliente, tracker = planner([])
    agente.planificar_endpoints(modulo_api, fuente_api)

    assert len(cliente.prompts) == 1
    [llamada] = tracker.llamadas
    assert llamada.agente == "planner"
    assert (llamada.tokens_entrada, llamada.tokens_salida) == (300, 120)
    assert llamada.funcion == "api_mvp.py (endpoints)"


def test_sin_endpoints_no_llama_a_la_ia():
    agente, cliente, _ = planner([])
    assert (
        agente.planificar_endpoints(
            {"ruta": "x.py", "huella": "a" * 64, "endpoints": []}
        )
        == []
    )
    assert cliente.prompts == []


# --- Criterios 2 y 3: casos mínimos y origen del valor esperado -------------------
def test_avisa_los_casos_minimos_que_faltan(modulo_api):
    agente, _, _ = planner(
        [
            {
                "objetivo": "DELETE /items/{item_id}",
                "casos": [caso("borrar", "DELETE", "/items/1", 204)],
            }
        ]
    )
    plan = agente.planificar_endpoints(modulo_api)

    assert len(plan) == 1
    assert agente.avisos == [
        "DELETE /items/{item_id}: falta un caso con datos inválidos (422)",
        "DELETE /items/{item_id}: falta un caso para la HTTPException 404",
    ]


def test_origen_ejecucion_no_existe(modulo_api):
    agente, _, _ = planner(
        [
            {
                "objetivo": "GET /salud",
                "casos": [caso("a", "GET", "/salud", 200, origen="ejecucion")],
            }
        ]
    )
    with pytest.raises(ErrorRespuestaPlanner):
        agente.planificar_endpoints(modulo_api)


# --- Criterio 4: validación sin IA ------------------------------------------------
@pytest.mark.parametrize(
    ("objetivo", "propuesto", "motivo"),
    [
        (
            "POST /items",
            caso("x", "GET", "/items", 201),
            "el método GET no es el del endpoint",
        ),
        (
            "GET /items/{item_id}",
            caso("x", "GET", "/productos/1", 200),
            "la ruta /productos/1 no corresponde",
        ),
        (
            "GET /salud",
            caso("x", "GET", "/salud", 500),
            "el estado 500 no está declarado",
        ),
        (
            "GET /salud",
            caso("x", "GET", "/salud", 422),
            "el estado 422 no está declarado",
        ),
        (
            "POST /items",
            caso("x", "POST", "/items", 201, json_contiene={"color": "rojo"}),
            "los campos color no están en el response_model",
        ),
        (
            "GET /items",
            caso("x", "GET", "/items", 200, json={"id": 1}),
            "el response_model es una lista",
        ),
    ],
    ids=[
        "metodo",
        "ruta",
        "estado_inventado",
        "422_sin_entradas",
        "campo_inventado",
        "lista",
    ],
)
def test_descarta_casos_que_no_salen_de_la_declaracion(
    modulo_api, objetivo, propuesto, motivo
):
    bueno = caso(
        "bueno", *objetivo.split(" ", 1), 201 if objetivo == "POST /items" else 200
    )
    agente, _, _ = planner([{"objetivo": objetivo, "casos": [propuesto, bueno]}])

    [contrato] = agente.planificar_endpoints(modulo_api)

    assert [c["id"] for c in contrato["casos"]] == ["bueno"]
    assert any(motivo in d for d in agente.descartados), agente.descartados


def test_los_errores_documentados_y_los_422_son_validos(modulo_api):
    agente, _, _ = planner(
        [
            {
                "objetivo": "GET /items/{item_id}",
                "casos": [
                    caso("no_existe", "GET", "/items/9", 404, origen="docstring"),
                    caso("id_texto", "GET", "/items/abc", 422, origen="tipo"),
                    caso(
                        "existe",
                        "GET",
                        "/items/1",
                        200,
                        json={"id": 1, "nombre": "a", "precio": 1.0},
                    ),
                ],
            }
        ]
    )
    [contrato] = agente.planificar_endpoints(modulo_api)
    assert len(contrato["casos"]) == 3
    assert agente.descartados == []


def test_endpoint_desconocido_o_repetido_se_descarta(modulo_api):
    salud = {"objetivo": "GET /salud", "casos": [caso("a", "GET", "/salud", 200)]}
    agente, _, _ = planner([{"objetivo": "GET /no-existe", "casos": []}, salud, salud])

    plan = agente.planificar_endpoints(modulo_api)

    assert [c["objetivo"] for c in plan] == ["GET /salud"]
    assert "endpoint desconocido: 'GET /no-existe'" in agente.descartados
    assert "endpoint repetido: GET /salud" in agente.descartados


def test_respuesta_que_no_es_lista_falla(modulo_api):
    agente, _, _ = planner("esto no es JSON")
    with pytest.raises(ErrorRespuestaPlanner):
        agente.planificar_endpoints(modulo_api)


def test_ruta_sin_resolver_no_se_planifica():
    modulo = {
        "ruta": "x.py",
        "huella": "a" * 64,
        "endpoints": [{"objetivo": "GET /z", "resuelta": False, "manejador": "z"}],
    }
    agente, cliente, _ = planner([])
    assert agente.planificar_endpoints(modulo) == []
    assert cliente.prompts == []
    assert "GET /z: ruta sin resolver" in agente.avisos[0]


@pytest.mark.parametrize(
    ("plantilla", "ruta", "coincide"),
    [
        ("/items/{item_id}", "/items/7", True),
        ("/items/{item_id}", "/items/7?x=1", True),
        ("/items/{item_id}", "/items/7/extra", False),
        ("/items/{item_id}", "/items/", False),
        ("/a/{x}/b/{y:path}", "/a/1/b/2", True),
        ("/salud", "/salud", True),
    ],
)
def test_ruta_coincide(plantilla, ruta, coincide):
    assert ruta_coincide(plantilla, ruta) is coincide


def test_estados_permitidos_del_banco(modulo_api):
    por_objetivo = {e["objetivo"]: e for e in modulo_api["endpoints"]}
    assert estados_permitidos(por_objetivo["GET /salud"]) == {200}
    assert estados_permitidos(por_objetivo["DELETE /items/{item_id}"]) == {
        204,
        404,
        422,
    }
    assert estados_permitidos(por_objetivo["GET /items/{item_id}"]) == {200, 404, 422}


def test_planificar_funciones_no_cambia(modulo_api):
    """Las funciones sueltas del mismo módulo se siguen planificando aparte."""
    agente = PlannerAgent(FakeLLMClient(), TokenTracker(), es_simulado=True)
    assert agente.planificar(modulo_api) == []  # sin grabaciones para sus funciones
