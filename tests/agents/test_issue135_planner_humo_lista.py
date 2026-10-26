"""#135: en Humo, un objeto suelto en vez de una lista no detiene el módulo.

Evidencia: con APP-RF (`image_to_bytes`), DeepSeek devolvió 1 de cada 6 veces
`{"objetivo": "image_to_bytes", "casos": []}`, y el Planner detenía el módulo.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qagent import contracts
from qagent.agents.planner import ErrorRespuestaPlanner, PlannerAgent
from qagent.analysis import analizar_proyecto
from qagent.llm import RespuestaLLM, TokenTracker

RAIZ = Path(__file__).resolve().parents[2]

MODULO = {
    "ruta": "imagenes.py",
    "huella": "a" * 64,
    "funciones": [
        {
            "nombre": "image_to_bytes",
            "firma": "(image_path)",
            "docstring": "Convierte una imagen a bytes.",
        },
        {
            "nombre": "duplicar",
            "firma": "(x: int) -> int",
            "docstring": "Devuelve x multiplicado por dos.",
        },
    ],
}

CASO_NORMAL = {
    "id": "duplica_positivo",
    "entrada": {"x": 2},
    "valor_esperado": 4,
    "origen": "docstring",
    "categoria": "normal",
}


class ClienteGrabado:
    """Cliente que devuelve un texto fijo, como lo mandaría el modelo."""

    def __init__(self, respuesta: object) -> None:
        self.contenido = (
            respuesta if isinstance(respuesta, str) else json.dumps(respuesta)
        )
        self.prompts: list[str] = []

    def generar(self, prompt: str, rol: str = "generator") -> RespuestaLLM:
        self.prompts.append(prompt)
        return RespuestaLLM(self.contenido, 300, 120, 0.0, "modelo-x")


def humo(respuesta: object) -> PlannerAgent:
    return PlannerAgent(ClienteGrabado(respuesta), TokenTracker(), perfil="humo")


def _modulo_api() -> dict:
    [modulo] = analizar_proyecto(RAIZ / "bench_api")["modulos"]
    return modulo


# --- Funciones --------------------------------------------------------------------


def test_objeto_suelto_sin_casos_deja_la_funcion_omitida() -> None:
    agente = humo({"objetivo": "image_to_bytes", "casos": []})

    plan = agente.planificar(MODULO)

    assert plan == []
    assert "image_to_bytes" in agente.omitidas
    assert "no hay un caso normal deducible" in agente.omitidas["image_to_bytes"]


def test_objeto_suelto_y_lista_de_uno_dan_el_mismo_contrato() -> None:
    elemento = {"objetivo": "duplicar", "casos": [CASO_NORMAL]}

    suelto = humo(elemento).planificar(MODULO)
    en_lista = humo([elemento]).planificar(MODULO)

    assert suelto == en_lista
    [contrato] = suelto
    contracts.validar(contracts.PLANNER, contrato)
    assert contrato["objetivo"] == "duplicar"
    assert [c["id"] for c in contrato["casos"]] == ["duplica_positivo"]


def test_objeto_suelto_con_casos_invalidos_sigue_siendo_error_del_modelo() -> None:
    """La tolerancia es solo de forma: los casos se validan igual que siempre."""
    agente = humo({"objetivo": "duplicar", "casos": [{"id": "incompleto"}]})
    # Solo la función del caso: otra sin mencionar quedaría omitida y, con razón,
    # evitaría el error (no todo el módulo falló por culpa del modelo).
    solo_duplicar = {
        **MODULO,
        "funciones": [f for f in MODULO["funciones"] if f["nombre"] == "duplicar"],
    }

    with pytest.raises(ErrorRespuestaPlanner, match="ningún contrato"):
        agente.planificar(solo_duplicar)


@pytest.mark.parametrize(
    ("respuesta", "recibido"),
    [
        ('"no hay casos"', "un texto"),
        ("42", "un número"),
        ("true", "un valor booleano"),
        ("null", "null"),
        ('{"otra": 1}', 'un objeto sin "objetivo"'),
    ],
)
def test_otras_formas_siguen_fallando_y_dicen_que_se_recibio(
    respuesta: str, recibido: str
) -> None:
    with pytest.raises(ErrorRespuestaPlanner) as error:
        humo(respuesta).planificar(MODULO)

    mensaje = str(error.value)
    assert (
        mensaje
        == f"El Planner debe devolver una lista de objetivos; se recibió {recibido}."
    )


def test_el_mensaje_de_error_no_copia_la_respuesta() -> None:
    with pytest.raises(ErrorRespuestaPlanner) as error:
        humo('{"otra": "texto-que-no-debe-aparecer"}').planificar(MODULO)

    assert "texto-que-no-debe-aparecer" not in str(error.value)


def test_el_prompt_de_humo_pide_una_lista_y_acepta_la_vacia() -> None:
    prompt = PlannerAgent._crear_prompt_humo(MODULO)

    assert "Devuelve SOLO una lista JSON con un objeto por función:" in prompt
    assert '[{"objetivo": nombre, "casos": [caso]}]' in prompt
    assert "devuelve la lista vacía []" in prompt
    # Regresión: ya no muestra un objeto suelto como formato de la lista.
    assert 'una lista JSON: {"objetivo"' not in prompt


# --- Endpoints --------------------------------------------------------------------


def test_endpoint_como_objeto_suelto_se_planifica_igual() -> None:
    modulo = _modulo_api()
    elemento = {
        "objetivo": "GET /salud",
        "casos": [
            {
                "id": "salud_ok",
                "entrada": {"metodo": "GET", "ruta": "/salud"},
                "valor_esperado": {"status_code": 200},
                "origen": "status_code",
                "categoria": "normal",
            }
        ],
    }

    suelto = humo(elemento).planificar_endpoints(modulo)
    en_lista = humo([elemento]).planificar_endpoints(modulo)

    assert suelto == en_lista
    assert [c["objetivo"] for c in suelto] == ["GET /salud"]
    contracts.validar(contracts.PLANNER, suelto[0])


def test_endpoints_con_otra_forma_siguen_fallando() -> None:
    with pytest.raises(ErrorRespuestaPlanner, match="se recibió un texto"):
        humo('"nada"').planificar_endpoints(_modulo_api())


def test_el_prompt_de_endpoints_de_humo_pide_una_lista_y_acepta_la_vacia() -> None:
    modulo = _modulo_api()
    endpoints = {e["objetivo"]: e for e in modulo["endpoints"]}

    prompt = PlannerAgent._crear_prompt_endpoints_humo(modulo, endpoints)

    assert "Devuelve SOLO una lista JSON con un objeto por endpoint:" in prompt
    assert '[{"objetivo": "MÉTODO /ruta", "casos": [caso]}]' in prompt
    assert "devuelve la lista vacía []" in prompt
    assert 'una lista JSON: {"objetivo"' not in prompt
