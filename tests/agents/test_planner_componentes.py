"""Planner de componentes React: contratos v3 con oráculo de props y JSDoc (#171).

Todo con la IA simulada (``FakeLLMClient`` con grabaciones) o un cliente grabado:
ninguna prueba llama a una API real ni necesita Docker.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from qagent import contracts
from qagent.agents.planner import MOTIVO_COMPONENTE_SIN_CASOS, PlannerAgent
from qagent.lenguajes import TypeScriptAdapter
from qagent.lenguajes.javascript_componentes import MOTIVO_SIN_ORACULO
from qagent.lenguajes.javascript_componentes_planificacion import (
    motivo_caso_componente,
    prompt_componentes,
)
from qagent.llm import RespuestaLLM, TokenTracker
from qagent.llm.fake import FakeLLMClient

BOTON = """
interface BotonProps {
  /** Texto visible del botón. */
  etiqueta: string;
  deshabilitado?: boolean;
  /** Se llama al pulsar el botón. */
  onPulsar: () => void;
}

/** Botón de pago. Muestra el texto "Pagar ahora" si no recibe etiqueta. */
export function Boton({ etiqueta, deshabilitado = false, onPulsar }: BotonProps) {
  return <button disabled={deshabilitado} onClick={onPulsar}>{etiqueta}</button>;
}

export function Contador(props: { inicial: number }) {
  return <output>{props.inicial}</output>;
}

export function Libre(props) {
  return <div>{props.x}</div>;
}
"""

FN = {"$funcion": True}

CASOS_BOTON = [
    {
        "id": "muestra_etiqueta",
        "descripcion": "La etiqueta documentada se ve en el botón",
        "entrada": {"props": {"etiqueta": "Pagar", "onPulsar": FN}},
        "valor_esperado": {
            "renderiza": True,
            "visible": [{"rol": "button", "nombre": "Pagar"}],
        },
        "origen": "docstring",
        "categoria": "normal",
    },
    {
        "id": "sin_opcionales",
        "entrada": {"props": {"etiqueta": "Pagar", "onPulsar": FN}},
        "valor_esperado": {"renderiza": True},
        "origen": "tipo",
        "categoria": "limite",
    },
    {
        "id": "pulsar_avisa",
        "entrada": {
            "props": {"etiqueta": "Pagar", "onPulsar": FN},
            "interacciones": [
                {"accion": "click", "elemento": {"rol": "button", "nombre": "Pagar"}}
            ],
        },
        "valor_esperado": {
            "renderiza": True,
            "llamadas": [{"prop": "onPulsar", "veces": 1}],
        },
        "origen": "docstring",
        "categoria": "normal",
    },
]


@pytest.fixture
def modulo(tmp_path: Path) -> dict[str, Any]:
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"react": "^19.0.0"}}), encoding="utf-8"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "Boton.tsx").write_text(BOTON, encoding="utf-8")
    [modulo] = TypeScriptAdapter().analizar(tmp_path)["modulos"]
    return modulo


def _componente(modulo: dict[str, Any], nombre: str) -> dict[str, Any]:
    return next(c for c in modulo["componentes"] if c["nombre"] == nombre)


def _planner(grabaciones: dict[str, Any], **opciones: Any) -> PlannerAgent:
    return PlannerAgent(
        FakeLLMClient(grabaciones=grabaciones),
        TokenTracker(),
        es_simulado=True,
        adaptador=TypeScriptAdapter(),
        **opciones,
    )


class ClienteContador:
    """Cuenta las llamadas al modelo."""

    def __init__(self) -> None:
        self.llamadas = 0

    def generar(self, prompt: str, rol: str = "generator") -> RespuestaLLM:
        self.llamadas += 1
        return RespuestaLLM("[]", 0, 0, 0.0, "contador")


# --- Planner -------------------------------------------------------------------------


def test_planifica_componente_con_contrato_v3_react(modulo: dict[str, Any]) -> None:
    planner = _planner({"Boton.tsx::Boton": CASOS_BOTON})
    [contrato] = planner.planificar_componentes(modulo)

    assert contracts.errores(contracts.PLANNER_V3, contrato) == []
    assert contrato["tipo"] == "componente"
    assert contrato["framework_app"] == "react"
    assert contrato["framework_pruebas"] == "vitest"
    assert contrato["lenguaje"] == "typescript"
    assert contrato["critical"] is False
    assert [c["id"] for c in contrato["casos"]] == [
        "muestra_etiqueta",
        "sin_opcionales",
        "pulsar_avisa",
    ]


def test_componente_sin_tipos_ni_jsdoc_queda_omitido_sin_gastar_tokens(
    modulo: dict[str, Any],
) -> None:
    solo_libre = {**modulo, "componentes": [_componente(modulo, "Libre")]}
    cliente = ClienteContador()
    planner = PlannerAgent(cliente, TokenTracker(), adaptador=TypeScriptAdapter())

    assert planner.planificar_componentes(solo_libre) == []
    assert planner.omitidas == {"Libre": MOTIVO_SIN_ORACULO}
    assert cliente.llamadas == 0


def test_sin_casos_respaldados_queda_omitido(modulo: dict[str, Any]) -> None:
    inventado = [
        {
            "id": "inventa",
            "entrada": {"props": {"inicial": 3}},
            "valor_esperado": {"renderiza": True, "visible": [{"texto": "3"}]},
            "origen": "docstring",
            "categoria": "normal",
        }
    ]
    planner = _planner({"Boton.tsx::Contador": inventado})
    plan = planner.planificar_componentes(modulo)

    assert all(c["objetivo"] != "Contador" for c in plan)
    assert planner.omitidas["Contador"] == MOTIVO_COMPONENTE_SIN_CASOS
    assert planner.omitidas["Libre"] == MOTIVO_SIN_ORACULO
    assert any("exige JSDoc" in d for d in planner.descartados)


def test_humo_conserva_un_caso_normal(modulo: dict[str, Any]) -> None:
    planner = _planner({"Boton.tsx::Boton": CASOS_BOTON}, perfil="humo")
    [contrato] = planner.planificar_componentes(modulo)
    assert [c["id"] for c in contrato["casos"]] == ["muestra_etiqueta"]


def test_sin_reglas_de_componentes_no_planifica() -> None:
    from qagent.lenguajes import adaptador_para

    planner = PlannerAgent(
        ClienteContador(), TokenTracker(), adaptador=adaptador_para("python")
    )
    assert planner.planificar_componentes({"componentes": [{"nombre": "X"}]}) == []


# --- Prompt --------------------------------------------------------------------------


def test_prompt_solo_lleva_componentes_verificables_sin_cuerpo(
    modulo: dict[str, Any],
) -> None:
    prompt = prompt_componentes(modulo, humo=False)
    assert '"nombre": "Boton"' in prompt
    assert '"nombre": "Contador"' in prompt
    assert "Libre" not in prompt
    assert "onClick" not in prompt  # nunca viaja el cuerpo
    assert "Testing Library" in prompt
    assert "clases CSS" in prompt


# --- Oráculo de cada caso ------------------------------------------------------------


def _caso(**cambios: Any) -> dict[str, Any]:
    return {**CASOS_BOTON[0], **cambios}


@pytest.mark.parametrize(
    ("cambios", "fragmento"),
    [
        ({"categoria": "error"}, "no tiene casos de error"),
        (
            {"entrada": {"props": {"onPulsar": FN}}},
            "faltan props obligatorias: etiqueta",
        ),
        (
            {"entrada": {"props": {"etiqueta": 3, "onPulsar": FN}}},
            "no es compatible con string",
        ),
        (
            {"entrada": {"props": {"etiqueta": "a", "onPulsar": "x"}}},
            "prop de evento onPulsar",
        ),
        (
            {"entrada": {"props": {"etiqueta": "a", "onPulsar": FN, "color": "rojo"}}},
            "props no declaradas: color",
        ),
        ({"origen": "tipo"}, "solo garantizan que el componente renderiza"),
        (
            {
                "valor_esperado": {
                    "renderiza": True,
                    "visible": [{"texto": "Total: 10"}],
                }
            },
            "no está citado en el JSDoc",
        ),
        (
            {
                "valor_esperado": {
                    "renderiza": True,
                    "llamadas": [{"prop": "onPulsar", "veces": 1}],
                }
            },
            "necesita una interacción",
        ),
        (
            {
                "valor_esperado": {
                    "renderiza": True,
                    "llamadas": [{"prop": "onCerrar", "veces": 0}],
                }
            },
            "no es una prop de evento declarada",
        ),
    ],
)
def test_motivos_de_rechazo(
    modulo: dict[str, Any], cambios: dict[str, Any], fragmento: str
) -> None:
    motivo = motivo_caso_componente(_componente(modulo, "Boton"), _caso(**cambios))
    assert motivo is not None
    assert fragmento in motivo


def test_texto_citado_en_el_jsdoc_es_valido(modulo: dict[str, Any]) -> None:
    caso = _caso(
        entrada={"props": {"etiqueta": "", "onPulsar": FN}},
        valor_esperado={"renderiza": True, "visible": [{"texto": "Pagar ahora"}]},
    )
    assert motivo_caso_componente(_componente(modulo, "Boton"), caso) is None


def test_evento_sin_documentar_se_rechaza(modulo: dict[str, Any]) -> None:
    componente = _componente(modulo, "Boton")
    sin_doc = {
        **componente,
        "props": [
            {**p, "descripcion": ""} if p["nombre"] == "onPulsar" else p
            for p in componente["props"]
        ],
    }
    motivo = motivo_caso_componente(sin_doc, CASOS_BOTON[2])
    assert motivo is not None and "no está documentado" in motivo


def test_casos_por_tipo_aceptan_solo_render(modulo: dict[str, Any]) -> None:
    contador = _componente(modulo, "Contador")
    caso = {
        "id": "renderiza",
        "entrada": {"props": {"inicial": 0}},
        "valor_esperado": {"renderiza": True},
        "origen": "tipo",
        "categoria": "normal",
    }
    assert motivo_caso_componente(contador, caso) is None
