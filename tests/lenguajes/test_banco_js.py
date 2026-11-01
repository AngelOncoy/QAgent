"""Banco JS/TS con bugs sembrados (``bench/banco_mvp_js``), sin Docker ni red (#176).

Equivale a ``bench/banco_mvp.py``: comprueba que el análisis encuentra las funciones
en ESM y CommonJS, ignora dependencias, compilados y pruebas existentes, y que el
Planner (con la IA simulada) emite ``planner_contract.v3`` válidos cuyos valores
esperados salen del JSDoc y de los tipos. Los casos que copian el comportamiento
con bug del código se rechazan: el oráculo nunca sale de la implementación.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from qagent import contracts
from qagent.agents.planner import PlannerAgent
from qagent.lenguajes import JavaScriptAdapter, TypeScriptAdapter
from qagent.lenguajes.base import LanguageAdapter
from qagent.lenguajes.javascript_oraculo import oraculo_del_caso
from qagent.llm import TokenTracker
from qagent.llm.fake import FakeLLMClient

BANCO = Path(__file__).resolve().parents[2] / "bench" / "banco_mvp_js"


def _caso(id_: str, entrada: Any, origen: str = "docstring", **esperado: Any):
    return {"id": id_, "entrada": entrada, "origen": origen, **esperado}


#: Lo que propondría el modelo. Los ``*_como_el_codigo`` repiten el resultado con bug.
GRABACIONES = {
    "precios.ts::calcularDescuento": [
        _caso("descuento_normal", {"precio": 100, "porcentaje": 20}, valor_esperado=80),
        _caso("sin_descuento", [50, 0], valor_esperado=50),
        _caso("precio_negativo", [-1, 10], excepcion="RangeError", categoria="error"),
        _caso("porcentaje_alto", [10, 150], excepcion="RangeError", categoria="error"),
        _caso("descuento_como_el_codigo", [100, 20], valor_esperado=20),
    ],
    "personas.mjs::clasificarEdad": [
        _caso("menor", [10], valor_esperado="menor"),
        _caso("frontera_18", {"edad": 18}, valor_esperado="adulto", categoria="limite"),
        _caso("frontera_65", [65], valor_esperado="adulto mayor", categoria="limite"),
        _caso("negativa", [-1], excepcion="RangeError", categoria="error"),
        _caso("frontera_como_el_codigo", [18], valor_esperado="menor"),
        _caso("sin_ejemplo", [40], valor_esperado="adulto"),
    ],
    "listas.cjs::buscarElementoMayor": [
        _caso("positivos", [[3, 9, 2]], valor_esperado=9),
        _caso("negativos", {"numeros": [-10, -5, -20]}, valor_esperado=-5),
        _caso("vacia", [[]], excepcion="RangeError", categoria="error"),
        _caso("negativos_como_el_codigo", [[-10, -5, -20]], valor_esperado=0),
    ],
    "texto.ts::esPalindromo": [
        _caso("frase", ["Anita lava la tina"], valor_esperado=True),
        _caso("no", ["QAgent"], valor_esperado=False),
    ],
    "texto.ts::invertirPalabras": [
        _caso("tres", ["hola  mundo cruel"], valor_esperado="cruel mundo hola"),
    ],
    "texto.ts::Formateador.moneda": [
        _caso("simbolo_por_defecto", {"cantidad": 12.5}, valor_esperado="$12.50"),
        _caso("soles", [3, "S/ "], valor_esperado="S/ 3.00"),
    ],
    "texto.ts::versionFormato": [_caso("v1", [], "tipo", valor_esperado="v1")],
    # Nunca se piden: no tienen evidencia que fije un resultado.
    "sin_documentar.js::mezclar": [_caso("m", [3, 1], valor_esperado=2)],
    "sin_documentar.js::promedio": [_caso("p", [[1, 3]], valor_esperado=2)],
}


@pytest.fixture(scope="module")
def proyecto(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Copia del banco con lo que el análisis debe ignorar."""
    raiz = tmp_path_factory.mktemp("banco_js")
    shutil.copytree(BANCO, raiz, dirs_exist_ok=True)
    distractores = {
        "node_modules/lodash/index.js": "export function chunk(a) { return a; }",
        "dist/precios.js": "export function calcularDescuento(p) { return p; }",
        "src/precios.test.ts": "export function prueba() {}",
        "src/__tests__/listas.spec.cjs": "exports.caso = function () {};",
        "src/tipos.d.ts": "export declare function declarada(): void;",
    }
    for relativa, codigo in distractores.items():
        ruta = raiz / relativa
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(codigo, encoding="utf-8")
    return raiz


def _analisis(adaptador: LanguageAdapter, proyecto: Path) -> dict[str, Any]:
    estructura = adaptador.analizar(proyecto)
    assert estructura["errores"] == []
    return estructura


def _planificar(
    adaptador: LanguageAdapter, estructura: dict[str, Any]
) -> tuple[dict[str, dict[str, Any]], dict[str, str], list[str]]:
    planner = PlannerAgent(
        FakeLLMClient(grabaciones=GRABACIONES),
        TokenTracker(),
        es_simulado=True,
        adaptador=adaptador,
    )
    plan: dict[str, dict[str, Any]] = {}
    omitidas: dict[str, str] = {}
    descartados: list[str] = []
    for modulo in estructura["modulos"]:
        for contrato in planner.planificar(modulo):
            plan[contrato["objetivo"]] = contrato
        omitidas |= planner.omitidas
        descartados += planner.descartados
    return plan, omitidas, descartados


# --- Análisis -------------------------------------------------------------------------


def test_objetivos_del_banco(proyecto: Path) -> None:
    js, ts = JavaScriptAdapter(), TypeScriptAdapter()
    objetivos = js.objetivos(_analisis(js, proyecto)) + ts.objetivos(
        _analisis(ts, proyecto)
    )
    assert {(o["modulo"], o["objetivo"]): o["critical"] for o in objetivos} == {
        ("src/listas.cjs", "buscarElementoMayor"): True,
        ("src/personas.mjs", "clasificarEdad"): True,
        ("src/sin_documentar.js", "mezclar"): True,
        ("src/sin_documentar.js", "promedio"): False,
        ("src/precios.ts", "calcularDescuento"): True,
        ("src/texto.ts", "esPalindromo"): False,
        ("src/texto.ts", "invertirPalabras"): False,
        ("src/texto.ts", "Formateador.moneda"): False,
        ("src/texto.ts", "versionFormato"): False,
    }


def test_resumen_del_banco(proyecto: Path) -> None:
    resumen = _analisis(TypeScriptAdapter(), proyecto)["resumen"]
    assert resumen["total_modulos"] == 2
    assert resumen["total_funciones_publicas"] == 5
    assert resumen["total_errores"] == 0


# --- Planificación --------------------------------------------------------------------


@pytest.fixture(scope="module")
def planes(proyecto: Path):
    resultado = {}
    for adaptador in (JavaScriptAdapter(), TypeScriptAdapter()):
        estructura = _analisis(adaptador, proyecto)
        resultado[adaptador.lenguaje] = (
            estructura,
            *_planificar(adaptador, estructura),
        )
    return resultado


def test_contratos_v3_validos_con_vitest(planes) -> None:
    for lenguaje, (_, plan, _, _) in planes.items():
        assert plan
        for contrato in plan.values():
            contracts.validar(contracts.PLANNER_V3, contrato)
            contracts.validar_versionado(contracts.FAMILIA_PLANNER, contrato)
            assert contrato["lenguaje"] == lenguaje
            assert contrato["framework_pruebas"] == "vitest"
            assert "framework_app" not in contrato


def test_cada_caso_tiene_un_oraculo_verificable_jsdoc_o_typescript(planes) -> None:
    for lenguaje, (estructura, plan, _, _) in planes.items():
        funciones = {
            f["nombre"]: f for m in estructura["modulos"] for f in m["funciones"]
        }
        for contrato in plan.values():
            funcion = funciones[contrato["objetivo"]]
            for caso in contrato["casos"]:
                oraculo, motivo = oraculo_del_caso(
                    lenguaje, contrato["modulo"], funcion, caso
                )
                assert motivo is None, (contrato["objetivo"], caso["id"], motivo)
                assert oraculo["estado_evidencia"] == "verificable"
                assert oraculo["evidencia"]["fuente"] in {"jsdoc", "typescript"}
                contracts.validar_oraculo_js_ts(oraculo, funcion["evidencias"])


def test_los_casos_que_detectan_los_bugs_sembrados_se_planifican(planes) -> None:
    _, plan_js, _, _ = planes["javascript"]
    _, plan_ts, _, _ = planes["typescript"]
    casos = {
        (c["objetivo"], caso["id"]): caso
        for c in [*plan_js.values(), *plan_ts.values()]
        for caso in c["casos"]
    }
    # Bug 1, 2 y 3 (ver bench/banco_mvp_js/README.md).
    assert casos[("calcularDescuento", "descuento_normal")]["valor_esperado"] == 80
    assert casos[("clasificarEdad", "frontera_18")]["valor_esperado"] == "adulto"
    assert casos[("buscarElementoMayor", "negativos")]["valor_esperado"] == -5


def test_el_comportamiento_con_bug_no_es_un_oraculo(planes) -> None:
    ids = {
        (c["objetivo"], caso["id"])
        for _, plan, _, _ in planes.values()
        for c in plan.values()
        for caso in c["casos"]
    }
    for objetivo, id_ in [
        ("calcularDescuento", "descuento_como_el_codigo"),
        ("clasificarEdad", "frontera_como_el_codigo"),
        ("buscarElementoMayor", "negativos_como_el_codigo"),
        ("clasificarEdad", "sin_ejemplo"),
    ]:
        assert (objetivo, id_) not in ids
    descartados = "\n".join(d for _, _, _, ds in planes.values() for d in ds)
    assert "'descuento_como_el_codigo'" in descartados
    assert "'sin_ejemplo'" in descartados


def test_casos_por_funcion(planes) -> None:
    _, plan_js, _, _ = planes["javascript"]
    _, plan_ts, _, _ = planes["typescript"]
    ids = {
        objetivo: [c["id"] for c in contrato["casos"]]
        for objetivo, contrato in {**plan_js, **plan_ts}.items()
    }
    assert ids == {
        "buscarElementoMayor": ["positivos", "negativos", "vacia"],
        "clasificarEdad": ["menor", "frontera_18", "frontera_65", "negativa"],
        "calcularDescuento": [
            "descuento_normal",
            "sin_descuento",
            "precio_negativo",
            "porcentaje_alto",
        ],
        "esPalindromo": ["frase", "no"],
        "invertirPalabras": ["tres"],
        "Formateador.moneda": ["simbolo_por_defecto", "soles"],
        "versionFormato": ["v1"],
    }


def test_sin_resultado_esperado_verificable(planes) -> None:
    _, plan, omitidas, _ = planes["javascript"]
    assert "mezclar" not in plan and "promedio" not in plan
    assert set(omitidas) == {"mezclar", "promedio"}
    assert all("resultado esperado verificable" in m for m in omitidas.values())
    assert omitidas["mezclar"].startswith("la función no tiene docstring")
