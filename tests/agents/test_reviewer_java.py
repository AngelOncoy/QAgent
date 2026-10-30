"""Reviewer y orquestación Java con XML grabado y entradas controladas (#182)."""

import json
from pathlib import Path

import pytest

from qagent import contracts
from qagent.lenguajes import JavaAdapter
from qagent.lenguajes.base import NoImplementado
from qagent.lenguajes.java_cobertura import interpretar_jacoco
from qagent.lenguajes.java_revision import clasificar_java
from qagent.llm import cargar_precios
from qagent.sandbox import ResultadoSandbox
from qagent.storage.exportar_informe import exportar_informe
from qagent.storage.registro import escribir_corrida
from qagent.storage.vista_ejecucion import vista_ejecucion
from qagent.storage.vista_reporte import vista_reporte
from tests.agents.java_controlado import RAIZ, preparar_corrida

FIXTURES = RAIZ / "tests/fixtures/java"


def resultado_grabado(**cambios):
    """Resultado real guardado del promedio; no ejecuta fuentes del banco."""
    datos = {
        "exit_code": 1,
        "stdout": "QAGENT_JAVA_ETAPA=ejecucion",
        "stderr": "",
        "junit_xml": (FIXTURES / "junit5-sandbox-promedio.xml").read_text(
            encoding="utf-8"
        ),
        "coverage": interpretar_jacoco(
            (FIXTURES / "jacoco-sandbox-promedio.xml").read_text(encoding="utf-8")
        ),
    }
    datos.update(cambios)
    return ResultadoSandbox(**datos)


@pytest.mark.parametrize(
    ("cambios", "tipo", "motivo"),
    [
        ({}, "fallo_asercion", None),
        (
            {"stdout": "QAGENT_JAVA_ETAPA=proyecto", "junit_xml": None},
            "entorno",
            "error_compilacion_proyecto",
        ),
        ({"stdout": "QAGENT_JAVA_ETAPA=prueba", "junit_xml": None}, "error_test", None),
        ({"stdout": "QAGENT_JAVA_ETAPA=cobertura"}, "entorno", "error_cobertura"),
        ({"timed_out": True}, "entorno", "timeout_sandbox"),
        ({"oom_killed": True}, "entorno", "memoria_sandbox"),
        ({"junit_xml": None}, "entorno", "informe_pruebas_invalido"),
        (
            {"junit_xml": "<testsuite/>", "exit_code": 0},
            "entorno",
            "informe_pruebas_invalido",
        ),
        (
            {
                "junit_xml": '<testsuite><testcase name="x"><skipped/></testcase></testsuite>',
                "exit_code": 0,
            },
            "entorno",
            "pruebas_no_ejecutadas",
        ),
        ({"exit_code": 0}, "entorno", "salida_runner_incoherente"),
        (
            {
                "junit_xml": '<testsuite><testcase name="x"><error type="NullPointerException"/></testcase></testsuite>'
            },
            "entorno",
            "error_ejecucion_pruebas",
        ),
        (
            {
                "junit_xml": '<testsuite><testcase name="x"><failure type="Desconocido"/></testcase></testsuite>'
            },
            "entorno",
            "fallo_junit_no_clasificado",
        ),
    ],
)
def test_clasificacion_conservadora(cambios, tipo, motivo):
    """Errores técnicos, omisiones y XML incoherente nunca se presentan como bugs."""
    clasificacion = clasificar_java(resultado_grabado(**cambios))
    assert (clasificacion.tipo, clasificacion.motivo_sin_veredicto) == (tipo, motivo)


def test_junit_correcto_con_exit_cero_permite_aceptar():
    """Solo una prueba ejecutada sin fallos con salida cero permite aceptación."""
    xml = '<testsuite><testcase name="x"/></testsuite>'
    assert clasificar_java(resultado_grabado(junit_xml=xml, exit_code=0)) is None
    assert (
        clasificar_java(resultado_grabado(junit_xml=xml)).motivo_sin_veredicto
        == "salida_runner_incoherente"
    )


def _modulo_promedio(proyecto):
    """Un objetivo concreto del AST real mantiene su firma, huella y Javadoc."""
    modulo = next(
        m
        for m in JavaAdapter().analizar(proyecto)["modulos"]
        if "Defectuoso" in m["ruta"]
    )
    return {
        **modulo,
        "funciones": [
            f for f in modulo["funciones"] if f["nombre"].endswith("calcularPromedio")
        ],
    }


def test_reviewer_detecta_bug_con_xml_real_y_cobertura_exacta(monkeypatch):
    """El Reviewer usa el contrato y reporta 2.5 frente a 2.0, con métricas del método."""
    banco = RAIZ / "bench_java"
    orquestador, _, _ = preparar_corrida(
        monkeypatch, banco, lambda *args: resultado_grabado()
    )
    resultado = orquestador.ejecutar(_modulo_promedio(banco))
    [objetivo] = resultado.objetivos
    assert objetivo.decision == "bug_detectado", resultado.motivo_fallo
    assert objetivo.intentos == 1
    assert objetivo.cobertura == {"lineas": 100.0, "ramas": 100.0}
    [caso] = objetivo.revisiones[0]["ejecucion"]["casos"]
    assert (caso["esperado"], caso["obtenido"]) == ("2.5", "2.0")


@pytest.mark.parametrize(("repetir", "intentos"), [(False, 3), (True, 2)])
def test_reintentos_y_corte_por_hash_real(monkeypatch, repetir, intentos):
    """Compilación de prueba vuelve al Generator: máximo tres, dos si repite hash."""
    llamadas = []

    def ejecutar(*args):
        llamadas.append(1)
        detalle = (
            "simbolo_desconocido" if repetir else "simbolo_" + chr(64 + len(llamadas))
        )
        return resultado_grabado(
            stdout="QAGENT_JAVA_ETAPA=prueba\n" + detalle, junit_xml=None, coverage=None
        )

    banco = RAIZ / "bench_java"
    orquestador, _, generator = preparar_corrida(monkeypatch, banco, ejecutar)
    resultado = orquestador.ejecutar(_modulo_promedio(banco))
    [objetivo] = resultado.objetivos
    assert objetivo.decision == "stalled", resultado.motivo_fallo
    assert objetivo.intentos == len(llamadas) == intentos
    assert len(generator.feedbacks) == intentos
    assert all(generator.feedbacks[1:])


@pytest.mark.parametrize(
    "cambios",
    [
        {"stdout": "QAGENT_JAVA_ETAPA=proyecto", "junit_xml": None},
        {"timed_out": True},
        {"oom_killed": True},
    ],
)
def test_fallo_tecnico_sin_veredicto_se_guarda_sin_reintentar(
    monkeypatch, tmp_path: Path, cambios
):
    """El motivo técnico persiste en results.json y el contrato de revisión lo admite."""
    banco = RAIZ / "bench_java"
    orquestador, tracker, generator = preparar_corrida(
        monkeypatch, banco, lambda *args: resultado_grabado(**cambios)
    )
    resultado = orquestador.ejecutar(_modulo_promedio(banco))
    [objetivo] = resultado.objetivos
    assert objetivo.decision is None
    assert objetivo.motivo_sin_veredicto
    assert objetivo.intentos == len(generator.feedbacks) == 1
    revision = objetivo.revisiones[0]
    contracts.validar(contracts.REVIEW_RESULT, revision)
    rutas = escribir_corrida(tmp_path, resultado, tracker, cargar_precios(), "std")
    guardado = json.loads(rutas.results.read_text(encoding="utf-8"))
    assert (
        guardado["objetivos"][0]["motivo_sin_veredicto"]
        == objetivo.motivo_sin_veredicto
    )


def test_guardrail_y_disponibilidad_no_se_habilitan_por_182():
    """Java permanece incompleto y nunca acepta código libre sin el guardrail #184."""
    assert JavaAdapter().completo is False
    with pytest.raises(NoImplementado):
        JavaAdapter().reglas_revision().validar_oraculo({}, "class Test {}")


def test_resultados_e_informes_conservan_java_y_sus_metricas(monkeypatch, tmp_path):
    """El mismo XML real alimenta JSON, vistas y exportaciones Markdown/HTML/PDF."""
    banco = RAIZ / "bench_java"
    orquestador, tracker, _ = preparar_corrida(
        monkeypatch, banco, lambda *args: resultado_grabado()
    )
    resultado = orquestador.ejecutar(_modulo_promedio(banco))
    rutas = escribir_corrida(tmp_path, resultado, tracker, cargar_precios(), "std")
    results = json.loads(rutas.results.read_text(encoding="utf-8"))
    detalle = json.loads(rutas.detalle.read_text(encoding="utf-8"))
    vista = vista_ejecucion(results)
    assert vista["modulos"][0]["pruebas"][0]["lenguaje"] == "java"
    reporte = vista_reporte(results, detalle)
    assert reporte["funciones"][0]["lenguaje"] == "java"
    assert reporte["funciones"][0]["framework_pruebas"] == "junit5"
    assert results["objetivos"][0]["controles"]["sintaxis"] is True
    for formato in ("md", "html", "pdf"):
        exportado = exportar_informe(
            tmp_path, run_id=results["run_id"], formato=formato
        )
        assert exportado["ok"]
        archivo = Path(exportado["ruta"])
        assert archivo.stat().st_size > 0
        if formato != "pdf":
            texto = archivo.read_text(encoding="utf-8")
            assert "java" in texto.lower()
            assert "junit5" in texto
            assert "2.5" in texto and "2.0" in texto


def test_schema_rechaza_aceptacion_con_motivo_sin_veredicto():
    """El nuevo campo no puede combinarse con una aceptación ni con un bug."""
    from tests.orchestrator.fakes import veredicto

    for decision in ("accept", "bug_detectado"):
        with pytest.raises(contracts.ContratoInvalido):
            contracts.validar(
                contracts.REVIEW_RESULT,
                veredicto("x", 1, decision, motivo_sin_veredicto="error_tecnico"),
            )
