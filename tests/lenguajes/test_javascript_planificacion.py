"""Planner con las reglas de JavaScript/TypeScript: v3 + Vitest y oráculo estricto (#176).

Usa la IA simulada con casos grabados: ninguna prueba llama a una API real.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from qagent import contracts
from qagent.agents.planner import MOTIVO_OMITIDA, PlannerAgent, contrato_sin_triviales
from qagent.lenguajes import JavaScriptAdapter, NoImplementado, TypeScriptAdapter
from qagent.lenguajes.javascript_planificacion import (
    REGLAS_PLANIFICACION_JAVASCRIPT,
    REGLAS_PLANIFICACION_TYPESCRIPT,
    prompt_funciones,
)
from qagent.llm import TokenTracker
from qagent.llm.fake import MARCA_OBJETIVOS, FakeLLMClient

FUENTE = """/**
 * Clasifica a una persona según su edad.
 * @param {number} edad años cumplidos
 * @throws {RangeError} si la edad es negativa
 * @example
 * clasificar(10) // => "menor"
 * clasificar(30) // => "adulto"
 */
export function clasificar(edad: number): "menor" | "adulto" | "mayor" {
  if (edad < 0) throw new RangeError("negativa");
  return edad < 18 ? "menor" : edad < 65 ? "adulto" : "mayor";
}

export function sumar(a: number, b: number): number { return a + b; }

/**
 * Promedio de los valores.
 * @returns {number} el promedio aritmético
 */
export function promedio(...xs: number[]): number { return 0; }

/** @returns la versión del formato */
export function version(): "v1" { return "v1"; }
"""


@pytest.fixture
def modulo(tmp_path: Path) -> dict[str, Any]:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "personas.ts").write_text(FUENTE, encoding="utf-8")
    [modulo] = TypeScriptAdapter().analizar(tmp_path)["modulos"]
    return modulo


def _planner(grabaciones: dict[str, list[dict[str, Any]]], adaptador=None):
    return PlannerAgent(
        FakeLLMClient(grabaciones=grabaciones),
        TokenTracker(),
        es_simulado=True,
        adaptador=adaptador or TypeScriptAdapter(),
    )


def _funcion(modulo: dict[str, Any], nombre: str) -> dict[str, Any]:
    return next(f for f in modulo["funciones"] if f["nombre"] == nombre)


# --- El adaptador entrega las reglas --------------------------------------------------


def test_cada_adaptador_tiene_sus_reglas_y_vitest() -> None:
    assert TypeScriptAdapter().reglas_planificacion() is REGLAS_PLANIFICACION_TYPESCRIPT
    assert JavaScriptAdapter().reglas_planificacion() is REGLAS_PLANIFICACION_JAVASCRIPT
    assert TypeScriptAdapter().framework_predeterminado == "vitest"
    assert JavaScriptAdapter().framework_predeterminado == "vitest"
    # Siguen en desarrollo: la app no ofrece JS/TS hasta tener generación y ejecución.
    assert TypeScriptAdapter().completo is False


def test_endpoints_express_aun_no_se_planifican() -> None:
    with pytest.raises(NoImplementado, match="Express"):
        REGLAS_PLANIFICACION_TYPESCRIPT.prompt_endpoints({}, {}, None, False)


# --- Prompt ---------------------------------------------------------------------------


def test_prompt_solo_con_funciones_verificables_y_sin_cuerpos(modulo) -> None:
    prompt = prompt_funciones(modulo, humo=False)
    objetivos = json.loads(prompt.split(MARCA_OBJETIVOS, 1)[1])

    assert [o["nombre"] for o in objetivos] == ["clasificar", "version"]
    clasificar = objetivos[0]
    assert (
        clasificar["firma"] == 'clasificar(edad: number): "menor" | "adulto" | "mayor"'
    )
    assert clasificar["jsdoc"]["ejemplos"] == [
        'clasificar(10) // => "menor"\nclasificar(30) // => "adulto"'
    ]
    assert {e["id"] for e in clasificar["evidencias"]} == {
        "jsdoc:clasificar:ejemplo:1",
        "jsdoc:clasificar:ejemplo:2",
        "jsdoc:clasificar:throws:1",
    }
    assert "Vitest" in prompt
    assert "edad < 18" not in prompt  # nunca el cuerpo
    assert "critical" not in prompt.split(MARCA_OBJETIVOS, 1)[1]


def test_prompt_de_humo(modulo) -> None:
    assert "un único caso normal" in prompt_funciones(modulo, humo=True)


# --- Planner de punta a punta ---------------------------------------------------------


CASOS_CLASIFICAR = [
    {
        "id": "menor",
        "entrada": {"edad": 10},
        "valor_esperado": "menor",
        "origen": "docstring",
        "categoria": "normal",
    },
    {
        "id": "adulto",
        "entrada": [30],
        "valor_esperado": "adulto",
        "origen": "docstring",
        "categoria": "normal",
    },
    {
        "id": "negativa",
        "entrada": {"edad": -3},
        "excepcion": "RangeError",
        "origen": "docstring",
        "categoria": "error",
    },
    # Inventado: ningún @example documenta 70.
    {
        "id": "mayor",
        "entrada": {"edad": 70},
        "valor_esperado": "mayor",
        "origen": "docstring",
        "categoria": "normal",
    },
    # Bug sembrado de la IA: contradice el @example.
    {
        "id": "menor_mal",
        "entrada": {"edad": 10},
        "valor_esperado": "adulto",
        "origen": "docstring",
        "categoria": "normal",
    },
    # No corresponde a la firma.
    {
        "id": "texto",
        "entrada": {"edad": "diez"},
        "valor_esperado": "menor",
        "origen": "docstring",
    },
]


def test_planner_emite_v3_vitest_con_oraculos_verificables(modulo) -> None:
    planner = _planner(
        {
            "personas.ts::clasificar": CASOS_CLASIFICAR,
            "personas.ts::version": [
                {"id": "v1", "entrada": [], "valor_esperado": "v1", "origen": "tipo"}
            ],
        }
    )
    plan = {c["objetivo"]: c for c in planner.planificar(modulo)}

    assert set(plan) == {"clasificar", "version"}
    for contrato in plan.values():
        contracts.validar(contracts.PLANNER_V3, contrato)
        assert contrato["lenguaje"] == "typescript"
        assert contrato["framework_pruebas"] == "vitest"
        assert contrato["modulo"] == "src/personas.ts"
        assert contrato["huella"] == modulo["huella"]
    clasificar = plan["clasificar"]
    assert [c["id"] for c in clasificar["casos"]] == ["menor", "adulto", "negativa"]
    assert clasificar["critical"] is True
    assert plan["version"]["critical"] is False
    descartados = "\n".join(planner.descartados)
    assert "'mayor'" in descartados and "no documenta un valor concreto" in descartados
    assert "'menor_mal'" in descartados and "no coincide" in descartados
    assert "'texto'" in descartados and "no corresponden a la firma" in descartados


def test_funciones_sin_jsdoc_ni_tipos_verificables_quedan_omitidas(modulo) -> None:
    # Aunque el modelo propusiera casos, sumar y promedio nunca se le piden.
    planner = _planner(
        {
            "personas.ts::clasificar": CASOS_CLASIFICAR[:1],
            "personas.ts::sumar": [
                {"id": "s", "entrada": [1, 2], "valor_esperado": 3, "origen": "tipo"}
            ],
        }
    )
    plan = planner.planificar(modulo)

    assert [c["objetivo"] for c in plan] == ["clasificar"]
    assert set(planner.omitidas) == {"sumar", "promedio", "version"}
    assert planner.omitidas["sumar"] == (
        f"la función no tiene docstring y {MOTIVO_OMITIDA}"
    )
    assert "resultado esperado verificable" in planner.omitidas["promedio"]


def test_un_modulo_sin_nada_verificable_no_es_un_error(tmp_path: Path) -> None:
    (tmp_path / "a.js").write_text(
        "export function suma(a, b) { return a + b; }", encoding="utf-8"
    )
    [modulo] = JavaScriptAdapter().analizar(tmp_path)["modulos"]
    planner = _planner({}, JavaScriptAdapter())

    assert planner.planificar(modulo) == []
    assert set(planner.omitidas) == {"suma"}


def test_humo_conserva_un_caso_normal(modulo) -> None:
    planner = PlannerAgent(
        FakeLLMClient(grabaciones={"personas.ts::clasificar": CASOS_CLASIFICAR}),
        TokenTracker(),
        es_simulado=True,
        perfil="humo",
        adaptador=TypeScriptAdapter(),
    )
    [contrato] = planner.planificar(modulo)
    assert [c["id"] for c in contrato["casos"]] == ["menor"]


# --- Filtros sueltos ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "trivial"),
    [
        ({"xs": [1, 2]}, False),
        ([1, 2, 3], False),
        ([], False),
        ({"xs": ["a"]}, True),
        (["a"], True),
        ({"ys": [1]}, True),
    ],
)
def test_es_caso_trivial_con_resto(modulo, entrada: Any, trivial: bool) -> None:
    funcion = _funcion(modulo, "promedio")
    caso = {"id": "c", "entrada": entrada, "valor_esperado": 1, "origen": "docstring"}
    assert REGLAS_PLANIFICACION_TYPESCRIPT.es_caso_trivial(funcion, caso) is trivial


@pytest.mark.parametrize(
    ("entrada", "trivial"),
    [([1, 2], False), ([1], True), ([1, 2, 3], True), ([1, True], True)],
)
def test_es_caso_trivial_desde_la_firma_de_un_contrato(entrada, trivial) -> None:
    contrato = {"firma": "async sumar(a: number, b: number): Promise<number>"}
    caso = {"id": "c", "entrada": entrada, "valor_esperado": 3, "origen": "docstring"}
    assert REGLAS_PLANIFICACION_TYPESCRIPT.es_caso_trivial(contrato, caso) is trivial


def test_es_caso_trivial_usa_los_tipos_del_jsdoc_en_javascript(tmp_path: Path) -> None:
    (tmp_path / "a.js").write_text(
        "/** @param {string} nombre\n @example saludar('Ana') // => 'Hola Ana' */\n"
        "export function saludar(nombre) { return 'Hola ' + nombre; }",
        encoding="utf-8",
    )
    [modulo] = JavaScriptAdapter().analizar(tmp_path)["modulos"]
    funcion = modulo["funciones"][0]
    reglas = REGLAS_PLANIFICACION_JAVASCRIPT
    assert reglas.es_caso_trivial(funcion, {"entrada": [5]}) is True
    assert reglas.es_caso_trivial(funcion, {"entrada": ["Ana"]}) is False


def test_contrato_guardado_sin_triviales(modulo) -> None:
    contrato = {
        "version": "3",
        "lenguaje": "typescript",
        "framework_pruebas": "vitest",
        "modulo": "src/personas.ts",
        "huella": modulo["huella"],
        "tipo": "funcion",
        "objetivo": "sumar",
        "critical": False,
        "firma": "sumar(a: number, b: number): number",
        "casos": [
            {
                "id": "bien",
                "entrada": [1, 2],
                "valor_esperado": 3,
                "origen": "docstring",
            },
            {"id": "mal", "entrada": [1], "valor_esperado": 1, "origen": "docstring"},
        ],
    }
    limpio = contrato_sin_triviales(contrato)
    assert [c["id"] for c in limpio["casos"]] == ["bien"]


def test_motivo_oraculo_sin_registro_o_con_tupla(modulo) -> None:
    reglas = REGLAS_PLANIFICACION_TYPESCRIPT
    caso = {"entrada": [10], "valor_esperado": "menor", "origen": "docstring"}
    assert "registro de evidencias" in reglas.motivo_oraculo_funcion(
        {"nombre": "clasificar", "firma": "clasificar(edad: number)"}, caso
    )
    funcion = _funcion(modulo, "clasificar")
    assert reglas.motivo_oraculo_funcion(funcion, caso) is None
    assert "tuplas" in reglas.motivo_oraculo_funcion(
        funcion, {**caso, "valor_esperado": [1], "tipo_valor_esperado": "tuple"}
    )
