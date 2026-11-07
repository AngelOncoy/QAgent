"""Generator de componentes React con Testing Library y su guardrail (#171, CA3, CA4).

Estático: la prueba se parsea con tree-sitter, nunca se ejecuta (eso lo cubre la
prueba marcada ``docker`` de ``tests/sandbox``). IA simulada, sin red.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from qagent import contracts
from qagent.agents.generator import GeneratorAgent
from qagent.lenguajes import JavaScriptAdapter, TypeScriptAdapter
from qagent.lenguajes.javascript_componentes_generacion import (
    codigo_componente,
    contexto_componente,
    prompt_componente,
    validar_componente,
)
from qagent.llm import TokenTracker
from qagent.llm.fake import FakeLLMClient


def _contrato() -> dict[str, Any]:
    ruta = contracts.DIR_CONTRATOS / "ejemplos" / "planner_contract.v3.react.json"
    return json.loads(ruta.read_text(encoding="utf-8"))


def _codigo(contrato: dict[str, Any] | None = None) -> str:
    contrato = contrato or _contrato()
    return codigo_componente(contrato, contexto_componente(contrato, None))


# --- Plantilla y prompt --------------------------------------------------------------


def test_plantilla_usa_testing_library_por_rol_y_cumple_el_oraculo() -> None:
    codigo = _codigo()
    assert 'from "@testing-library/react"' in codigo
    assert 'import "@testing-library/jest-dom/vitest";' in codigo
    assert 'import { Boton } from "../proyecto/src/componentes/Boton";' in codigo
    assert 'screen.getByRole("button", { name: "Pagar" })' in codigo
    assert "fireEvent.click(" in codigo
    assert "toHaveBeenCalledTimes(1)" in codigo
    assert "querySelector" not in codigo and "className" not in codigo
    assert TypeScriptAdapter().validar_sintaxis(codigo) == []
    assert validar_componente(_contrato(), codigo) is None


def test_plantilla_jsx_valida_en_javascript() -> None:
    contrato = {**_contrato(), "lenguaje": "javascript", "modulo": "src/Boton.jsx"}
    codigo = _codigo(contrato)
    assert '"../proyecto/src/Boton.jsx"' in codigo
    assert JavaScriptAdapter().validar_sintaxis(codigo) == []
    assert validar_componente(contrato, codigo) is None


def test_exportacion_por_defecto_se_importa_sin_llaves(tmp_path: Path) -> None:
    (tmp_path / "src" / "componentes").mkdir(parents=True)
    (tmp_path / "src" / "componentes" / "Boton.tsx").write_text(
        "export default function Boton(p: { etiqueta: string }) {\n"
        "  return <button>{p.etiqueta}</button>;\n}\n",
        encoding="utf-8",
    )
    contexto = contexto_componente(_contrato(), tmp_path)
    assert contexto["importacion"].startswith("import Boton from ")


def test_ausencia_escritura_y_argumentos() -> None:
    contrato = _contrato()
    contrato["casos"] = [
        {
            "id": "busca",
            "entrada": {
                "props": {"onBuscar": {"$funcion": True}},
                "interacciones": [
                    {
                        "accion": "escribir",
                        "elemento": {"rol": "textbox"},
                        "valor": "pan",
                    },
                    {"accion": "enviar", "elemento": {"rol": "form"}},
                ],
            },
            "valor_esperado": {
                "renderiza": True,
                "ausente": [{"texto": "Sin resultados"}],
                "llamadas": [{"prop": "onBuscar", "veces": 1, "argumentos": ["pan"]}],
            },
            "origen": "docstring",
        }
    ]
    codigo = _codigo(contrato)
    assert (
        'fireEvent.change(screen.getByRole("textbox"), { target: { value: "pan" } });'
        in codigo
    )
    assert 'expect(screen.queryByText("Sin resultados")).toBeNull();' in codigo
    assert 'toHaveBeenCalledWith("pan")' in codigo
    assert validar_componente(contrato, codigo) is None


def test_prompt_prohibe_selectores_e_instantaneas() -> None:
    prompt = prompt_componente(_contrato(), 1, None, None)
    assert "Testing Library" in prompt
    assert "querySelector" in prompt and "toMatchSnapshot" in prompt
    assert "jsdom" in prompt


# --- Oráculo de la prueba generada ---------------------------------------------------


@pytest.mark.parametrize(
    ("cambio", "fragmento"),
    [
        (
            (
                'screen.getByRole("button", { name: "Pagar" })).toBeInTheDocument',
                'document.querySelector(".btn-pagar")).toBeInTheDocument',
            ),
            "selectores",
        ),
        (
            (
                "render(<Boton {...props} />);\n    expect(screen.getByRole",
                "const { container } = render(<Boton {...props} />);\n    expect(screen.getByRole",
            ),
            "container",
        ),
        (
            (
                'expect(screen.getByRole("button", { name: "Pagar" })).toBeInTheDocument();',
                "expect(document.body).toMatchSnapshot();",
            ),
            "",
        ),
        (("toHaveBeenCalledTimes(1)", "toHaveBeenCalledTimes(2)"), "pulsar_avisa"),
        (
            ('name: "Pagar" })).toBeInTheDocument', 'name: "Pagar" })).toBeTruthy'),
            "muestra_la_etiqueta",
        ),
        (('it("sin_props_opcionales"', 'it.skip("sin_props_opcionales"'), "omitida"),
        (('from "@testing-library/react"', 'from "@testing-library/dom"'), "render"),
        (("../proyecto/src/componentes/Boton", "./Boton"), "importar el componente"),
    ],
)
def test_oraculo_rechaza(cambio: tuple[str, str], fragmento: str) -> None:
    antes, despues = cambio
    codigo = _codigo()
    assert antes in codigo
    motivo = validar_componente(_contrato(), codigo.replace(antes, despues, 1))
    assert motivo is not None and motivo.startswith("Oráculo inválido")
    assert fragmento in motivo


def test_instantanea_se_rechaza_aunque_cumpla_lo_demas() -> None:
    codigo = _codigo().replace(
        "  });\n});", "    expect(document.body).toMatchSnapshot();\n  });\n});"
    )
    motivo = validar_componente(_contrato(), codigo)
    assert motivo is not None and "instantánea" in motivo


def test_mock_sin_mock_name_vale_con_un_solo_evento() -> None:
    codigo = _codigo().replace('vi.fn().mockName("onPulsar")', "vi.fn()")
    assert validar_componente(_contrato(), codigo) is None


# --- Guardrail de Assertion Laundering (CA4) -----------------------------------------


@pytest.mark.parametrize(
    ("antes", "despues"),
    [
        ("toHaveBeenCalledTimes(1)", "toHaveBeenCalled()"),
        (".toBeInTheDocument()", ".toBeTruthy()"),
        (
            'expect(screen.getByRole("button", { name: "Pagar" })).toBeInTheDocument();',
            "",
        ),
        ('it("pulsar_avisa"', 'it.todo("pulsar_avisa"'),
        (
            "expect(onPulsar).toHaveBeenCalledTimes(1);",
            "expect(onPulsar).not.toHaveBeenCalledTimes(1);",
        ),
        (".not.toThrow()", ".toThrow()"),
    ],
)
def test_laundering_en_pruebas_de_componentes(antes: str, despues: str) -> None:
    original = _codigo()
    assert antes in original
    resultado = TypeScriptAdapter().comparar_aserciones(
        original, original.replace(antes, despues, 1)
    )
    assert resultado.es_laundering, resultado.resumen


def test_reformatear_no_es_laundering() -> None:
    original = _codigo()
    reparado = original.replace('{ name: "Pagar" }', "{ name: 'Pagar' }").replace(
        "  it(", "\n  it("
    )
    assert not TypeScriptAdapter().comparar_aserciones(original, reparado).es_laundering


# --- Generator compartido con IA simulada --------------------------------------------


def test_generator_entrega_generated_test_v2_tsx() -> None:
    generador = GeneratorAgent(
        FakeLLMClient(grabaciones={}), TokenTracker(), es_simulado=True
    )
    contrato = _contrato()
    prueba = generador.generar(contrato, 1, None)

    assert contracts.errores(contracts.GENERATED_TEST_V2, prueba) == []
    assert prueba["archivo"] == "generado.test.tsx"
    assert prueba["framework_pruebas"] == "vitest"
    assert (
        TypeScriptAdapter().validar_oraculo(contrato, prueba["codigo"], Path("."))
        is None
    )


def test_generator_en_javascript_usa_jsx() -> None:
    generador = GeneratorAgent(
        FakeLLMClient(grabaciones={}), TokenTracker(), es_simulado=True
    )
    contrato = copy.deepcopy(_contrato())
    contrato.update(lenguaje="javascript", modulo="src/Boton.jsx")
    assert generador.generar(contrato, 1, None)["archivo"] == "generado.test.jsx"
