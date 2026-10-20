"""Pruebas de PlannerAgent sin usar una API real."""

from __future__ import annotations

import json

import pytest

from qagent import contracts
from qagent.agents.planner import ErrorRespuestaPlanner, PlannerAgent
from qagent.llm import RespuestaLLM, TokenTracker

MODULO = {
    "ruta": "calculadora.py",
    "huella": "a" * 64,
    "funciones": [
        {
            "nombre": "duplicar",
            "firma": "(x: int) -> int",
            "docstring": "Devuelve x multiplicado por dos.",
            "llama_a": [],
        }
    ],
}

PLAN = [
    {
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
]


class ClienteGrabado:
    """Cliente que devuelve una respuesta controlada."""

    def __init__(self, contenido: str) -> None:
        self.contenido = contenido
        self.llamadas: list[tuple[str, str]] = []

    def generar(self, prompt: str, rol: str = "generator") -> RespuestaLLM:
        self.llamadas.append((prompt, rol))
        return RespuestaLLM(
            contenido=self.contenido,
            tokens_entrada=100,
            tokens_salida=40,
            costo_usd=0.01,
            modelo="modelo-prueba",
        )


def test_planner_devuelve_contratos_validos() -> None:
    cliente = ClienteGrabado(json.dumps(PLAN))
    planner = PlannerAgent(cliente, TokenTracker())

    resultado = planner.planificar(MODULO)

    assert resultado == PLAN
    assert contracts.es_valido(contracts.PLANNER, resultado[0])


def test_planner_envia_estructura_y_registra_tokens() -> None:
    cliente = ClienteGrabado(json.dumps(PLAN))
    tracker = TokenTracker()
    planner = PlannerAgent(cliente, tracker)

    planner.planificar(MODULO)

    prompt, rol = cliente.llamadas[0]
    assert rol == "planner"
    assert "calculadora.py" in prompt
    assert "duplicar" in prompt
    assert "No ejecutes" in prompt

    [llamada] = tracker.llamadas
    assert llamada.agente == "planner"
    assert llamada.tokens_entrada == 100
    assert llamada.tokens_salida == 40


def test_planner_acepta_json_dentro_de_cerca_markdown() -> None:
    cliente = ClienteGrabado(f"```json\n{json.dumps(PLAN)}\n```")
    planner = PlannerAgent(cliente, TokenTracker())

    assert planner.planificar(MODULO) == PLAN


def test_planner_rechaza_json_invalido() -> None:
    cliente = ClienteGrabado("esto no es JSON")
    planner = PlannerAgent(cliente, TokenTracker())

    with pytest.raises(ErrorRespuestaPlanner, match="JSON válido"):
        planner.planificar(MODULO)


def test_planner_rechaza_un_objeto_en_lugar_de_lista() -> None:
    cliente = ClienteGrabado(json.dumps(PLAN[0]))
    planner = PlannerAgent(cliente, TokenTracker())

    with pytest.raises(ErrorRespuestaPlanner, match="lista"):
        planner.planificar(MODULO)


def test_los_campos_del_contrato_salen_del_analisis_y_no_del_modelo() -> None:
    """El modelo solo aporta los casos; huella, firma y módulo vienen del AST."""
    inventado = [
        {
            **PLAN[0],
            "modulo": "otro.py",
            "huella": "f" * 64,
            "firma": "(y)",
            "critical": True,
        }
    ]
    planner = PlannerAgent(ClienteGrabado(json.dumps(inventado)), TokenTracker())

    [contrato] = planner.planificar(MODULO)

    assert contrato["modulo"] == "calculadora.py"
    assert contrato["huella"] == "a" * 64
    assert contrato["firma"] == "(x: int) -> int"
    assert contrato["critical"] is False


def test_la_marca_critica_sale_de_la_seleccion_y_no_del_modelo() -> None:
    """HU-06: la marca Profundizar de la vista previa llega al contrato."""
    marcada = {**MODULO, "funciones": [{**MODULO["funciones"][0], "critical": True}]}
    planner = PlannerAgent(ClienteGrabado(json.dumps(PLAN)), TokenTracker())

    [contrato] = planner.planificar(marcada)

    assert contrato["critical"] is True
    assert contracts.es_valido(contracts.PLANNER, contrato)


def test_planner_acepta_la_respuesta_compacta() -> None:
    compacta = [{"objetivo": "duplicar", "casos": PLAN[0]["casos"]}]
    planner = PlannerAgent(ClienteGrabado(json.dumps(compacta)), TokenTracker())

    assert planner.planificar(MODULO) == PLAN


def test_planner_descarta_objetivos_y_casos_invalidos() -> None:
    respuesta = [
        {
            "objetivo": "duplicar",
            "casos": [
                PLAN[0]["casos"][0],
                {"id": "sin_esperado", "entrada": {"x": 1}, "origen": "docstring"},
                {
                    "id": "origen_prohibido",
                    "entrada": {"x": 1},
                    "valor_esperado": 2,
                    "origen": "ejecucion",
                },
            ],
        },
        {"objetivo": "funcion_inventada", "casos": PLAN[0]["casos"]},
    ]
    planner = PlannerAgent(ClienteGrabado(json.dumps(respuesta)), TokenTracker())

    [contrato] = planner.planificar(MODULO)

    assert [caso["id"] for caso in contrato["casos"]] == ["duplica_positivo"]
    assert len(planner.descartados) == 3
    assert any("funcion_inventada" in motivo for motivo in planner.descartados)


def test_planner_falla_si_ningun_contrato_es_valido() -> None:
    respuesta = [{"objetivo": "duplicar", "casos": [{"id": "x"}]}]
    planner = PlannerAgent(ClienteGrabado(json.dumps(respuesta)), TokenTracker())

    with pytest.raises(ErrorRespuestaPlanner, match="ningún contrato"):
        planner.planificar(MODULO)


def test_modulo_sin_funciones_no_llama_al_modelo() -> None:
    cliente = ClienteGrabado("[]")
    planner = PlannerAgent(cliente, TokenTracker())

    assert planner.planificar({**MODULO, "funciones": []}) == []
    assert cliente.llamadas == []


def test_prompt_explica_el_formato_del_caso_sin_enviar_datos_de_mas() -> None:
    cliente = ClienteGrabado(json.dumps(PLAN))
    modulo = {
        **MODULO,
        "funciones": [{**MODULO["funciones"][0], "linea": 99, "ramas": 7}],
    }

    PlannerAgent(cliente, TokenTracker()).planificar(modulo)

    prompt = cliente.llamadas[0][0]
    for campo in ('"valor_esperado"', '"excepcion"', '"origen"', "docstring"):
        assert campo in prompt
    assert "ejecucion" not in prompt
    assert '"linea"' not in prompt
    assert '"huella"' not in prompt


# --- Funciones sin valor esperado deducible: se omiten, no detienen la corrida ---

MODULO_SIN_ORACULO = {
    "ruta": "jwt_auth.py",
    "huella": "b" * 64,
    "funciones": [
        {
            "nombre": "create_access_token",
            "firma": "(identity, roles=None, email=None)",
            "docstring": "Genera un access token de corta duración.",
        },
        {
            "nombre": "create_refresh_token",
            "firma": "(identity)",
            "docstring": "Genera un refresh token de larga duración.",
        },
    ],
}


@pytest.mark.parametrize("perfil", [None, "humo"])
def test_sin_casos_las_funciones_quedan_omitidas_sin_error(perfil) -> None:
    respuesta = [
        {"objetivo": "create_access_token", "casos": []},
        {"objetivo": "create_refresh_token"},
    ]
    planner = PlannerAgent(
        ClienteGrabado(json.dumps(respuesta)), TokenTracker(), perfil=perfil
    )

    assert planner.planificar(MODULO_SIN_ORACULO) == []
    assert set(planner.omitidas) == {"create_access_token", "create_refresh_token"}
    assert all(
        "deduc" in motivo and "docstring" in motivo
        for motivo in planner.omitidas.values()
    )
    assert planner.descartados == []


def test_la_funcion_que_el_modelo_no_menciona_queda_omitida() -> None:
    planner = PlannerAgent(ClienteGrabado("[]"), TokenTracker())

    assert planner.planificar(MODULO_SIN_ORACULO) == []
    assert set(planner.omitidas) == {"create_access_token", "create_refresh_token"}


def test_se_omite_una_y_se_planifican_las_demas() -> None:
    modulo = {
        **MODULO,
        "funciones": [*MODULO["funciones"], MODULO_SIN_ORACULO["funciones"][0]],
    }
    respuesta = [{"objetivo": "duplicar", "casos": PLAN[0]["casos"]}]
    planner = PlannerAgent(ClienteGrabado(json.dumps(respuesta)), TokenTracker())

    [contrato] = planner.planificar(modulo)

    assert contrato["objetivo"] == "duplicar"
    assert list(planner.omitidas) == ["create_access_token"]


def test_solo_casos_limite_sin_especificacion_tambien_es_omitir() -> None:
    respuesta = [
        {
            "objetivo": "duplicar",
            "casos": [
                {
                    "id": "maximo_entero",
                    "entrada": {"x": 2**31},
                    "valor_esperado": 2**32,
                    "origen": "tipo",
                    "categoria": "limite",
                }
            ],
        }
    ]
    planner = PlannerAgent(ClienteGrabado(json.dumps(respuesta)), TokenTracker())

    assert planner.planificar(MODULO) == []
    assert "duplicar" in planner.omitidas


def test_casos_con_formato_invalido_siguen_siendo_un_error_del_modelo() -> None:
    """Omitir no tapa los errores del modelo: un caso mal formado no es «sin oráculo»."""
    respuesta = [{"objetivo": "duplicar", "casos": [{"id": "x"}]}]
    planner = PlannerAgent(ClienteGrabado(json.dumps(respuesta)), TokenTracker())

    with pytest.raises(ErrorRespuestaPlanner, match="ningún contrato"):
        planner.planificar(MODULO)
    assert planner.omitidas == {}
