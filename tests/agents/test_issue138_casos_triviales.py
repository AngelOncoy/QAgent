"""#138: una llamada con argumentos que no encajan con la firma no prueba la función.

Evidencia (APP-RF): `euclidean_distance()` → TypeError e `image_to_bytes()` → TypeError
fueron los únicos casos de sus funciones; «pasaron» con cobertura 0 % porque Python
rechaza la llamada antes de entrar al cuerpo.
"""

from __future__ import annotations

import json

import pytest

from qagent import contracts
from qagent.agents.planner import (
    MOTIVO_CASO_TRIVIAL,
    MOTIVO_OMITIDA_TRIVIAL,
    PlannerAgent,
    contrato_sin_triviales,
    es_caso_trivial,
)
from qagent.llm import RespuestaLLM, TokenTracker

MODULO = {
    "ruta": "app/utils/face_utils.py",
    "huella": "1" * 64,
    "funciones": [
        {"nombre": "euclidean_distance", "firma": "(vec_a, vec_b)", "docstring": None},
        {
            "nombre": "image_to_bytes",
            "firma": "(image_path)",
            "docstring": "Convierte una imagen a bytes.",
        },
        {
            "nombre": "duplicar",
            "firma": "(x: int) -> int",
            "docstring": "Devuelve x multiplicado por dos; lanza TypeError si x no es int.",
        },
    ],
}


def caso(id_: str, entrada: dict, *, origen: str = "firma", **extra) -> dict:
    datos = {"id": id_, "entrada": entrada, "origen": origen}
    if "excepcion" in extra:
        datos.update(excepcion=extra["excepcion"], categoria="error")
    else:
        datos.update(valor_esperado=extra["valor"], categoria="normal")
    return datos


SIN_ARGUMENTOS = caso("sin_argumentos", {}, excepcion="TypeError")
DUPLICA = caso("duplica", {"x": 2}, origen="docstring", valor=4)
TIPO_INVALIDO = caso("texto", {"x": "a"}, origen="docstring", excepcion="TypeError")


class ClienteGrabado:
    def __init__(self, propuesta: object) -> None:
        self.contenido = json.dumps(propuesta)
        self.prompts: list[str] = []

    def generar(self, prompt: str, rol: str = "generator") -> RespuestaLLM:
        self.prompts.append(prompt)
        return RespuestaLLM(self.contenido, 1, 1, 0.0, "modelo-prueba")


def planner(propuesta: object, perfil: str | None = None) -> PlannerAgent:
    return PlannerAgent(
        ClienteGrabado(propuesta), TokenTracker(), es_simulado=True, perfil=perfil
    )


# --- Detección sin IA -------------------------------------------------------------


@pytest.mark.parametrize(
    ("firma", "entrada"),
    [
        ("(vec_a, vec_b)", {}),  # sin argumentos
        ("(vec_a, vec_b)", {"vec_a": [1]}),  # falta uno de varios
        ("(x)", {"x": 1, "y": 2}),  # sobra una clave
        ("(x, /)", {"x": 1}),  # posicional-only pasado por nombre
        ("(*, clave)", {}),  # keyword-only obligatorio que falta
    ],
)
def test_la_llamada_que_no_encaja_con_la_firma_es_trivial(firma, entrada) -> None:
    funcion = {"firma": firma}

    assert es_caso_trivial(funcion, caso("c", entrada, excepcion="TypeError"))
    # Con cualquier origen: el error lo lanza Python, no la función.
    assert es_caso_trivial(
        funcion, caso("c", entrada, origen="docstring", excepcion="TypeError")
    )


@pytest.mark.parametrize(
    ("firma", "datos"),
    [
        ("(x: int) -> int", TIPO_INVALIDO),  # TypeError con argumentos que sí encajan
        ("(x)", caso("c", {}, excepcion="ValueError")),  # otra excepción
        ("(x=1)", caso("c", {}, excepcion="TypeError")),  # todos opcionales
        ("(**kwargs)", caso("c", {"y": 1}, excepcion="TypeError")),  # acepta claves
        ("(x)", DUPLICA),  # caso normal
    ],
)
def test_no_es_trivial(firma, datos) -> None:
    assert not es_caso_trivial({"firma": firma}, datos)


# --- Planner ----------------------------------------------------------------------


def test_un_objetivo_con_solo_el_caso_trivial_queda_omitido() -> None:
    agente = planner(
        [
            {"objetivo": "euclidean_distance", "casos": [SIN_ARGUMENTOS]},
            {"objetivo": "image_to_bytes", "casos": [SIN_ARGUMENTOS]},
        ]
    )

    plan = agente.planificar(MODULO)

    assert plan == []
    sin_doc = agente.omitidas["euclidean_distance"]
    assert sin_doc == f"la función no tiene docstring y {MOTIVO_OMITIDA_TRIVIAL}"
    assert agente.omitidas["image_to_bytes"] == MOTIVO_OMITIDA_TRIVIAL
    assert any(MOTIVO_CASO_TRIVIAL in d for d in agente.descartados)


def test_el_caso_trivial_se_descarta_y_se_conservan_los_de_comportamiento() -> None:
    agente = planner(
        [{"objetivo": "duplicar", "casos": [DUPLICA, TIPO_INVALIDO, SIN_ARGUMENTOS]}]
    )

    [contrato] = agente.planificar(MODULO)

    contracts.validar(contracts.PLANNER, contrato)
    assert [c["id"] for c in contrato["casos"]] == ["duplica", "texto"]
    assert "duplicar" not in agente.omitidas
    assert any(
        "sin_argumentos" in d and MOTIVO_CASO_TRIVIAL in d for d in agente.descartados
    )


def test_funciones_identicas_sin_docstring_reciben_el_mismo_trato() -> None:
    """Cualquier propuesta del modelo para ellas termina igual: omitidas."""
    modulo = {
        **MODULO,
        "funciones": [
            {"nombre": "a", "firma": "(vec_a, vec_b)", "docstring": None},
            {"nombre": "b", "firma": "(vec_a, vec_b)", "docstring": None},
        ],
    }
    agente = planner(
        [
            {"objetivo": "a", "casos": [SIN_ARGUMENTOS]},
            {
                "objetivo": "b",
                "casos": [caso("v", {"vec_a": [0], "vec_b": [0]}, valor=0)],
            },
        ]
    )

    assert agente.planificar(modulo) == []
    assert set(agente.omitidas) == {"a", "b"}


def test_los_prompts_ya_no_piden_el_typeerror_de_firma() -> None:
    estandar = PlannerAgent._crear_prompt(MODULO)
    humo = PlannerAgent._crear_prompt_humo(MODULO)

    for prompt in (estandar, humo):
        assert (
            "No propongas llamadas con argumentos que no encajan con la firma" in prompt
        )
        assert "puede justificar TypeError" not in prompt
        assert "solo propón TypeError" not in prompt


# --- Specs guardadas antes de #138 ------------------------------------------------


def _contrato(casos: list[dict]) -> dict:
    return {
        "version": "2",
        "modulo": "app/utils/face_utils.py",
        "huella": "1" * 64,
        "tipo": "funcion",
        "objetivo": "duplicar",
        "firma": "(x: int) -> int",
        "critical": False,
        "llama_a": [],
        "casos": casos,
    }


def test_una_spec_guardada_pierde_sus_casos_triviales() -> None:
    contrato = _contrato([DUPLICA, SIN_ARGUMENTOS])

    limpio = contrato_sin_triviales(contrato)

    assert [c["id"] for c in limpio["casos"]] == ["duplica"]
    assert [c["id"] for c in contrato["casos"]] == ["duplica", "sin_argumentos"]


def test_una_spec_con_solo_el_caso_trivial_se_vuelve_a_planificar() -> None:
    assert contrato_sin_triviales(_contrato([SIN_ARGUMENTOS])) is None


def test_una_spec_sin_triviales_no_cambia() -> None:
    contrato = _contrato([DUPLICA])

    assert contrato_sin_triviales(contrato) is contrato
