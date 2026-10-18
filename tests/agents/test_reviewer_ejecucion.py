"""El veredicto del Reviewer incluye lo que pasó en el sandbox (EN-17).

Se usan grabaciones reales de pytest (`tests/sandbox/grabaciones/`), sin Docker.
"""

from __future__ import annotations

from pathlib import Path

from qagent import contracts
from qagent.agents.reviewer import ReviewerAgent
from qagent.llm import TokenTracker
from qagent.sandbox import LimitesSandbox, ResultadoSandbox, ejecutar_pruebas
from tests.agents.test_reviewer import CODIGO_VALIDO, CONTRATO, EjecutorGrabado

GRABACIONES = Path(__file__).resolve().parents[1] / "sandbox" / "grabaciones"
TEST = {
    "version": "1",
    "objetivo": "duplicar",
    "intento": 1,
    "codigo": CODIGO_VALIDO,
    "casos_cubiertos": ["duplica_positivo"],
}


def _grabado(nombre: str, exit_code: int, coverage: dict | None = None):
    return ResultadoSandbox(
        exit_code=exit_code,
        stdout=(GRABACIONES / f"{nombre}.stdout.txt").read_text(encoding="utf-8"),
        stderr="",
        coverage=coverage,
        duracion_s=0.42,
        junit_xml=(GRABACIONES / f"{nombre}.junit.xml").read_text(encoding="utf-8"),
    )


def _revisar(tmp_path: Path, resultado: ResultadoSandbox, calculadora: str = ""):
    if calculadora:
        (tmp_path / "calculadora.py").write_text(calculadora, encoding="utf-8")
    reviewer = ReviewerAgent(
        TokenTracker(), tmp_path, "imagen-prueba", ejecutor=EjecutorGrabado(resultado)
    )
    return reviewer.revisar(CONTRATO, dict(TEST), None)


def test_un_bug_trae_los_casos_con_donde_y_que_fallo(tmp_path: Path) -> None:
    revision = _revisar(tmp_path, _grabado("falla_assert", 1))

    assert contracts.es_valido(contracts.REVIEW_RESULT, revision)
    assert revision["decision"] == "bug_detectado"
    ejecucion = revision["ejecucion"]
    assert ejecucion["exit_code"] == 1
    assert ejecucion["duracion_s"] == 0.42
    assert ejecucion["totales"] == {
        "total": 2,
        "pasaron": 1,
        "fallaron": 1,
        "errores": 0,
        "omitidos": 0,
    }
    fallo = next(c for c in ejecucion["casos"] if c["resultado"] == "fallo")
    assert (fallo["archivo"], fallo["linea"]) == ("tests/test_generado.py", 4)
    assert (fallo["obtenido"], fallo["esperado"]) == ("12", "8")
    assert ejecucion["codigo_test"] == CODIGO_VALIDO
    assert "1 failed, 1 passed" in ejecucion["salida"]


def test_el_entorno_sale_de_la_cabecera_de_pytest(tmp_path: Path) -> None:
    entorno = _revisar(tmp_path, _grabado("falla_assert", 1))["ejecucion"]["entorno"]

    assert entorno["imagen"] == "imagen-prueba"
    assert entorno["python"] == "3.11.9"
    assert entorno["pytest"] == "9.1.1"
    assert entorno["plataforma"] == "linux"
    assert "--junitxml=/out/junit.xml" in entorno["comando"]
    assert entorno["limites"] == {"cpus": 4.0, "memoria": "3g", "timeout_s": 120}


def test_un_test_aprobado_tambien_deja_sus_casos(tmp_path: Path) -> None:
    revision = _revisar(tmp_path, _grabado("todo_pasa", 0))

    assert revision["decision"] == "accept"
    assert revision["ejecucion"]["totales"]["pasaron"] == 2
    assert all(c["resultado"] == "paso" for c in revision["ejecucion"]["casos"])


def test_sin_junit_la_salida_sigue_disponible(tmp_path: Path) -> None:
    resultado = ResultadoSandbox(1, "assert 1 == 2\n", "", duracion_s=0.1)

    revision = _revisar(tmp_path, resultado)

    assert contracts.es_valido(contracts.REVIEW_RESULT, revision)
    assert revision["ejecucion"]["casos"] == []
    assert "assert 1 == 2" in revision["ejecucion"]["salida"]


def test_un_junit_corrupto_no_rompe_la_revision(tmp_path: Path) -> None:
    resultado = ResultadoSandbox(1, "assert 1 == 2\n", "", junit_xml="<testsuites>")

    revision = _revisar(tmp_path, resultado)

    assert contracts.es_valido(contracts.REVIEW_RESULT, revision)
    assert revision["ejecucion"]["casos"] == []
    assert "assert 1 == 2" in revision["ejecucion"]["salida"]


def test_un_test_que_no_llega_al_sandbox_no_trae_ejecucion(tmp_path: Path) -> None:
    test = dict(TEST, codigo="def test_x(:\n    pass\n")
    reviewer = ReviewerAgent(
        TokenTracker(),
        tmp_path,
        "imagen-prueba",
        ejecutor=EjecutorGrabado(_grabado("todo_pasa", 0)),
    )

    revision = reviewer.revisar(CONTRATO, test, None)

    assert "ejecucion" not in revision


def test_las_lineas_sin_cubrir_salen_del_coverage(tmp_path: Path) -> None:
    coverage = {
        "files": {
            "calculadora.py": {
                "executed_lines": [2],
                "missing_lines": [3, 9],
                "executed_branches": [],
                "missing_branches": [],
            }
        },
        "totals": {"percent_covered": 33.0},
    }
    fuente = "def duplicar(x):\n    if x < 0:\n        return 0\n    return x * 2\n"

    revision = _revisar(tmp_path, _grabado("falla_assert", 1, coverage), fuente)

    assert revision["ejecucion"]["lineas_sin_cubrir"] == [3]


def test_el_reviewer_aplica_los_limites_de_config_al_sandbox_real(
    tmp_path: Path,
) -> None:
    limites = LimitesSandbox(cpus=2.0, memoria="1g", timeout_s=30)
    reviewer = ReviewerAgent(TokenTracker(), tmp_path, "img", limites=limites)

    assert reviewer.ejecutor.func is ejecutar_pruebas
    assert reviewer.ejecutor.keywords == {"limites": limites}


def test_el_informe_muestra_los_limites_que_de_verdad_se_aplicaron(
    tmp_path: Path,
) -> None:
    resultado = _grabado("falla_assert", 1)
    resultado.limites = LimitesSandbox(cpus=2.0, memoria="3g", timeout_s=120)

    entorno = _revisar(tmp_path, resultado)["ejecucion"]["entorno"]

    assert entorno["limites"] == {"cpus": 2.0, "memoria": "3g", "timeout_s": 120}
