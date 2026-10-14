"""Pruebas del ReviewerAgent con el sandbox sustituido."""

from __future__ import annotations

from pathlib import Path

from qagent import contracts
from qagent.agents.reviewer import ReviewerAgent
from qagent.llm import RespuestaLLM, TokenTracker
from qagent.sandbox import ResultadoSandbox

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

CONTRATO_ENDPOINT = {
    "version": "2",
    "modulo": "api_mvp.py",
    "huella": "b" * 64,
    "tipo": "endpoint",
    "objetivo": "GET /salud",
    "manejador": "salud",
    "aplicacion": "app",
    "dependencias": [],
    "firma": "() -> dict[str, str]",
    "critical": False,
    "llama_a": [],
    "casos": [
        {
            "id": "salud_ok",
            "entrada": {"metodo": "GET", "ruta": "/salud"},
            "valor_esperado": {"status_code": 200, "json": {"estado": "ok"}},
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

    def __init__(
        self, resultado: ResultadoSandbox, modulo_cov_esperado: str = "calculadora"
    ) -> None:
        self.resultado = resultado
        self.modulo_cov_esperado = modulo_cov_esperado
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
        assert modulo_cov == self.modulo_cov_esperado
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


def test_oraculo_endpoint_valida_status_y_json(tmp_path: Path) -> None:
    codigo = (
        "def test_salud(client):\n"
        "    response = client.get('/salud')\n"
        "    assert response.status_code == 200\n"
        "    assert response.json() == {'estado': 'ok'}\n"
    )
    reviewer = ReviewerAgent(
        TokenTracker(),
        tmp_path,
        "imagen-prueba",
        ejecutor=EjecutorGrabado(
            sandbox(0, stdout="1 passed"), modulo_cov_esperado="api_mvp"
        ),
    )

    revision = reviewer.revisar(
        CONTRATO_ENDPOINT,
        {
            "version": "1",
            "objetivo": "GET /salud",
            "intento": 1,
            "codigo": codigo,
            "casos_cubiertos": ["salud_ok"],
        },
        None,
    )

    assert revision["decision"] == "accept"


def test_oraculo_endpoint_rechaza_json_esperado_omitido(tmp_path: Path) -> None:
    codigo = (
        "def test_salud(client):\n"
        "    response = client.get('/salud')\n"
        "    assert response.status_code == 200\n"
    )
    ejecutor = EjecutorGrabado(sandbox(0))
    reviewer = ReviewerAgent(
        TokenTracker(), tmp_path, "imagen-prueba", ejecutor=ejecutor
    )

    revision = reviewer.revisar(
        CONTRATO_ENDPOINT,
        {
            "version": "1",
            "objetivo": "GET /salud",
            "intento": 1,
            "codigo": codigo,
            "casos_cubiertos": ["salud_ok"],
        },
        None,
    )

    assert revision["decision"] == "retry"
    assert "{'estado': 'ok'}" in revision["feedback"]
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


def _intento(intento: int, codigo: str) -> dict:
    return {
        "version": "1",
        "objetivo": "duplicar",
        "intento": intento,
        "codigo": codigo,
        "casos_cubiertos": ["duplica_positivo"],
    }


CODIGO_DEBILITADO = (
    "from calculadora import duplicar\n\n"
    "def test_duplicar():\n"
    "    assert duplicar(2) == 4 or True\n"
)

CODIGO_MAS_DEBIL = (
    "from calculadora import duplicar\n\n"
    "def test_duplicar():\n"
    "    assert duplicar(2) is not None\n"
)


def test_laundering_se_compara_con_el_ultimo_test_no_debilitado(
    tmp_path: Path,
) -> None:
    """Un intento rechazado por laundering no pasa a ser la referencia del siguiente."""
    reviewer = ReviewerAgent(
        TokenTracker(),
        tmp_path,
        "imagen-prueba",
        ejecutor=EjecutorGrabado(sandbox(2, stdout="ImportError: no module")),
    )
    primero = _intento(1, CODIGO_VALIDO)
    segundo = _intento(2, CODIGO_DEBILITADO)
    tercero = _intento(3, CODIGO_DEBILITADO)

    reviewer.revisar(CONTRATO, primero, None)
    revision_2 = reviewer.revisar(CONTRATO, segundo, primero)
    # El orquestador pasa el intento 2 (debilitado) como "anterior" del 3.
    revision_3 = reviewer.revisar(CONTRATO, tercero, segundo)

    assert revision_2["laundering_detectado"] is True
    assert revision_3["laundering_detectado"] is True
    assert revision_3["decision"] == "stalled"


def test_la_referencia_se_reinicia_en_el_primer_intento(tmp_path: Path) -> None:
    reviewer = ReviewerAgent(
        TokenTracker(),
        tmp_path,
        "imagen-prueba",
        ejecutor=EjecutorGrabado(sandbox(0)),
    )
    reviewer.revisar(CONTRATO, _intento(1, CODIGO_VALIDO), None)

    otra_corrida = (
        "from calculadora import duplicar\n\n"
        "def test_duplicar_otro():\n"
        "    assert duplicar(2) == 4\n"
    )
    revision = reviewer.revisar(CONTRATO, _intento(1, otra_corrida), None)

    assert revision["laundering_detectado"] is False
    assert revision["decision"] == "accept"


def test_sin_tests_recolectados_es_error_test(tmp_path: Path) -> None:
    """pytest sale con código 5 si no encuentra funciones test_: se reintenta."""
    reviewer = ReviewerAgent(
        TokenTracker(),
        tmp_path,
        "imagen-prueba",
        ejecutor=EjecutorGrabado(
            sandbox(5, stdout="collected 0 items\n\nno tests ran")
        ),
    )

    revision = reviewer.revisar(CONTRATO, _intento(1, CODIGO_VALIDO), None)

    assert revision["tipo_fallo"] == "error_test"
    assert revision["decision"] == "retry"
    assert revision["estado_sandbox"] == "fallo"


def test_la_cobertura_es_la_de_la_funcion_y_no_la_del_modulo(tmp_path: Path) -> None:
    """coverage.py mide el módulo completo; el Reviewer cuenta solo el cuerpo de la función."""
    (tmp_path / "calculadora.py").write_text(
        "def duplicar(x):\n"  # 1
        "    if x < 0:\n"  # 2
        "        return 0\n"  # 3
        "    return x * 2\n"  # 4
        "\n"
        "def otra():\n"  # 6
        "    return 1\n",  # 7
        encoding="utf-8",
    )
    coverage = {
        "files": {
            "calculadora.py": {
                "executed_lines": [1, 2, 4, 6],
                "missing_lines": [3, 7],
                "executed_branches": [[2, 4]],
                "missing_branches": [[2, 3]],
            }
        },
        "totals": {"percent_covered": 50.0, "num_branches": 2, "covered_branches": 1},
    }
    reviewer = ReviewerAgent(
        TokenTracker(),
        tmp_path,
        "imagen-prueba",
        ejecutor=EjecutorGrabado(sandbox(0, coverage=coverage)),
    )

    revision = reviewer.revisar(CONTRATO, _intento(1, CODIGO_VALIDO), None)

    # Cuerpo de duplicar = líneas 2 a 4: se ejecutaron 2 y 4, faltó 3.
    assert revision["cobertura"] == {"lineas": 66.67, "ramas": 50.0}
