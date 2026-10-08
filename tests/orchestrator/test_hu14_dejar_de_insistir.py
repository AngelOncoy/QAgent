"""HU-14: el sistema deja de reparar una prueba que no converge.

Evidencia del criterio 5 con errores simulados (IA simulada, sin Docker, 0 tokens):
corte a los 3 intentos o al repetirse el hash del error normalizado.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from fakes import (
    MODULO,
    GeneratorEspia,
    GeneratorSimulado,
    PlannerSimulado,
    ReviewerConErrores,
    ReviewerGuionado,
    veredicto,
)

from pyagent.contracts import REVIEW_RESULT, RUN_LOG, es_valido
from pyagent.llm import FakeLLMClient, TokenTracker, cargar_precios
from pyagent.orchestrator import (
    ERROR_REPETIDO,
    LIMITE_INTENTOS,
    BusEventos,
    Estado,
    Orquestador,
    decidir_corte,
    etiqueta_estancado,
)
from pyagent.sandbox.normalizacion import hash_error, normalizar_error
from pyagent.storage import escribir_corrida

E = Estado

# Mismo ImportError en tres ejecuciones: cambian la carpeta temporal (Linux y
# Windows), el número de línea, la dirección de memoria y la duración.
ERROR_A1 = """\
/tmp/pytest-of-qa/pytest-3/test_duplicar0/test_duplicar.py:12: in <module>
    from modulo_simulado import duplicar
E   ImportError: cannot import name 'duplicar' from <module 'modulo_simulado' at 0x7f3a2c1b9d60>
  File "/app/src/modulo_simulado.py", line 42
1 error in 0.12s
"""
ERROR_A2 = """\
C:\\Users\\qa\\AppData\\Local\\Temp\\pytest-of-qa\\pytest-7\\test_duplicar0\\test_duplicar.py:27: in <module>
    from modulo_simulado import duplicar
E   ImportError: cannot import name 'duplicar' from <module 'modulo_simulado' at 0x000001F2A3B4C5D6>
  File "C:/proyectos/tienda/src/modulo_simulado.py", line 7
1 error in 3.48s
"""
ERROR_A3 = """\
/tmp/tmpk2j9x0ab/test_duplicar.py:99: in <module>
    from modulo_simulado import duplicar
E   ImportError: cannot import name 'duplicar' from <module 'modulo_simulado' at 0x55d0c0ffee00>
  File "/home/runner/work/src/modulo_simulado.py", line 3
1 error in 0.02s
"""
ERROR_B = """\
/tmp/pytest-of-qa/pytest-3/test_duplicar0/test_duplicar.py:5: in test_duplicar
E   NameError: name 'pytest' is not defined
1 failed in 0.10s
"""
ERROR_C = """\
/tmp/pytest-of-qa/pytest-3/test_duplicar0/test_duplicar.py:8: in test_duplicar
E   TypeError: duplicar() missing 1 required positional argument: 'x'
1 failed in 0.09s
"""


def armar(reviewer, generator=None, **opciones):
    """Orquestador con Planner simulado; devuelve (orquestador, generator, reviewer)."""
    tracker = TokenTracker()
    generator = generator or GeneratorSimulado(tracker)
    orquestador = Orquestador(
        PlannerSimulado(tracker),
        generator,
        reviewer,
        bus=BusEventos(),
        tracker=tracker,
        **opciones,
    )
    return orquestador, generator, reviewer


def veredicto_final(orquestador: Orquestador):
    [evento] = [e for e in orquestador.bus.historial if e.tipo == "veredicto"]
    return evento


# --- Criterio 2: normalización del error (caso e) -------------------------------


def test_errores_que_solo_difieren_en_ruta_linea_memoria_y_tiempo_dan_el_mismo_hash() -> (
    None
):
    assert normalizar_error(ERROR_A1) == normalizar_error(ERROR_A2)
    assert hash_error(ERROR_A1) == hash_error(ERROR_A2) == hash_error(ERROR_A3)


def test_errores_distintos_dan_hashes_distintos() -> None:
    hashes = {hash_error(ERROR_A1), hash_error(ERROR_B), hash_error(ERROR_C)}
    assert len(hashes) == 3


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("/tmp/pytest-of-ana/pytest-1/test_x.py:12: in f", "<ruta>:<n>: in f"),
        ("C:\\Users\\ana\\Temp\\test_x.py:48: in f", "<ruta>:<n>: in f"),
        ('File "/app/x.py", line 42, in f', 'File "<ruta>", line <n>, in f'),
        ("<Foo object at 0x7f3a2c1b9d60>", "<Foo object at <mem>>"),
        ("1 failed in 0.12s", "1 failed in <t>"),
        ("tardó 250ms", "tardó <t>"),
        ("a   b\r\n\r\n  c  ", "a b\nc"),
    ],
)
def test_normalizar_error_reemplaza_lo_variable(texto: str, esperado: str) -> None:
    assert normalizar_error(texto) == esperado


def test_normalizar_conserva_el_mensaje_del_error() -> None:
    normalizado = normalizar_error(ERROR_B)
    assert "NameError: name 'pytest' is not defined" in normalizado
    assert "qa" not in normalizado and "0.10" not in normalizado


def test_hash_cumple_el_pattern_de_review_result() -> None:
    dato = veredicto("duplicar", 1, "retry", hash_error=hash_error(ERROR_A1))
    assert es_valido(REVIEW_RESULT, dato)
    assert len(dato["hash_error"]) == 64


# --- Criterio 5: evidencia del corte en el orquestador --------------------------


def test_a_tres_errores_distintos_cortan_en_el_intento_3_por_limite() -> None:
    orquestador, generator, _ = armar(ReviewerConErrores([ERROR_A1, ERROR_B, ERROR_C]))

    resultado = orquestador.ejecutar(MODULO)

    [objetivo] = resultado.objetivos
    assert resultado.estado_final is E.FIN
    assert objetivo.decision == "stalled"
    assert objetivo.intentos == 3
    assert objetivo.motivo_estancado == LIMITE_INTENTOS
    assert len(generator.feedbacks) == 3
    assert veredicto_final(orquestador).mensaje == "Estancado 3/3 · límite de intentos"


def test_b_mismo_error_normalizado_corta_en_el_intento_2() -> None:
    orquestador, generator, reviewer = armar(
        ReviewerConErrores([ERROR_A1, ERROR_A2, ERROR_A3])
    )

    resultado = orquestador.ejecutar(MODULO)

    [objetivo] = resultado.objetivos
    assert objetivo.decision == "stalled"
    assert objetivo.intentos == 2
    assert objetivo.motivo_estancado == ERROR_REPETIDO
    assert len(generator.feedbacks) == 2  # no hubo intento 3
    assert reviewer.errores == [ERROR_A3]  # el tercer error nunca se pidió
    assert resultado.traza_estados.count(E.REINTENTAR) == 1
    assert (
        veredicto_final(orquestador).mensaje == "Estancado 2/3 · mismo error repetido"
    )


def test_c_error_a_luego_b_repetido_corta_en_el_intento_3_por_error_repetido() -> None:
    orquestador, *_ = armar(ReviewerConErrores([ERROR_A1, ERROR_B, ERROR_B]))

    resultado = orquestador.ejecutar(MODULO)

    [objetivo] = resultado.objetivos
    assert objetivo.decision == "stalled"
    assert objetivo.intentos == 3
    assert objetivo.motivo_estancado == ERROR_REPETIDO


def test_errores_iguales_no_consecutivos_siguen_reintentando() -> None:
    orquestador, *_ = armar(ReviewerConErrores([ERROR_A1, ERROR_B, ERROR_A2]))

    [objetivo] = orquestador.ejecutar(MODULO).objetivos

    assert (objetivo.intentos, objetivo.motivo_estancado) == (3, LIMITE_INTENTOS)


def test_d_exito_antes_del_limite_es_accept() -> None:
    orquestador, *_ = armar(ReviewerConErrores([ERROR_A1, ERROR_B, None]))

    resultado = orquestador.ejecutar(MODULO)

    [objetivo] = resultado.objetivos
    assert objetivo.decision == "accept"
    assert objetivo.intentos == 3
    assert objetivo.motivo_estancado is None
    assert veredicto_final(orquestador).datos == {"decision": "accept", "intento": 3}


def test_evento_del_estancado_lleva_intento_motivo_y_etiqueta() -> None:
    orquestador, *_ = armar(ReviewerConErrores([ERROR_A1, ERROR_A2]))

    orquestador.ejecutar(MODULO)

    evento = veredicto_final(orquestador)
    assert evento.funcion == "duplicar"
    assert evento.datos == {
        "decision": "stalled",
        "intento": 2,
        "max_intentos": 3,
        "motivo": "error_repetido",
        "etiqueta": "Estancado 2/3 · mismo error repetido",
    }
    json.dumps(evento.a_dict())  # llega a la interfaz como JSON


# --- Criterio 1: nunca más de 3 intentos ----------------------------------------


def test_reviewer_que_pide_retry_en_el_intento_3_queda_estancado_3_de_3() -> None:
    # Un Reviewer que siempre pide otro intento, con errores siempre distintos.
    errores = [ERROR_A1, ERROR_B, ERROR_C, ERROR_A1, ERROR_B]
    orquestador, generator, reviewer = armar(ReviewerConErrores(errores))

    resultado = orquestador.ejecutar(MODULO)

    [objetivo] = resultado.objetivos
    assert resultado.estado_final is E.FIN  # no termina en fallo controlado
    assert (objetivo.decision, objetivo.intentos) == ("stalled", 3)
    assert objetivo.motivo_estancado == LIMITE_INTENTOS
    assert len(generator.feedbacks) == 3
    assert len(reviewer.errores) == 2  # nunca hubo intento 4 ni 5


@pytest.mark.parametrize("max_intentos", [1, 2, 3])
def test_max_intentos_de_config_menor_o_igual_a_3_se_respeta(max_intentos) -> None:
    errores = [ERROR_A1, ERROR_B, ERROR_C]
    orquestador, *_ = armar(ReviewerConErrores(errores), max_intentos=max_intentos)

    [objetivo] = orquestador.ejecutar(MODULO).objetivos

    assert (objetivo.decision, objetivo.intentos) == ("stalled", max_intentos)
    assert objetivo.motivo_estancado == LIMITE_INTENTOS


def test_config_no_puede_pedir_mas_de_3_intentos() -> None:
    with pytest.raises(ValueError):
        armar(ReviewerConErrores([]), max_intentos=4)


def test_stalled_del_reviewer_se_clasifica_por_limite() -> None:
    orquestador, *_ = armar(
        ReviewerGuionado(TokenTracker(), ["retry", "retry", "stalled"])
    )

    [objetivo] = orquestador.ejecutar(MODULO).objetivos

    assert (objetivo.decision, objetivo.intentos) == ("stalled", 3)
    assert objetivo.motivo_estancado == LIMITE_INTENTOS


@pytest.mark.parametrize(
    ("argumentos", "esperado"),
    [
        (("retry", 1, 3, "aa", None), ("retry", None)),
        (("retry", 2, 3, "aa", "bb"), ("retry", None)),
        (("retry", 2, 3, "aa", "aa"), ("stalled", ERROR_REPETIDO)),
        (("retry", 3, 3, "aa", "bb"), ("stalled", LIMITE_INTENTOS)),
        (("retry", 2, 3, None, None), ("retry", None)),  # null no cuenta como repetido
        (("stalled", 3, 3, "aa", "aa"), ("stalled", ERROR_REPETIDO)),
        (("stalled", 3, 3, None, "aa"), ("stalled", LIMITE_INTENTOS)),
        (("accept", 2, 3, None, "aa"), ("accept", None)),
        (("bug_detectado", 1, 3, "aa", None), ("bug_detectado", None)),
    ],
)
def test_decidir_corte(argumentos, esperado) -> None:
    assert decidir_corte(*argumentos) == esperado


def test_etiqueta_estancado() -> None:
    assert (
        etiqueta_estancado(3, LIMITE_INTENTOS) == "Estancado 3/3 · límite de intentos"
    )
    assert (
        etiqueta_estancado(2, ERROR_REPETIDO) == "Estancado 2/3 · mismo error repetido"
    )


# --- Criterio 3: el Generator recibe solo el último error y el contrato original --


def test_generator_recibe_solo_el_ultimo_error_y_el_contrato_original() -> None:
    tracker = TokenTracker()
    original = json.loads(FakeLLMClient().generar("plan", rol="planner").contenido)[0]
    planner = PlannerSimulado(tracker, plan=[copy.deepcopy(original)])
    espia = GeneratorEspia(tracker)
    reviewer = ReviewerConErrores([ERROR_A1, ERROR_B, None])
    orquestador = Orquestador(planner, espia, reviewer, tracker=tracker)

    orquestador.ejecutar(MODULO)

    # Solo el error del intento anterior; nunca el historial acumulado.
    assert espia.feedbacks == [None, ERROR_A1, ERROR_B]
    # El contrato es el original del Planner en cada intento, aunque el Generator
    # haya modificado el que recibió en el intento anterior.
    assert espia.contratos == [original, original, original]
    assert reviewer.contratos == [original, original, original]
    assert planner.plan == [original]


# --- Criterio 4: el motivo queda en results.json --------------------------------


@pytest.mark.parametrize(
    ("errores", "intentos", "motivo"),
    [
        ([ERROR_A1, ERROR_B, ERROR_C], 3, "limite_intentos"),
        ([ERROR_A1, ERROR_A2], 2, "error_repetido"),
    ],
)
def test_results_json_registra_el_motivo_del_estancado(
    tmp_path: Path, errores, intentos, motivo
) -> None:
    precios = cargar_precios()
    orquestador, *_ = armar(ReviewerConErrores(errores))
    resultado = orquestador.ejecutar(MODULO)

    rutas = escribir_corrida(tmp_path, resultado, orquestador.tracker, precios, "deep")
    results = json.loads(rutas.results.read_text(encoding="utf-8"))

    [funcion] = results["objetivos"]
    assert funcion["decision"] == "stalled"
    assert funcion["motivo_estancado"] == motivo
    assert funcion["metricas"]["iteraciones"] == intentos
    assert results["resumen"]["stalled"] == 1


def test_contrato_run_log_exige_motivo_coherente_con_la_decision() -> None:
    ejemplo = json.loads(
        (
            Path(__file__).parents[2]
            / "contracts"
            / "ejemplos"
            / "run_log.results.json"
        ).read_text(encoding="utf-8")
    )
    objetivo = ejemplo["objetivos"][0]
    assert es_valido(RUN_LOG, ejemplo)

    objetivo.update(decision="stalled", motivo_estancado="error_repetido")
    assert es_valido(RUN_LOG, ejemplo)

    objetivo["motivo_estancado"] = None  # stalled sin motivo
    assert not es_valido(RUN_LOG, ejemplo)

    objetivo.update(decision="accept", motivo_estancado="limite_intentos")
    assert not es_valido(RUN_LOG, ejemplo)

    objetivo["motivo_estancado"] = "otro_motivo"
    assert not es_valido(RUN_LOG, ejemplo)

    del objetivo["motivo_estancado"]
    assert not es_valido(RUN_LOG, ejemplo)
