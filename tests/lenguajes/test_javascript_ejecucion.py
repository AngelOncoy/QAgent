"""Pruebas de ejecución y revisión de JavaScript y TypeScript (EP-11a, parte 3).

Sin Docker ni red: interpreta reportes grabados (JUnit XML y JSON) y cobertura
coverage-v8 (Istanbul), prueba el comando de Vitest, la clasificación de salida,
el rango de objetivo y las decisiones del Reviewer (accept, bug_detectado, reintentos,
límite de 3 intentos y corte por hash repetido), así como la presencia del lenguaje y
las 5 métricas en results.json y el informe exportado.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from qagent import contracts
from qagent.agents.reviewer import ReviewerAgent
from qagent.lenguajes import JavaScriptAdapter, TypeScriptAdapter
from qagent.lenguajes.javascript_cobertura import (
    interpretar_cobertura_v8,
    leer_cobertura_v8,
)
from qagent.lenguajes.javascript_ejecucion import (
    variables_node,
)
from qagent.lenguajes.javascript_junit import interpretar_resultados_vitest
from qagent.lenguajes.javascript_revision import (
    clasificar_salida_vitest,
    rango_de_objetivo_js,
)
from qagent.llm import TokenTracker
from qagent.sandbox import LimitesSandbox, ResultadoSandbox
from qagent.sandbox.informe_pytest import JUnitInvalido
from qagent.sandbox.modelos import IMAGEN_NODE
from qagent.storage.exportar_informe import exportar_informe
from qagent.storage.registro import escribir_corrida
from qagent.storage.vista_ejecucion import vista_ejecucion

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "javascript"
BANCO_JS = Path(__file__).resolve().parents[2] / "bench" / "banco_mvp_js"


# --- Criterio 1: entorno_sandbox y comando_pruebas -----------------------------------


def test_entorno_sandbox_devuelve_imagen_node_y_carpetas() -> None:
    for adaptador in (JavaScriptAdapter(), TypeScriptAdapter()):
        entorno = adaptador.entorno_sandbox()
        assert entorno.imagen == IMAGEN_NODE
        assert "vitest" in entorno.paquetes_base
        assert "@vitest/coverage-v8" in entorno.paquetes_base
        assert entorno.dir_tests == "/work/tests"
        assert entorno.dir_salida == "/out"
        assert entorno.informe == "junit.xml"


def test_comando_pruebas_arma_comando_vitest_con_junit_y_coverage_v8() -> None:
    js = JavaScriptAdapter()
    ts = TypeScriptAdapter()

    cmd_js = js.comando_pruebas("src/personas.mjs", "vitest")
    cmd_ts = ts.comando_pruebas("src/precios.ts", "vitest")

    for cmd in (cmd_js, cmd_ts):
        assert cmd[0] == "vitest"
        assert cmd[1] == "run"
        assert "/work/tests" in cmd
        assert "--reporter=junit" in cmd
        assert "--outputFile=/out/junit.xml" in cmd
        assert "--coverage.enabled=true" in cmd
        assert "--coverage.provider=v8" in cmd
        assert "--coverage.reporter=json" in cmd
        assert "--coverage.reporter=json-summary" in cmd
        assert "--coverage.reportsDirectory=/out" in cmd
        assert "--no-color" in cmd
        # #171: raíz /work (proyecto y pruebas), sin escribir fuera de /tmp y /out.
        assert "--root=/work" in cmd
        assert "--fsModuleCache=false" in cmd
        assert "--coverage.clean=false" in cmd
        assert "--coverage.reportOnFailure=true" in cmd

    assert "--coverage.include=proyecto/src/personas.mjs" in cmd_js
    assert "--coverage.include=proyecto/src/precios.ts" in cmd_ts


def test_variables_pruebas_incluye_node_env_y_no_color() -> None:
    vars_node = variables_node()
    assert vars_node.get("NODE_ENV") == "test"
    assert vars_node.get("NO_COLOR") == "1"
    assert vars_node.get("HOME") == "/tmp"


# --- Criterio 3: interpretar_resultados (JUnit XML y JSON) ---------------------------


def test_interpretar_resultados_junit_xml_extrae_casos_esperado_obtenido_y_error() -> (
    None
):
    ruta_xml = FIXTURES_DIR / "vitest-report-controlado.xml"
    contenido = ruta_xml.read_text(encoding="utf-8")

    informe = interpretar_resultados_vitest(contenido)

    assert informe["total"] == 4
    assert informe["pasaron"] == 1
    assert informe["fallaron"] == 1
    assert informe["errores"] == 1
    assert informe["omitidos"] == 1
    assert informe["duracion_s"] == 0.150

    fallo = next(c for c in informe["casos"] if c["resultado"] == "fallo")
    assert fallo["tipo_error"] == "AssertionError"
    assert fallo["esperado"] == "80"
    assert fallo["obtenido"] == "20"
    assert fallo["operador"] == "=="
    assert fallo["archivo"] == "generado.test.ts"
    assert fallo["linea"] == 8
    assert len(fallo["pila"]) >= 1

    paso = next(c for c in informe["casos"] if c["resultado"] == "paso")
    assert paso["esperado"] is None
    assert paso["obtenido"] is None

    error = next(c for c in informe["casos"] if c["resultado"] == "error")
    assert error["tipo_error"] == "TypeError"
    assert "Cannot read properties" in error["mensaje"]

    omitido = next(c for c in informe["casos"] if c["resultado"] == "omitido")
    assert omitido["resultado"] == "omitido"


def test_interpretar_resultados_json_extrae_casos_igual_que_junit() -> None:
    ruta_json = FIXTURES_DIR / "vitest-report-json.json"
    contenido = ruta_json.read_text(encoding="utf-8")

    informe = interpretar_resultados_vitest(contenido)

    assert informe["total"] == 4
    assert informe["pasaron"] == 1
    assert informe["fallaron"] == 2
    assert informe["omitidos"] == 1

    fallo = next(
        c
        for c in informe["casos"]
        if c["nombre"] == "calcularDescuento > caso 1: descuento del 20%"
    )
    assert fallo["resultado"] == "fallo"
    assert fallo["tipo_error"] == "AssertionError"
    assert fallo["esperado"] == "80"
    assert fallo["obtenido"] == "20"
    assert fallo["archivo"] == "generado.test.ts"
    assert fallo["linea"] == 8


def test_interpretar_resultados_informe_vacio_o_invalido_lanza_error() -> None:
    with pytest.raises(JUnitInvalido, match="vacío"):
        interpretar_resultados_vitest("")

    with pytest.raises(JUnitInvalido):
        interpretar_resultados_vitest("not an xml or json")


# --- Criterio 4: leer_cobertura (coverage-v8) ---------------------------------------


def test_leer_cobertura_v8_desde_archivo_grabado(tmp_path: Path) -> None:
    fixture_cov = FIXTURES_DIR / "coverage-final.json"
    (tmp_path / "coverage-final.json").write_text(
        fixture_cov.read_text(encoding="utf-8"), encoding="utf-8"
    )

    cobertura = leer_cobertura_v8(tmp_path)
    assert cobertura is not None
    assert "files" in cobertura
    assert "totals" in cobertura
    assert "src/precios.ts" in cobertura["files"]

    datos_precios = cobertura["files"]["src/precios.ts"]
    assert 13 in datos_precios["executed_lines"]
    assert 14 in datos_precios["executed_lines"]
    assert 15 in datos_precios["missing_lines"]
    assert 18 in datos_precios["missing_lines"]
    assert 21 in datos_precios["executed_lines"]

    # Ramas: 2 if con una rama ejecutada y otra faltante cada uno
    assert len(datos_precios["executed_branches"]) == 2
    assert len(datos_precios["missing_branches"]) == 2

    # Totales
    totals = cobertura["totals"]
    assert totals["covered_lines"] == 5
    assert totals["missing_lines"] == 2
    assert totals["percent_covered"] > 70.0
    assert totals["covered_branches"] == 2
    assert totals["missing_branches"] == 2
    assert totals["percent_branches_covered"] == 50.0


def test_cobertura_v8_interpreta_datos_directos() -> None:
    dummy_v8 = {
        "/work/proyecto/src/util.js": {
            "path": "/work/proyecto/src/util.js",
            "statementMap": {
                "0": {"start": {"line": 1}},
                "1": {"start": {"line": 2}},
                "2": {"start": {"line": 3}},
            },
            "s": {"0": 1, "1": 1, "2": 0},
            "branchMap": {
                "0": {"line": 2},
            },
            "b": {"0": [1, 0]},
        }
    }
    resultado = interpretar_cobertura_v8(dummy_v8)
    assert resultado is not None
    assert "src/util.js" in resultado["files"]
    util = resultado["files"]["src/util.js"]
    assert util["executed_lines"] == [1, 2]
    assert util["missing_lines"] == [3]
    assert util["executed_branches"] == [[2, 1]]
    assert util["missing_branches"] == [[2, -2]]
    assert util["summary"]["percent_branches_covered"] == 50.0


# --- Criterio 5: Decisiones del Reviewer y reglas de salida ---------------------------


def test_rango_de_objetivo_js_y_ts() -> None:
    rango_desc = rango_de_objetivo_js(BANCO_JS, "src/precios.ts", "calcularDescuento")
    assert rango_desc is not None
    inicio, fin = rango_desc
    assert inicio == 13
    assert fin == 23

    rango_edad = rango_de_objetivo_js(BANCO_JS, "src/personas.mjs", "clasificarEdad")
    assert rango_edad is not None
    assert rango_edad[0] == 17
    assert rango_edad[1] == 28

    rango_palindromo = rango_de_objetivo_js(BANCO_JS, "src/texto.ts", "esPalindromo")
    assert rango_palindromo is not None
    assert rango_palindromo[0] == 11
    assert rango_palindromo[1] == 14

    rango_metodo = rango_de_objetivo_js(BANCO_JS, "src/texto.ts", "Formateador.moneda")
    assert rango_metodo is not None
    assert rango_metodo[0] == 38
    assert rango_metodo[1] == 40


def test_clasificar_salida_vitest_distingue_tipos() -> None:
    salida_asercion = "FAIL ...\nAssertionError: expected 20 to be 80\n"
    c_asercion = clasificar_salida_vitest(salida_asercion, {}, BANCO_JS)
    assert c_asercion is not None
    assert c_asercion.tipo == "fallo_asercion"

    salida_error_test = "SyntaxError: Unexpected token '{' at line 5"
    c_test = clasificar_salida_vitest(salida_error_test, {}, BANCO_JS)
    assert c_test is not None
    assert c_test.tipo == "error_test"

    salida_entorno = "Error: connect ECONNREFUSED 127.0.0.1:5432"
    c_entorno = clasificar_salida_vitest(salida_entorno, {}, BANCO_JS)
    assert c_entorno is not None
    assert c_entorno.tipo == "entorno"


def test_reviewer_decide_accept_en_prueba_aprobada(tmp_path: Path) -> None:
    contrato = {
        "version": "3",
        "lenguaje": "typescript",
        "framework_pruebas": "vitest",
        "modulo": "src/texto.ts",
        "huella": "0" * 64,
        "tipo": "funcion",
        "objetivo": "esPalindromo",
        "firma": "esPalindromo(texto: string): boolean",
        "critical": False,
        "casos": [
            {
                "id": "caso_1",
                "entrada": ["Anita lava la tina"],
                "valor_esperado": True,
                "origen": "docstring",
            }
        ],
    }
    codigo_test = (
        'import { describe, it, expect } from "vitest";\n'
        'import { esPalindromo } from "../proyecto/src/texto";\n'
        'describe("esPalindromo", () => {\n'
        '  it("caso 1", () => {\n'
        '    expect(esPalindromo("Anita lava la tina")).toBe(true);\n'
        "  });\n"
        "});\n"
    )

    def ejecutor_ok(img, raiz, tests, cov):
        res = ResultadoSandbox(
            exit_code=0,
            stdout="✓ esPalindromo > caso 1 (2ms)\n",
            stderr="",
            limites=LimitesSandbox(cpus=2.0, memoria="2g", timeout_s=120),
            duracion_s=0.1,
        )
        res.junit_xml = (
            '<testsuites tests="1" failures="0">'
            '<testsuite name="tests/generado.test.ts" tests="1" failures="0">'
            '<testcase name="esPalindromo &gt; caso 1"/>'
            "</testsuite></testsuites>"
        )
        res.coverage = {
            "files": {
                "src/texto.ts": {
                    "executed_lines": [11, 12, 13],
                    "missing_lines": [],
                    "executed_branches": [],
                    "missing_branches": [],
                }
            },
            "totals": {
                "percent_covered": 100.0,
                "num_branches": 0,
                "covered_branches": 0,
            },
        }
        return res

    tracker = TokenTracker()
    reviewer = ReviewerAgent(
        tracker,
        BANCO_JS,
        IMAGEN_NODE,
        ejecutor=ejecutor_ok,
        limites=LimitesSandbox(cpus=2.0, memoria="2g", timeout_s=120),
    )

    revision = reviewer.revisar(contrato, {"codigo": codigo_test, "intento": 1}, None)
    assert revision["decision"] == "accept"
    assert revision["estado_sandbox"] == "ok"
    assert revision["cobertura"]["lineas"] == 100.0
    assert revision["ejecucion"]["totales"]["pasaron"] == 1


def test_reviewer_decide_bug_detectado_en_fallo_de_asercion() -> None:
    contrato = {
        "version": "3",
        "lenguaje": "typescript",
        "framework_pruebas": "vitest",
        "modulo": "src/precios.ts",
        "huella": "0" * 64,
        "tipo": "funcion",
        "objetivo": "calcularDescuento",
        "firma": "calcularDescuento(precio: number, porcentaje: number): number",
        "critical": True,
        "casos": [
            {
                "id": "caso_1",
                "entrada": {"precio": 100, "porcentaje": 20},
                "valor_esperado": 80,
                "origen": "docstring",
            }
        ],
    }
    codigo_test = (
        'import { describe, it, expect } from "vitest";\n'
        'import { calcularDescuento } from "../proyecto/src/precios";\n'
        'describe("calcularDescuento", () => {\n'
        '  it("caso 1", () => {\n'
        "    expect(calcularDescuento(100, 20)).toBe(80);\n"
        "  });\n"
        "});\n"
    )

    def ejecutor_bug(img, raiz, tests, cov):
        res = ResultadoSandbox(
            exit_code=1,
            stdout="FAIL tests/generado.test.ts\nAssertionError: expected 20 to be 80\n",
            stderr="",
            limites=LimitesSandbox(cpus=2.0, memoria="2g", timeout_s=120),
            duracion_s=0.1,
        )
        res.junit_xml = (
            '<testsuites tests="1" failures="1">'
            '<testsuite name="tests/generado.test.ts" tests="1" failures="1">'
            '<testcase name="calcularDescuento &gt; caso 1">'
            '<failure message="AssertionError: expected 20 to be 80">at /work/tests/generado.test.ts:8:25</failure>'
            "</testcase></testsuite></testsuites>"
        )
        res.coverage = {
            "files": {
                "src/precios.ts": {
                    "executed_lines": [13, 14, 17, 21, 22],
                    "missing_lines": [15, 18],
                    "executed_branches": [[14, 1], [17, 1]],
                    "missing_branches": [[14, 2], [17, 2]],
                }
            },
            "totals": {
                "percent_covered": 71.43,
                "num_branches": 4,
                "covered_branches": 2,
            },
        }
        return res

    tracker = TokenTracker()
    reviewer = ReviewerAgent(
        tracker,
        BANCO_JS,
        IMAGEN_NODE,
        ejecutor=ejecutor_bug,
    )

    revision = reviewer.revisar(contrato, {"codigo": codigo_test, "intento": 1}, None)
    assert revision["decision"] == "bug_detectado"
    assert revision["tipo_fallo"] == "bug_codigo"
    assert revision["estado_sandbox"] == "fallo"
    assert revision["hash_error"] is not None


def test_reviewer_reintenta_error_test_y_corta_en_intento_3() -> None:
    contrato = {
        "version": "3",
        "lenguaje": "typescript",
        "framework_pruebas": "vitest",
        "modulo": "src/precios.ts",
        "huella": "0" * 64,
        "tipo": "funcion",
        "objetivo": "calcularDescuento",
        "firma": "calcularDescuento(precio: number, porcentaje: number): number",
        "critical": True,
        "casos": [
            {
                "id": "caso_1",
                "entrada": {"precio": 100, "porcentaje": 20},
                "valor_esperado": 80,
                "origen": "docstring",
            }
        ],
    }
    codigo_test = (
        'import { describe, it, expect } from "vitest";\n'
        'import { calcularDescuento } from "../proyecto/src/precios";\n'
        'describe("calcularDescuento", () => {\n'
        '  it("caso 1", () => {\n'
        "    expect(calcularDescuento(100, 20)).toBe(80);\n"
        "  });\n"
        "});\n"
    )

    contador = {"intento": 0}

    def ejecutor_error_tecnico(img, raiz, tests, cov):
        contador["intento"] += 1
        res = ResultadoSandbox(
            exit_code=1,
            stdout=f"Error: Cannot find module './dep_{contador['intento']}'",
            stderr="",
            limites=LimitesSandbox(cpus=2.0, memoria="2g", timeout_s=120),
            duracion_s=0.1,
        )
        res.junit_xml = None
        res.coverage = None
        return res

    tracker = TokenTracker()
    reviewer = ReviewerAgent(
        tracker,
        BANCO_JS,
        IMAGEN_NODE,
        ejecutor=ejecutor_error_tecnico,
    )

    # Intento 1: reintento
    rev1 = reviewer.revisar(contrato, {"codigo": codigo_test, "intento": 1}, None)
    assert rev1["decision"] == "retry"
    assert rev1["tipo_fallo"] == "error_test"

    # Intento 2: reintento
    rev2 = reviewer.revisar(
        contrato, {"codigo": codigo_test, "intento": 2}, {"codigo": codigo_test}
    )
    assert rev2["decision"] == "retry"

    # Intento 3: estancada (máximo 3 intentos)
    rev3 = reviewer.revisar(
        contrato, {"codigo": codigo_test, "intento": 3}, {"codigo": codigo_test}
    )
    assert rev3["decision"] == "stalled"


# --- Criterio 6: results.json e informe con 5 métricas y columna lenguaje -------------


def test_results_json_e_informe_contienen_lenguaje_y_5_metricas(
    tmp_path: Path,
) -> None:
    modulo = "src/precios.ts"
    objetivo = "calcularDescuento"
    contrato = {
        "version": "3",
        "lenguaje": "typescript",
        "framework_pruebas": "vitest",
        "modulo": modulo,
        "huella": "0" * 64,
        "tipo": "funcion",
        "objetivo": objetivo,
        "firma": "calcularDescuento(precio: number, porcentaje: number): number",
        "critical": True,
        "casos": [
            {
                "id": "c1",
                "entrada": {"precio": 100, "porcentaje": 20},
                "valor_esperado": 80,
                "origen": "docstring",
            }
        ],
    }

    class MockObjetivo:
        def __init__(self):
            self.modulo = modulo
            self.objetivo = objetivo
            self.decision = "bug_detectado"
            self.intentos = 1
            self.cobertura = {"lineas": 71.43, "ramas": 50.0}
            self.mutation_score = None
            self.contrato = contrato
            self.critical = True
            self.motivo_estancado = None
            self.motivo_sin_veredicto = None
            self.detalle_error_planner = None
            self.lenguaje = "typescript"
            self.reutilizada = False
            self.motivo_regresion = None
            self.laundering_detectado = False
            self.duracion_s = 0.5
            self.inicio = None
            self.fin = None
            self.duracion_generacion_s = 0.1
            self.duracion_revision_s = 0.2
            self.duracion_sandbox_s = 0.1
            self.duracion_pytest_s = 0.1
            self.tiempos_intentos = []
            self.mutacion = None
            self.revisiones = [
                {
                    "intento": 1,
                    "estado_sandbox": "fallo",
                    "cobertura": self.cobertura,
                    "laundering_detectado": False,
                    "tipo_fallo": "bug_codigo",
                    "hash_error": "h123",
                    "decision": "bug_detectado",
                    "feedback": "AssertionError",
                    "ejecucion": {
                        "totales": {
                            "total": 1,
                            "pasaron": 0,
                            "fallaron": 1,
                            "errores": 0,
                            "omitidos": 0,
                        },
                        "casos": [
                            {
                                "nombre": "calcularDescuento > c1",
                                "resultado": "fallo",
                                "esperado": "80",
                                "obtenido": "20",
                                "operador": "==",
                            }
                        ],
                        "entorno": {"imagen": IMAGEN_NODE, "comando": "vitest run"},
                    },
                }
            ]
            self.codigo = 'it("c1", () => expect(80).toBe(80));'

    class MockResultado:
        def __init__(self):
            self.modulo = modulo
            self.objetivos = [MockObjetivo()]
            self.plan = [contrato]
            self.estado_final = MagicMock()
            self.estado_final.value = "terminada"
            self.motivo_fallo = None

    tracker = TokenTracker()
    from qagent.llm import cargar_precios

    rutas = escribir_corrida(
        tmp_path,
        [MockResultado()],
        tracker,
        cargar_precios(),
        "estandar",
        run_id="20261106-120000-abcd",
    )

    assert rutas.results.is_file()
    results_path = rutas.results

    results_data = json.loads(results_path.read_text(encoding="utf-8"))
    contracts.validar(contracts.RUN_LOG, results_data)

    [prueba_res] = results_data["objetivos"]

    # Columna lenguaje
    assert prueba_res["lenguaje"] == "typescript"

    vista = vista_ejecucion(results_data)
    assert vista["modulos"][0]["pruebas"][0]["lenguaje"] == "typescript"

    # 5 métricas
    metricas = prueba_res["metricas"]
    assert "paso" in metricas
    assert metricas["cobertura_lineas"] == 71.43
    assert metricas["cobertura_ramas"] == 50.0
    assert metricas["iteraciones"] == 1
    assert "tokens_por_agente" in metricas

    # Informe exportado (Markdown y HTML)
    for formato in ("md", "html"):
        res_exp = exportar_informe(
            tmp_path, run_id="20261106-120000-abcd", formato=formato
        )
        assert res_exp["ok"]
        texto = Path(res_exp["ruta"]).read_text(encoding="utf-8")
        assert "typescript" in texto.lower()
        assert "calcularDescuento" in texto
