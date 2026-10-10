"""Pruebas del ReviewerAgent con el sandbox sustituido."""

from __future__ import annotations

from pathlib import Path

from pyagent import contracts
from pyagent.agents.reviewer import ReviewerAgent
from pyagent.llm import RespuestaLLM, TokenTracker
from pyagent.sandbox import ResultadoSandbox

CONTRATO = {
    "version": "2",
    "modulo": "calculadora.py",
    "huella": "a" * 64,
    "tipo": "funcion",
    "objetivo": "duplicar",
    "firma": "(x: int) -> int",
    "critical": False,
    "llama_a": [],
    "casos": [
        {
            "id": "duplica_positivo",
            "entrada": {"x": 2},
            "valor_esperado": 4,
            "origen": "docstring",
        }
    ],
}

CODIGO_VALIDO = """\
from calculadora import duplicar


def test_duplicar():
    assert duplicar(2) == 4
"""


class EjecutorGrabado:
    """Sustituye Docker y devuelve un ResultadoSandbox fijo."""

    def __init__(self, resultado: ResultadoSandbox) -> None:
        self.resultado = resultado
        self.llamadas = 0

    def __call__(
        self,
        imagen: str,
        ruta_proyecto: Path,
        ruta_tests: Path,
        modulo_cov: str,
    ) -> ResultadoSandbox:
        self.llamadas += 1
        assert imagen == "imagen-prueba"
        assert ruta_tests.joinpath("test_generado.py").exists()
        assert modulo_cov == "calculadora"
        return self.resultado


class ClienteClasificador:
    """Cliente simulado para un fallo que necesita clasificación semántica."""

    def __init__(self, decision: str) -> None:
        self.decision = decision
        self.prompts: list[str] = []

    def generar(self, prompt: str, rol: str = "generator") -> RespuestaLLM:
        self.prompts.append(prompt)
        return RespuestaLLM(
            contenido=self.decision,
            tokens_entrada=20,
            tokens_salida=2,
            costo_usd=0.0,
            modelo="reviewer-prueba",
        )


def sandbox(
    exit_code: int,
    *,
    stdout: str = "",
    stderr: str = "",
    coverage: dict | None = None,
    timed_out: bool = False,
    oom_killed: bool = False,
) -> ResultadoSandbox:
    return ResultadoSandbox(
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        coverage=coverage,
        timed_out=timed_out,
        oom_killed=oom_killed,
        duracion_s=0.1,
    )


def test_syntax_error_es_error_test_y_retry(tmp_path: Path) -> None:
    ejecutor = EjecutorGrabado(sandbox(0))
    reviewer = ReviewerAgent(
        TokenTracker(),
        tmp_path,
        "imagen-prueba",
        ejecutor=ejecutor,
    )
    test = {
        "version": "1",
        "objetivo": "duplicar",
        "intento": 1,
        "codigo": "def test_duplicar()\n    assert duplicar(2) == 4\n",
        "casos_cubiertos": ["duplica_positivo"],
    }

    revision = reviewer.revisar(CONTRATO, test, None)

    assert contracts.es_valido(contracts.REVIEW_RESULT, revision)
    assert revision["estado_sandbox"] == "fallo"
    assert revision["tipo_fallo"] == "error_test"
    assert revision["decision"] == "retry"
    assert revision["hash_error"]
    assert "SyntaxError" in revision["feedback"]
    assert ejecutor.llamadas == 0


def test_import_error_es_error_test_y_retry(tmp_path: Path) -> None:
    resultado = sandbox(
        2,
        stdout=(
            "ImportError while importing test module\n"
            "ModuleNotFoundError: No module named 'calculadora'"
        ),
    )
    reviewer = ReviewerAgent(
        TokenTracker(),
        tmp_path,
        "imagen-prueba",
        ejecutor=EjecutorGrabado(resultado),
    )
    test = {
        "version": "1",
        "objetivo": "duplicar",
        "intento": 1,
        "codigo": CODIGO_VALIDO,
        "casos_cubiertos": ["duplica_positivo"],
    }

    revision = reviewer.revisar(CONTRATO, test, None)

    assert revision["estado_sandbox"] == "fallo"
    assert revision["tipo_fallo"] == "error_test"
    assert revision["decision"] == "retry"
    assert "ModuleNotFoundError" in revision["feedback"]


def test_assertion_error_es_bug_codigo(tmp_path: Path) -> None:
    resultado = sandbox(
        1,
        stdout="FAILED test_generado.py::test_duplicar - assert 3 == 4",
    )
    reviewer = ReviewerAgent(
        TokenTracker(),
        tmp_path,
        "imagen-prueba",
        ejecutor=EjecutorGrabado(resultado),
    )
    test = {
        "version": "1",
        "objetivo": "duplicar",
        "intento": 1,
        "codigo": CODIGO_VALIDO,
        "casos_cubiertos": ["duplica_positivo"],
    }

    revision = reviewer.revisar(CONTRATO, test, None)

    assert revision["tipo_fallo"] == "bug_codigo"
    assert revision["decision"] == "bug_detectado"


def test_test_correcto_es_accept(tmp_path: Path) -> None:
    resultado = sandbox(
        0,
        stdout="1 passed",
        coverage={
            "totals": {
                "percent_covered": 75.0,
                "num_branches": 4,
                "covered_branches": 2,
            }
        },
    )
    reviewer = ReviewerAgent(
        TokenTracker(),
        tmp_path,
        "imagen-prueba",
        ejecutor=EjecutorGrabado(resultado),
    )
    test = {
        "version": "1",
        "objetivo": "duplicar",
        "intento": 1,
        "codigo": CODIGO_VALIDO,
        "casos_cubiertos": ["duplica_positivo"],
    }

    revision = reviewer.revisar(CONTRATO, test, None)

    assert revision["decision"] == "accept"
    assert revision["tipo_fallo"] is None
    assert revision["cobertura"] == {"lineas": 75.0, "ramas": 50.0}


def test_correccion_debilitada_detecta_laundering(tmp_path: Path) -> None:
    anterior = {
        "version": "1",
        "objetivo": "duplicar",
        "intento": 1,
        "codigo": CODIGO_VALIDO,
        "casos_cubiertos": ["duplica_positivo"],
    }
    actual = {
        **anterior,
        "intento": 2,
        "codigo": (
            "from calculadora import duplicar\n\n"
            "def test_duplicar():\n"
            "    assert duplicar(2) is not None\n"
        ),
    }
    ejecutor = EjecutorGrabado(sandbox(0))
    reviewer = ReviewerAgent(
        TokenTracker(),
        tmp_path,
        "imagen-prueba",
        ejecutor=ejecutor,
    )

    revision = reviewer.revisar(CONTRATO, actual, anterior)

    assert revision["laundering_detectado"] is True
    assert revision["decision"] == "retry"
    assert revision["tipo_fallo"] == "error_test"
    assert ejecutor.llamadas == 0


def test_error_test_en_tercer_intento_termina_stalled(tmp_path: Path) -> None:
    reviewer = ReviewerAgent(
        TokenTracker(),
        tmp_path,
        "imagen-prueba",
        ejecutor=EjecutorGrabado(sandbox(0)),
    )
    test = {
        "version": "1",
        "objetivo": "duplicar",
        "intento": 3,
        "codigo": "def test_duplicar(\n",
        "casos_cubiertos": ["duplica_positivo"],
    }

    revision = reviewer.revisar(CONTRATO, test, None)

    assert revision["tipo_fallo"] == "error_test"
    assert revision["decision"] == "stalled"


def test_primer_intento_con_assert_true_no_se_acepta(tmp_path: Path) -> None:
    ejecutor = EjecutorGrabado(sandbox(0))
    reviewer = ReviewerAgent(
        TokenTracker(), tmp_path, "imagen-prueba", ejecutor=ejecutor
    )
    test = {
        "version": "1",
        "objetivo": "duplicar",
        "intento": 1,
        "codigo": "def test_duplicar():\n    assert True\n",
        "casos_cubiertos": ["duplica_positivo"],
    }

    revision = reviewer.revisar(CONTRATO, test, None)

    assert revision["decision"] == "retry"
    assert revision["tipo_fallo"] == "error_test"
    assert "valor esperado 4" in revision["feedback"]
    assert ejecutor.llamadas == 0


def test_primer_intento_con_valor_cambiado_no_se_acepta(tmp_path: Path) -> None:
    ejecutor = EjecutorGrabado(sandbox(0))
    reviewer = ReviewerAgent(
        TokenTracker(), tmp_path, "imagen-prueba", ejecutor=ejecutor
    )
    test = {
        "version": "1",
        "objetivo": "duplicar",
        "intento": 1,
        "codigo": (
            "from calculadora import duplicar\n\n"
            "def test_duplicar():\n"
            "    assert duplicar(2) == 5\n"
        ),
        "casos_cubiertos": ["duplica_positivo"],
    }

    revision = reviewer.revisar(CONTRATO, test, None)

    assert revision["decision"] == "retry"
    assert revision["tipo_fallo"] == "error_test"
    assert "valor esperado 4" in revision["feedback"]
    assert ejecutor.llamadas == 0


def test_primer_intento_sin_aserciones_no_se_acepta(tmp_path: Path) -> None:
    ejecutor = EjecutorGrabado(sandbox(0))
    reviewer = ReviewerAgent(
        TokenTracker(), tmp_path, "imagen-prueba", ejecutor=ejecutor
    )
    test = {
        "version": "1",
        "objetivo": "duplicar",
        "intento": 1,
        "codigo": (
            "from calculadora import duplicar\n\n"
            "def test_duplicar():\n"
            "    duplicar(2)\n"
        ),
        "casos_cubiertos": ["duplica_positivo"],
    }

    revision = reviewer.revisar(CONTRATO, test, None)

    assert revision["decision"] == "retry"
    assert revision["tipo_fallo"] == "error_test"
    assert "no contiene aserciones" in revision["feedback"]
    assert ejecutor.llamadas == 0


def test_name_error_de_pytest_es_error_test(tmp_path: Path) -> None:
    resultado = sandbox(
        1,
        stdout=(
            "FAILED test_generado.py::test_duplicar\n"
            "NameError: name 'pytest' is not defined"
        ),
    )
    reviewer = ReviewerAgent(
        TokenTracker(),
        tmp_path,
        "imagen-prueba",
        ejecutor=EjecutorGrabado(resultado),
    )
    test = {
        "version": "1",
        "objetivo": "duplicar",
        "intento": 1,
        "codigo": CODIGO_VALIDO,
        "casos_cubiertos": ["duplica_positivo"],
    }

    revision = reviewer.revisar(CONTRATO, test, None)

    assert revision["tipo_fallo"] == "error_test"
    assert revision["decision"] == "retry"


def test_fallo_ambiguo_consulta_al_reviewer_llm(tmp_path: Path) -> None:
    cliente = ClienteClasificador("error_test")
    tracker = TokenTracker()
    resultado = sandbox(1, stdout="RuntimeError durante la preparación del test")
    reviewer = ReviewerAgent(
        tracker,
        tmp_path,
        "imagen-prueba",
        cliente=cliente,
        ejecutor=EjecutorGrabado(resultado),
        es_simulado=True,
    )
    test = {
        "version": "1",
        "objetivo": "duplicar",
        "intento": 1,
        "codigo": CODIGO_VALIDO,
        "casos_cubiertos": ["duplica_positivo"],
    }

    revision = reviewer.revisar(CONTRATO, test, None)

    assert revision["tipo_fallo"] == "error_test"
    assert revision["decision"] == "retry"
    assert len(cliente.prompts) == 1
    assert "CONTRATO DEL PLANNER" in cliente.prompts[0]
    assert tracker.llamadas[0].agente == "reviewer"
