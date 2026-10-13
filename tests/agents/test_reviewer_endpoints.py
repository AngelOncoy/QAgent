"""EN-16: el Reviewer y la corrida con pruebas de endpoints FastAPI.

Sin red, sin Docker y sin FastAPI: las pruebas de endpoints son las escritas a mano
en `endpoints_a_mano.py` y el sandbox se reemplaza por salidas de pytest grabadas.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from endpoints_a_mano import PRUEBAS

from pyagent import contracts
from pyagent.agents.planner import PlannerAgent
from pyagent.agents.reviewer import ReviewerAgent
from pyagent.almacenamiento import AlmacenProyecto
from pyagent.analysis import analizar_proyecto, comparar_aserciones
from pyagent.config import cargar_configuracion
from pyagent.config.carga import RUTA_CONFIG
from pyagent.llm import FakeLLMClient, TokenTracker
from pyagent.orchestrator.corrida import ejecutar_corrida
from pyagent.sandbox import ResultadoSandbox

RAIZ_REPO = Path(__file__).resolve().parents[2]
BANCO_API = RAIZ_REPO / "bench_api"
# Lo que pytest muestra con FastAPI real para los 3 bugs de bench_api/bugs.md.
SALIDAS_BUG = {
    "test_obtener_inexistente": (
        "E   fastapi.exceptions.ResponseValidationError: 1 validation error:\n"
        "FAILED test_generado.py::test_obtener_inexistente - "
        "fastapi.exceptions.ResponseValidationError"
    ),
    "test_borrar_existente": (
        "E       assert 200 == 204\n"
        "FAILED test_generado.py::test_borrar_existente - assert 200 == 204"
    ),
    "test_descuento_normal": (
        "E       AssertionError: assert {'precio_final': 20.0} == "
        "{'precio_final': 80.0}\nFAILED test_generado.py::test_descuento_normal"
    ),
}


def resultado(exit_code: int, salida: str = "", coverage: dict | None = None):
    return ResultadoSandbox(
        exit_code=exit_code,
        stdout=salida,
        stderr="",
        coverage=coverage,
        timed_out=False,
        oom_killed=False,
        duracion_s=0.1,
    )


def ejecutor_api(imagen, ruta_proyecto, ruta_tests, modulo_cov) -> ResultadoSandbox:
    """Responde como pytest con FastAPI real sobre bench_api (ver el informe EN-16)."""
    codigo = (ruta_tests / "test_generado.py").read_text(encoding="utf-8")
    for nombre, salida in SALIDAS_BUG.items():
        if f"def {nombre}(" in codigo:
            return resultado(1, salida)
    return resultado(0, "3 passed")


@pytest.fixture(scope="module")
def plan_api() -> dict[str, dict]:
    modulo = analizar_proyecto(BANCO_API)["modulos"][0]
    fuente = (BANCO_API / "api_mvp.py").read_text(encoding="utf-8")
    agente = PlannerAgent(FakeLLMClient(), TokenTracker(), es_simulado=True)
    return {c["objetivo"]: c for c in agente.planificar_endpoints(modulo, fuente)}


def reviewer(ejecutor=ejecutor_api, ruta: Path = BANCO_API) -> ReviewerAgent:
    return ReviewerAgent(TokenTracker(), ruta, "imagen-prueba", ejecutor=ejecutor)


def prueba(objetivo: str, codigo: str, intento: int = 1) -> dict:
    return {"version": "1", "objetivo": objetivo, "intento": intento, "codigo": codigo}


# --- Veredictos sobre la API de prueba ----------------------------------------
@pytest.mark.parametrize(
    ("objetivo", "decision"),
    [
        ("GET /salud", "accept"),
        ("POST /items", "accept"),
        ("GET /items", "accept"),
        ("GET /items/{item_id}", "bug_detectado"),  # bug 1
        ("DELETE /items/{item_id}", "bug_detectado"),  # bug 2
        ("GET /descuento", "bug_detectado"),  # bug 3
    ],
)
def test_veredicto_de_cada_endpoint_del_banco(plan_api, objetivo, decision):
    contrato = plan_api[objetivo]
    revision = reviewer().revisar(contrato, prueba(objetivo, PRUEBAS[objetivo]), None)

    contracts.validar(contracts.REVIEW_RESULT, revision)
    assert revision["decision"] == decision, revision["feedback"]
    if decision == "bug_detectado":
        assert revision["tipo_fallo"] == "bug_codigo"


def test_response_validation_error_es_bug_de_la_api(plan_api):
    contrato = plan_api["GET /items/{item_id}"]
    revision = reviewer().revisar(
        contrato, prueba("x", PRUEBAS["GET /items/{item_id}"]), None
    )
    assert "response_model" in revision["feedback"]
    assert revision["laundering_detectado"] is False


# --- El oráculo de un endpoint: estado y cuerpo esperados -----------------------
def _sin(codigo: str, linea: str) -> str:
    assert linea in codigo
    return codigo.replace(linea, "    assert r is not None\n", 1)


@pytest.mark.parametrize(
    ("objetivo", "linea", "falta"),
    [
        ("GET /salud", "    assert r.status_code == 200\n", "status_code 200"),
        ("GET /salud", '    assert r.json() == {"estado": "ok"}\n', "cuerpo esperado"),
        ("POST /items", '    assert r.json()["precio"] == 2.5\n', "campo 'precio'"),
        (
            "GET /items/{item_id}",
            "    assert r.status_code == 404\n",
            "status_code 404",
        ),
    ],
    ids=["sin_estado", "sin_cuerpo", "sin_campo", "sin_404"],
)
def test_oraculo_exige_estado_y_cuerpo(plan_api, objetivo, linea, falta):
    ejecutor = _Contador()
    codigo = _sin(PRUEBAS[objetivo], linea)
    revision = reviewer(ejecutor).revisar(
        plan_api[objetivo], prueba(objetivo, codigo), None
    )

    assert revision["decision"] == "retry"
    assert revision["tipo_fallo"] == "error_test"
    assert falta in revision["feedback"]
    assert ejecutor.llamadas == 0  # no se ejecuta un test sin oráculo


def test_json_contiene_acepta_un_dict_con_los_campos(plan_api):
    codigo = PRUEBAS["POST /items"].replace(
        '    assert r.json()["nombre"] == "lapiz"\n    assert r.json()["precio"] == 2.5\n',
        '    assert r.json() | {"id": 1} == {"nombre": "lapiz", "precio": 2.5, "id": 1}\n',
    )
    revision = reviewer().revisar(plan_api["POST /items"], prueba("x", codigo), None)
    assert revision["decision"] == "accept", revision["feedback"]


class _Contador:
    def __init__(self, salida: ResultadoSandbox | None = None) -> None:
        self.salida = salida or resultado(0, "1 passed")
        self.llamadas = 0

    def __call__(self, *args) -> ResultadoSandbox:
        self.llamadas += 1
        return self.salida


# --- Errores de entorno: se reportan sin reintentar ----------------------------
@pytest.mark.parametrize(
    "salida",
    [
        "E   ConnectionRefusedError: [Errno 111] Connection refused",
        "E   sqlalchemy.exc.OperationalError: could not connect to server",
        "E   ModuleNotFoundError: No module named 'fastapi'",
    ],
    ids=["conexion", "base_de_datos", "dependencia_declarada"],
)
def test_error_de_entorno_queda_estancado_sin_reintentos(plan_api, salida):
    revision = reviewer(_Contador(resultado(2, salida))).revisar(
        plan_api["GET /salud"], prueba("GET /salud", PRUEBAS["GET /salud"]), None
    )
    contracts.validar(contracts.REVIEW_RESULT, revision)
    assert revision["decision"] == "stalled"
    assert revision["tipo_fallo"] is None
    assert revision["estado_sandbox"] == "fallo"  # no aborta el módulo
    assert revision["feedback"].startswith("Error de entorno")


def test_modulo_inventado_por_el_test_si_se_reintenta(plan_api):
    salida = "E   ModuleNotFoundError: No module named 'mi_api'"
    revision = reviewer(_Contador(resultado(2, salida))).revisar(
        plan_api["GET /salud"], prueba("GET /salud", PRUEBAS["GET /salud"]), None
    )
    assert revision["decision"] == "retry"
    assert revision["tipo_fallo"] == "error_test"


# --- Cobertura sobre la función que atiende la ruta -----------------------------
def test_cobertura_se_mide_en_el_manejador(plan_api):
    contrato = plan_api["GET /salud"]
    import ast

    arbol = ast.parse((BANCO_API / "api_mvp.py").read_text(encoding="utf-8"))
    salud = next(n for n in arbol.body if getattr(n, "name", "") == "salud")
    cuerpo = list(range(salud.body[0].lineno, salud.end_lineno + 1))
    coverage = {
        "files": {"api_mvp.py": {"executed_lines": cuerpo, "missing_lines": [1, 2]}},
        "totals": {"percent_covered": 40.0},
    }
    revision = reviewer(_Contador(resultado(0, "1 passed", coverage))).revisar(
        contrato, prueba("GET /salud", PRUEBAS["GET /salud"]), None
    )
    assert revision["cobertura"]["lineas"] == 100.0


# --- Assertion Laundering en pruebas de endpoints --------------------------------
@pytest.mark.parametrize(
    ("antes", "despues"),
    [
        ("assert r.status_code == 201", "assert r.status_code in (200, 201)"),
        ("assert r.status_code == 201", "assert r.status_code < 500"),
        ("assert r.status_code == 204", "assert r.status_code == 200"),
        ('assert r.json() == {"a": 1}', 'assert "a" in r.json()'),
        ('assert r.json() == {"a": 1}', "assert r.json()"),
        ("assert r.status_code == 404", "assert r.status_code == r.status_code"),
    ],
)
def test_debilitar_un_endpoint_es_laundering(antes, despues):
    plantilla = "def test_x(cliente):\n    r = cliente.get('/x')\n    {}\n"
    comparacion = comparar_aserciones(
        plantilla.format(antes), plantilla.format(despues)
    )
    assert comparacion.es_laundering, comparacion.resumen


def test_quitar_la_asercion_de_estado_es_laundering():
    antes = (
        "def test_x(r):\n    assert r.status_code == 201\n    assert r.json() == {}\n"
    )
    despues = "def test_x(r):\n    assert r.json() == {}\n"
    assert comparar_aserciones(antes, despues).es_laundering


def test_reviewer_rechaza_el_reintento_debilitado(plan_api):
    contrato = plan_api["DELETE /items/{item_id}"]
    original = PRUEBAS["DELETE /items/{item_id}"]
    debilitado = original.replace(
        "assert r.status_code == 204", "assert r.status_code in (200, 204)"
    )
    agente = reviewer()
    primero = agente.revisar(contrato, prueba("x", original), None)
    segundo = agente.revisar(
        contrato, prueba("x", debilitado, 2), prueba("x", original)
    )
    assert primero["decision"] == "bug_detectado"
    assert segundo["laundering_detectado"] is True
    assert segundo["decision"] == "retry"


# --- Orquestador y corrida -------------------------------------------------------
@pytest.fixture
def proyecto_api(tmp_path: Path) -> AlmacenProyecto:
    carpeta = tmp_path / "api"
    shutil.copytree(BANCO_API, carpeta, ignore=shutil.ignore_patterns("*.md"))
    almacen = AlmacenProyecto(carpeta)
    almacen.inicializar()
    return almacen


def test_corrida_de_la_api_de_prueba_con_generator_real(proyecto_api):
    config = cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config
    eventos: list[dict] = []
    run_id = proyecto_api.crear_run(tipos_prueba=["funcion"])["run_id"]

    resumen = ejecutar_corrida(
        proyecto_api.raiz,
        "deep",
        config,
        None,
        simulado=True,
        al_evento=eventos.append,
        run_id=run_id,
        preparar_imagen=lambda ruta: "imagen-prueba",
        ejecutor=ejecutor_api,
    )

    assert resumen.estado == "fin", resumen.motivo
    assert (resumen.aceptadas, resumen.bugs_detectados, resumen.estancadas) == (3, 3, 0)
    mensajes = [e["mensaje"] for e in eventos]
    assert any("2 función(es) pública(s) y 6 endpoint(s)" in m for m in mensajes)
    assert "Plan con 6 objetivo(s)" in mensajes

    carpeta = proyecto_api.carpeta_run(resumen.run_id)
    results = json.loads((carpeta / "results.json").read_text(encoding="utf-8"))
    objetivos = {o["funcion"]: o for o in results["objetivos"]}
    assert objetivos["GET /descuento"]["tipo"] == "endpoint"
    assert objetivos["GET /descuento"]["decision"] == "bug_detectado"
    assert proyecto_api.leer_run(resumen.run_id)["tipos_prueba"] == [
        "funcion",
        "endpoint",
    ]
    aprobadas = sorted(p.name for p in proyecto_api.listar_pruebas_aprobadas())
    assert aprobadas == [
        "test_api_mvp_py__GET_items.py",
        "test_api_mvp_py__GET_salud.py",
        "test_api_mvp_py__POST_items.py",
    ]


def test_planner_sin_planificar_endpoints_sigue_funcionando():
    """Un Planner antiguo (solo funciones) no rompe el orquestador."""
    from pyagent.orchestrator.orquestador import Orquestador

    class SoloFunciones:
        def planificar(self, modulo):
            return []

    orq = Orquestador(SoloFunciones(), None, None, tracker=TokenTracker())
    assert orq._planificar_endpoints({"endpoints": [{"objetivo": "GET /x"}]}) == []


def test_modulo_sin_endpoints_no_llama_al_planner_de_endpoints():
    from pyagent.orchestrator.orquestador import Orquestador

    class Espia:
        llamadas = 0

        def planificar_endpoints(self, modulo, fuente=None):
            Espia.llamadas += 1
            return []

    orq = Orquestador(Espia(), None, None, tracker=TokenTracker())
    assert orq._planificar_endpoints({"endpoints": []}) == []
    assert Espia.llamadas == 0
