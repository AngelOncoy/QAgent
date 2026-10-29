"""#168: el Planner, el Generator y el Reviewer no conocen el lenguaje.

Se registra por un momento un adaptador de JavaScript de prueba (con Vitest) y se
comprueba que los agentes usan sus prompts, sus reglas y su comando, y que producen
contratos v3 y generated_test.v2 de JavaScript. Sin Docker ni red.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from qagent import contracts
from qagent.agents.generator import ErrorRespuestaGenerator, GeneratorAgent
from qagent.agents.planner import PlannerAgent
from qagent.agents.reviewer import ReviewerAgent
from qagent.lenguajes import REGISTRO, JavaScriptAdapter, NoImplementado
from qagent.lenguajes.base import Clasificacion, EntornoSandbox
from qagent.llm import RespuestaLLM, TokenTracker
from qagent.sandbox import ResultadoSandbox
from qagent.sandbox.ejecucion import DIR_SALIDA, DIR_TESTS


class ClienteGrabado:
    def __init__(self, contenido: str) -> None:
        self.contenido = contenido
        self.prompts: list[str] = []

    def generar(self, prompt: str, rol: str = "planner") -> RespuestaLLM:
        self.prompts.append(prompt)
        return RespuestaLLM(self.contenido, 1, 1, 0.0, "modelo")


class ReglasJs:
    motivo_caso_trivial = "trivial en JS"
    motivo_omitida_trivial = "omitida en JS"

    def prompt_funciones(self, modulo: dict[str, Any], humo: bool) -> str:
        return f"PROMPT-JS {modulo['ruta']} humo={humo}"

    def prompt_endpoints(self, modulo, endpoints, fuente, humo) -> str:
        return "PROMPT-JS-ENDPOINTS"

    def preparar_caso(self, funcion, caso):
        return caso

    def es_caso_trivial(self, funcion, caso) -> bool:
        return caso.get("id") == "trivial"

    def motivo_limite_funcion(self, funcion, caso):
        return None

    def motivo_oraculo_funcion(self, funcion, caso):
        return None

    def aplicacion_principal(self, endpoints) -> str:
        return "app"

    def dependencias_con_reemplazo(self, modulo, endpoint):
        return []

    def motivo_rechazo_endpoint(self, endpoint, caso, modelos):
        return None

    def motivo_limite_endpoint(self, endpoint, caso, modelos):
        return None

    def faltantes_endpoint(self, endpoint, casos):
        return []

    # Reglas de revisión
    def error_de_sintaxis(self, codigo: str) -> str | None:
        return None if "expect(" in codigo else "falta expect"

    def validar_oraculo(self, contrato, codigo) -> str | None:
        return None if "toBe(4)" in codigo else "Oráculo inválido: falta toBe(4)"

    def clasificar_salida(self, salida, contrato, raiz):
        if "AssertionError" in salida:
            return Clasificacion("fallo_asercion", salida)
        return None

    def rango_de_objetivo(self, raiz, modulo, nombre):
        return (1, 3)


class AdaptadorJsDePrueba(JavaScriptAdapter):
    completo = True
    frameworks_pruebas = ("vitest", "jest")

    def __init__(self) -> None:
        self.reglas = ReglasJs()
        self.comparaciones: list[tuple[str, str]] = []

    def reglas_planificacion(self):
        return self.reglas

    def reglas_revision(self):
        return self.reglas

    def prompt_generator(self, contrato, intento, feedback, ruta_proyecto) -> str:
        return f"GENERAR-JS {contrato['objetivo']} intento={intento} {feedback}"

    def comando_pruebas(self, modulo: str, framework: str | None = None) -> list[str]:
        return ["vitest", "run", "--coverage", modulo, self.elegir_framework(framework)]

    def entorno_sandbox(self) -> EntornoSandbox:
        return EntornoSandbox("qagent-sandbox:node", (), DIR_TESTS, DIR_SALIDA, "j.xml")

    def archivo_de_prueba(self, objetivo: str) -> str:
        return f"{objetivo}.test.js"

    def interpretar_resultados(self, informe: str) -> dict[str, Any]:
        return {
            "total": 1,
            "pasaron": 1,
            "fallaron": 0,
            "errores": 0,
            "omitidos": 0,
            "duracion_s": 0.5,
            "inicio": None,
            "casos": [],
        }

    def comparar_aserciones(self, original: str, reparado: str):
        self.comparaciones.append((original, reparado))

        class Sin:
            es_laundering = False
            resumen = ""

        return Sin()


@pytest.fixture
def adaptador():
    original = REGISTRO.adaptador_para("javascript")
    prueba = AdaptadorJsDePrueba()
    REGISTRO.registrar(prueba, reemplazar=True)
    yield prueba
    REGISTRO.registrar(original, reemplazar=True)


MODULO = {
    "ruta": "src/suma.js",
    "huella": "b" * 64,
    "funciones": [{"nombre": "suma", "firma": "(a, b)", "docstring": "Suma."}],
}
CASOS = [
    {
        "id": "suma_normal",
        "entrada": {"a": 2, "b": 2},
        "valor_esperado": 4,
        "origen": "docstring",
    },
    {"id": "trivial", "entrada": {}, "excepcion": "TypeError", "origen": "firma"},
]


def _contrato(adaptador) -> dict[str, Any]:
    cliente = ClienteGrabado(json.dumps([{"objetivo": "suma", "casos": CASOS}]))
    planner = PlannerAgent(cliente, TokenTracker(), adaptador=adaptador)
    [contrato] = planner.planificar(MODULO)
    assert cliente.prompts == ["PROMPT-JS src/suma.js humo=False"]
    assert any("trivial en JS" in d for d in planner.descartados)
    return contrato


def test_el_planner_usa_las_reglas_y_el_lenguaje_del_adaptador(adaptador) -> None:
    contrato = _contrato(adaptador)

    assert contrato["version"] == "3"
    assert contrato["lenguaje"] == "javascript"
    assert contrato["framework_pruebas"] == "vitest"
    assert [c["id"] for c in contrato["casos"]] == ["suma_normal"]
    contracts.validar(contracts.PLANNER_V3, contrato)


def test_el_generator_usa_el_prompt_y_la_sintaxis_del_adaptador(adaptador) -> None:
    contrato = _contrato(adaptador)
    cliente = ClienteGrabado("```js\nexpect(suma(2, 2)).toBe(4);\n```")

    generado = GeneratorAgent(cliente, TokenTracker()).generar(contrato, 2, "falló")

    assert cliente.prompts == ["GENERAR-JS suma intento=2 falló"]
    assert generado["lenguaje"] == "javascript"
    assert generado["framework_pruebas"] == "vitest"
    assert generado["codigo"] == "expect(suma(2, 2)).toBe(4);\n"
    contracts.validar(contracts.GENERATED_TEST_V2, generado)

    malo = GeneratorAgent(ClienteGrabado("console.log(1)"), TokenTracker())
    with pytest.raises(ErrorRespuestaGenerator, match="JavaScript inválido: falta"):
        malo.generar(contrato, 1, None)


def test_el_reviewer_ejecuta_con_el_adaptador_del_contrato(
    adaptador, tmp_path: Path
) -> None:
    contrato = _contrato(adaptador)
    test = contracts.generated_test_para(contrato, 1, "expect(suma(2, 2)).toBe(4);\n")
    vistos: dict[str, Any] = {}

    def ejecutor(imagen, proyecto, tests, modulo):
        vistos["archivos"] = sorted(p.name for p in Path(tests).iterdir())
        vistos["modulo"] = modulo
        return ResultadoSandbox(0, "ok", "", junit_xml="<x/>", duracion_s=0.1)

    reviewer = ReviewerAgent(TokenTracker(), tmp_path, "img", ejecutor=ejecutor)
    revision = reviewer.revisar(contrato, test, None)

    assert revision["decision"] == "accept"
    assert vistos == {"archivos": ["suma.test.js"], "modulo": "src/suma.js"}
    entorno = revision["ejecucion"]["entorno"]
    assert entorno["comando"] == "vitest run --coverage src/suma.js vitest"
    assert revision["ejecucion"]["duracion_pytest_s"] == 0.5  # del adaptador


def test_el_reviewer_aplica_el_oraculo_y_la_clasificacion_del_adaptador(
    adaptador, tmp_path: Path
) -> None:
    contrato = _contrato(adaptador)
    reviewer = ReviewerAgent(
        TokenTracker(),
        tmp_path,
        "img",
        ejecutor=lambda *a: ResultadoSandbox(1, "AssertionError: 5 != 4", ""),
    )

    sin_oraculo = contracts.generated_test_para(contrato, 1, "expect(1).toBe(1);\n")
    assert reviewer.revisar(contrato, sin_oraculo, None)["feedback"] == (
        "Oráculo inválido: falta toBe(4)"
    )

    bueno = contracts.generated_test_para(contrato, 2, "expect(suma(2,2)).toBe(4);\n")
    revision = reviewer.revisar(contrato, bueno, sin_oraculo)
    assert revision["decision"] == "bug_detectado"
    assert revision["tipo_fallo"] == "bug_codigo"


@pytest.mark.parametrize(
    "operacion, argumentos",
    [
        ("reglas_planificacion", ()),
        ("reglas_revision", ()),
        ("prompt_generator", ({}, 1, None, None)),
        ("huellas_de_archivo", ("", "a.ts")),
        ("funciones_de_modulo", (Path("."), "a.ts")),
        ("ejecutar_mutacion", ()),
    ],
)
def test_un_adaptador_en_desarrollo_no_implementa_lo_de_los_agentes(
    operacion, argumentos
) -> None:
    adaptador = REGISTRO.adaptador_para("typescript")

    assert adaptador.completo is False
    with pytest.raises(NoImplementado, match=operacion):
        getattr(adaptador, operacion)(*argumentos)


def test_agents_y_orchestrator_no_importan_lo_especifico_de_python() -> None:
    """Lo de Python vive en `qagent.lenguajes` (ADR-007); los agentes no lo importan."""
    raiz = Path(__file__).resolve().parents[2] / "src" / "qagent"
    prohibidos = (
        "import ast",
        "from qagent.analysis import arbol_ts",
        "from qagent.analysis import comparar_aserciones",
        "from qagent.analysis.analyzer import analizar_proyecto",
        "from qagent.analysis.contexto",
        "comando_pytest",
        "parsear_junit",
        "from qagent.lenguajes.python",
        "PythonAdapter",
    )
    archivos = [
        raiz / "agents" / "planner.py",
        raiz / "agents" / "generator.py",
        raiz / "agents" / "reviewer.py",
        *sorted((raiz / "orchestrator").glob("*.py")),
    ]
    for archivo in archivos:
        texto = archivo.read_text(encoding="utf-8")
        for prohibido in prohibidos:
            assert prohibido not in texto, f"{archivo.name}: {prohibido}"
