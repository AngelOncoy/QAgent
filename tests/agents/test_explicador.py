"""Agente Explicador con plantillas, sin IA (HU-32, ADR-008)."""

from __future__ import annotations

import copy
import re

import pytest

from qagent import contracts
from qagent.agents import explicador
from qagent.agents.explicador import (
    BUG,
    CORRIDA_NUEVA,
    ESTANCADA,
    LAUNDERING,
    SIN_VEREDICTO,
    explicar_corrida,
    explicar_objetivo,
    tipo_de_hallazgo,
)
from qagent.contracts.validacion_semantica import _propone_relajar_o_cambiar_esperado

RUN_ID = "20261028-120000-abcd"
CAMPOS_TEXTO = ("resumen", "que_se_esperaba", "que_paso", "que_hacer")
JERGA = re.compile(r"assert|traceback|fixture|pytest|stack", re.IGNORECASE)


def _objetivo(**cambios):
    base = {
        "modulo": "tienda/precios.py",
        "funcion": "calcular_descuento",
        "tipo": "funcion",
        "critical": False,
        "decision": "bug_detectado",
        "motivo_estancado": None,
        "motivo_sin_veredicto": None,
        "laundering_detectado": False,
        "metricas": {"iteraciones": 2},
    }
    base.update(cambios)
    return base


def _funcion(esperado="80.0", obtenido="75.0"):
    return {
        "modulo": "tienda/precios.py",
        "funcion": "calcular_descuento",
        "contrato": {
            "casos": [
                {
                    "id": "descuento_normal",
                    "descripcion": "Aplica el porcentaje al precio",
                    "entrada": {"precio": 100.0, "porcentaje": 20.0},
                    "valor_esperado": 80.0,
                },
                {
                    "id": "porcentaje_invalido",
                    "descripcion": "Un porcentaje mayor a 100 lanza ValueError",
                    "entrada": {"precio": 100.0, "porcentaje": 150.0},
                    "excepcion": "ValueError",
                },
            ]
        },
        "codigo": None,
        "traza": None,
        "intentos": [
            {"intento": 1, "ejecucion": None},
            {
                "intento": 2,
                "ejecucion": {
                    "casos": [
                        {"nombre": "test_porcentaje_invalido", "resultado": "ok"},
                        {
                            "nombre": "test_descuento_normal",
                            "resultado": "fallo",
                            "esperado": esperado,
                            "obtenido": obtenido,
                        },
                    ]
                },
            },
        ],
    }


def _corrida(*objetivos, funciones=()):
    results = {"run_id": RUN_ID, "objetivos": list(objetivos)}
    detalle = {"run_id": RUN_ID, "funciones": list(funciones)}
    return results, detalle


def _textos(explicacion):
    return " ".join(explicacion[c] for c in CAMPOS_TEXTO)


# --- Tipo de hallazgo ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("cambios", "tipo"),
    [
        ({"decision": "accept"}, None),
        ({"decision": "bug_detectado"}, BUG),
        ({"decision": "stalled", "motivo_estancado": "limite_intentos"}, ESTANCADA),
        ({"decision": None}, SIN_VEREDICTO),
        ({"decision": "requiere_corrida_nueva"}, CORRIDA_NUEVA),
        # Laundering no es una decisión: tiene prioridad sobre la que haya.
        ({"decision": "stalled", "laundering_detectado": True}, LAUNDERING),
        ({"decision": "bug_detectado", "laundering_detectado": True}, LAUNDERING),
        ({"decision": "accept", "laundering_detectado": True}, None),
    ],
)
def test_tipo_de_hallazgo(cambios, tipo):
    assert tipo_de_hallazgo(_objetivo(**cambios)) == tipo


# --- Una plantilla por tipo ----------------------------------------------------------


def test_bug_cita_esperado_obtenido_entrada_e_intentos():
    exp = explicar_objetivo(_objetivo(), _funcion(), RUN_ID)

    assert exp["decision"] == "bug_detectado"
    assert "80.0" in exp["que_paso"] and "75.0" in exp["que_paso"]
    assert "precio = 100.0, porcentaje = 20.0" in exp["que_paso"]
    assert "(2 intentos)" in exp["que_paso"]
    assert "aplica el porcentaje al precio" in exp["que_se_esperaba"]
    assert "código" in exp["que_hacer"]


def test_bug_sin_detalle_usa_solo_results():
    exp = explicar_objetivo(_objetivo(), None)

    assert exp["decision"] == "bug_detectado"
    assert "no se comportó como prometía" in exp["que_paso"]
    assert "documentación y sus tipos" in exp["que_se_esperaba"]


def test_bug_de_excepcion_usa_el_contrato_si_falta_el_esperado():
    funcion = _funcion(esperado=None, obtenido="None")
    funcion["intentos"][1]["ejecucion"]["casos"][1]["nombre"] = (
        "test_porcentaje_invalido"
    )

    exp = explicar_objetivo(_objetivo(), funcion)

    assert "un aviso de error (ValueError)" in exp["que_paso"]


@pytest.mark.parametrize(
    ("motivo", "texto"),
    [
        ("limite_intentos", "no lo logró"),
        ("error_repetido", "mismo motivo"),
        ("limite_tokens", "tope de gasto"),
    ],
)
def test_estancada_por_motivo(motivo, texto):
    objetivo = _objetivo(decision="stalled", motivo_estancado=motivo)

    exp = explicar_objetivo(objetivo, _funcion())

    assert exp["decision"] == "stalled"
    assert texto in exp["que_paso"]
    if motivo == "limite_tokens":
        assert "Configuración" in exp["que_hacer"]
    else:
        assert "no significa que tu código tenga un error" in exp["que_hacer"]


@pytest.mark.parametrize(
    ("motivo", "texto"),
    [
        ("tiempo_agotado", "tardó demasiado"),
        ("error_contrato_planner", "incompleto"),
        ("error_planner", "planificar"),
        (None, "se detuvo"),
    ],
)
def test_sin_veredicto_por_motivo(motivo, texto):
    objetivo = _objetivo(decision=None, motivo_sin_veredicto=motivo)

    exp = explicar_objetivo(objetivo, None)

    assert exp["decision"] is None
    assert texto in exp["que_paso"]
    assert "no dice nada sobre si" in exp["que_hacer"]


def test_laundering_explica_que_la_prueba_se_debilito_y_se_descarto():
    objetivo = _objetivo(decision="stalled", laundering_detectado=True)
    objetivo["motivo_estancado"] = "limite_intentos"

    exp = explicar_objetivo(objetivo, _funcion())

    assert exp["decision"] == "stalled"  # eco de results.json, no un valor nuevo
    assert "debilitado" in exp["resumen"]
    assert "descartó" in exp["que_paso"]
    assert "no cuenta como aprobada" in exp["que_paso"]
    assert "sigue siendo lo que debe cumplirse" in exp["que_hacer"]


def test_requiere_corrida_nueva():
    exp = explicar_objetivo(_objetivo(decision="requiere_corrida_nueva"), None)

    assert exp["decision"] == "requiere_corrida_nueva"
    assert "corrida nueva" in exp["que_hacer"]


def test_endpoint_se_nombra_como_ruta():
    objetivo = _objetivo(funcion="GET /items", tipo="endpoint")

    exp = explicar_objetivo(objetivo, None)

    assert "la ruta GET /items" in exp["resumen"]


def test_un_objetivo_aceptado_no_se_explica():
    with pytest.raises(ValueError):
        explicar_objetivo(_objetivo(decision="accept"), None)


# --- Reglas de todas las plantillas --------------------------------------------------


def _todas():
    """Una explicación de cada plantilla y motivo, con y sin detalle."""
    variantes = [
        _objetivo(),
        _objetivo(decision="requiere_corrida_nueva"),
        _objetivo(
            decision="stalled",
            laundering_detectado=True,
            motivo_estancado="error_repetido",
        ),
        _objetivo(decision="bug_detectado", laundering_detectado=True),
    ]
    variantes += [
        _objetivo(decision="stalled", motivo_estancado=m)
        for m in ("limite_intentos", "error_repetido", "limite_tokens")
    ]
    variantes += [
        _objetivo(decision=None, motivo_sin_veredicto=m)
        for m in ("tiempo_agotado", "error_contrato_planner", "error_planner", None)
    ]
    return [
        explicar_objetivo(o, f, RUN_ID) for o in variantes for f in (_funcion(), None)
    ]


def test_todas_cumplen_el_contrato_con_origen_plantilla():
    for exp in _todas():
        contracts.validar(contracts.EXPLANATION_V1, exp)
        assert exp["origen"] == "plantilla"
        assert exp["modelo"] is None


def test_ninguna_usa_jerga():
    for exp in _todas():
        assert not JERGA.search(_textos(exp)), _textos(exp)


def test_ninguna_sugiere_relajar_ni_cambiar_el_esperado():
    for exp in _todas():
        for campo in CAMPOS_TEXTO:
            assert not _propone_relajar_o_cambiar_esperado(exp[campo]), exp[campo]


def test_quita_claves_y_rutas_absolutas():
    clave = "sk-ant-" + "a" * 30
    funcion = _funcion(obtenido=f"{clave} en C:\\Users\\ana\\proy\\precios.py")
    objetivo = _objetivo(modulo="/home/ana/proy/precios.py")
    objetivo["funcion"] = funcion["funcion"]
    funcion["modulo"] = objetivo["modulo"]

    exp = explicar_objetivo(objetivo, funcion)

    assert clave not in exp["que_paso"]
    assert "C:\\Users" not in exp["que_paso"] and "precios.py" in exp["que_paso"]
    assert exp["modulo"] == "precios.py"


# --- La corrida completa -------------------------------------------------------------


def test_explicar_corrida_omite_aceptados_y_valida_el_archivo():
    aceptado = _objetivo(funcion="otra", decision="accept")
    results, detalle = _corrida(aceptado, _objetivo(), funciones=[_funcion()])

    resultado = explicar_corrida(results, detalle)

    assert resultado.descartadas == []
    assert resultado.datos["run_id"] == RUN_ID
    assert [e["objetivo"] for e in resultado.datos["explicaciones"]] == [
        "calcular_descuento"
    ]
    contracts.validar_explicaciones(resultado.datos, results_confiables=results)


def test_explicar_corrida_no_modifica_sus_entradas():
    results, detalle = _corrida(_objetivo(), funciones=[_funcion()])
    copias = copy.deepcopy((results, detalle))

    explicar_corrida(results, detalle)

    assert (results, detalle) == copias


def test_una_explicacion_invalida_se_descarta_sin_tumbar_las_demas(monkeypatch):
    def relaja(h):
        return {
            "resumen": "x",
            "que_se_esperaba": "x",
            "que_paso": "x",
            "que_hacer": "Hay que cambiar el valor esperado.",
        }

    monkeypatch.setitem(explicador._PLANTILLAS, ESTANCADA, relaja)
    estancada = _objetivo(
        funcion="otra", decision="stalled", motivo_estancado="limite_intentos"
    )
    results, detalle = _corrida(estancada, _objetivo(), funciones=[_funcion()])

    resultado = explicar_corrida(results, detalle)

    assert [e["objetivo"] for e in resultado.datos["explicaciones"]] == [
        "calcular_descuento"
    ]
    assert len(resultado.descartadas) == 1
    assert resultado.descartadas[0].startswith("otra:")


def test_corrida_sin_hallazgos_da_lista_vacia():
    results, _ = _corrida(_objetivo(decision="accept"))

    resultado = explicar_corrida(results)

    assert resultado.datos["explicaciones"] == []
    contracts.validar(contracts.EXPLICACIONES, resultado.datos)
