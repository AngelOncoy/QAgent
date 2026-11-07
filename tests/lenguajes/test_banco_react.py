"""Banco React multilenguaje (#171, CA7): análisis y plan con la IA simulada.

Sin Docker ni red. La corrida real con Vitest, Testing Library y jsdom está en
``tests/sandbox/test_react_corrida_docker.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from qagent import contracts
from qagent.agents.generator import GeneratorAgent
from qagent.agents.planner import PlannerAgent
from qagent.lenguajes import TypeScriptAdapter
from qagent.lenguajes.javascript_componentes import MOTIVO_SIN_ORACULO
from qagent.llm import TokenTracker
from qagent.llm.fake import FakeLLMClient

BANCO = Path(__file__).resolve().parents[2] / "bench" / "multilenguaje" / "react"
FN = {"$funcion": True}

#: Respuestas grabadas del Planner para el banco: un componente correcto, uno con un
#: bug sembrado (el JSDoc promete «Agotado») y la función de lógica.
GRABACIONES: dict[str, list[dict[str, Any]]] = {
    "Boton.tsx::Boton": [
        {
            "id": "muestra_la_etiqueta",
            "descripcion": "La etiqueta documentada es el nombre accesible del botón",
            "entrada": {"props": {"etiqueta": "Pagar", "onPulsar": FN}},
            "valor_esperado": {
                "renderiza": True,
                "visible": [{"rol": "button", "nombre": "Pagar"}],
            },
            "origen": "docstring",
            "categoria": "normal",
        },
        {
            "id": "sin_props_opcionales",
            "descripcion": "deshabilitado es opcional",
            "entrada": {"props": {"etiqueta": "Pagar", "onPulsar": FN}},
            "valor_esperado": {"renderiza": True},
            "origen": "tipo",
            "categoria": "limite",
        },
        {
            "id": "pulsar_avisa_una_vez",
            "descripcion": "onPulsar se llama una vez por pulsación",
            "entrada": {
                "props": {"etiqueta": "Pagar", "onPulsar": FN},
                "interacciones": [
                    {
                        "accion": "click",
                        "elemento": {"rol": "button", "nombre": "Pagar"},
                    }
                ],
            },
            "valor_esperado": {
                "renderiza": True,
                "llamadas": [{"prop": "onPulsar", "veces": 1}],
            },
            "origen": "docstring",
            "categoria": "normal",
        },
    ],
    "Insignia.tsx::Insignia": [
        {
            "id": "agotado_muestra_el_texto",
            "descripcion": "Sin stock muestra «Agotado» (JSDoc)",
            "entrada": {"props": {"disponible": False}},
            "valor_esperado": {"renderiza": True, "visible": [{"texto": "Agotado"}]},
            "origen": "docstring",
            "categoria": "normal",
        },
        {
            "id": "con_stock_no_muestra_nada",
            "descripcion": "Con stock no aparece «Agotado» (JSDoc)",
            "entrada": {"props": {"disponible": True}},
            "valor_esperado": {"renderiza": True, "ausente": [{"texto": "Agotado"}]},
            "origen": "docstring",
            "categoria": "limite",
        },
    ],
    "formato.ts::formatearPrecio": [
        {
            "id": "ejemplo_jsdoc",
            "entrada": {"monto": 5},
            "valor_esperado": "S/ 5.00",
            "origen": "docstring",
            "categoria": "normal",
        }
    ],
}


def _modulos() -> dict[str, dict[str, Any]]:
    estructura = TypeScriptAdapter().analizar(BANCO)
    assert estructura["errores"] == []
    return {m["ruta"]: m for m in estructura["modulos"]}


def test_banco_detecta_react_y_separa_componentes() -> None:
    estructura = TypeScriptAdapter().analizar(BANCO)
    assert estructura["framework_ui"]["framework"] == "react"
    assert estructura["framework_ui"]["componentes"] == 3
    assert estructura["framework_ui"]["verificables"] == 2
    modulos = _modulos()
    assert [f["nombre"] for f in modulos["src/formato.ts"]["funciones"]] == [
        "formatearPrecio"
    ]
    assert modulos["src/Insignia.tsx"]["componentes"][0]["exportacion"] == "default"
    assert modulos["src/Libre.tsx"]["componentes"][0]["verificable"] is False


def test_banco_planifica_y_genera_con_ia_simulada() -> None:
    planner = PlannerAgent(
        FakeLLMClient(grabaciones=GRABACIONES),
        TokenTracker(),
        es_simulado=True,
        adaptador=TypeScriptAdapter(),
    )
    generador = GeneratorAgent(
        FakeLLMClient(grabaciones={}),
        TokenTracker(),
        es_simulado=True,
        ruta_proyecto=BANCO,
    )
    modulos = _modulos()
    contratos = []
    for ruta in ("src/Boton.tsx", "src/Insignia.tsx"):
        contratos += planner.planificar_componentes(modulos[ruta])
    assert [c["objetivo"] for c in contratos] == ["Boton", "Insignia"]

    assert planner.planificar_componentes(modulos["src/Libre.tsx"]) == []
    assert planner.omitidas == {"Libre": MOTIVO_SIN_ORACULO}

    for contrato in contratos:
        prueba = generador.generar(contrato, 1, None)
        assert contracts.errores(contracts.GENERATED_TEST_V2, prueba) == []
        assert (
            TypeScriptAdapter().validar_oraculo(contrato, prueba["codigo"], BANCO)
            is None
        )
    insignia = generador.generar(contratos[1], 1, None)["codigo"]
    assert 'import Insignia from "../proyecto/src/Insignia";' in insignia
