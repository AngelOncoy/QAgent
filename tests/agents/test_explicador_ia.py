"""Explicaciones redactadas por un LLM con la plantilla de respaldo (#166, ADR-008).

Todas usan la IA simulada (`FakeLLMClient`, respuestas en `ia_simulada.json`) o un
cliente de prueba: ninguna llama a una API real.
"""

from __future__ import annotations

import json
import threading

import pytest

from qagent import contracts
from qagent.agents.explicador import (
    LARGO_MAXIMO_FEEDBACK,
    RedactorIA,
    SinExplicacionIA,
    entrada_ia,
    explicar_corrida,
)
from qagent.llm import FakeLLMClient, PrecioAgente, RespuestaLLM, TokenTracker
from qagent.llm.fake import MARCA_EXPLICACION

RUN_ID = "20261029-120000-abcd"
MODULO = "tienda/explicador_ia.py"
DOCSTRING = "Aplica un porcentaje de descuento.\n\nReturns: el precio final."
PRECIO = PrecioAgente("explicador", "openai", "modelo-explicador", 0.10, 0.50)
# Armados en tiempo de ejecución: no son claves reales.
SECRETO = "sk-" + "x" * 32
RUTA_ABSOLUTA = "C:\\Users\\alguien\\proyecto\\tienda\\explicador_ia.py"


def _objetivo(nombre="valida", **cambios):
    base = {
        "modulo": MODULO,
        "funcion": nombre,
        "tipo": "funcion",
        "critical": False,
        "decision": "bug_detectado",
        "motivo_estancado": None,
        "motivo_sin_veredicto": None,
        "laundering_detectado": False,
        "metricas": {
            "iteraciones": 2,
            "cobertura_lineas": 80.0,
            "cobertura_ramas": 50.0,
        },
    }
    base.update(cambios)
    return base


def _funcion(nombre="valida"):
    return {
        "modulo": MODULO,
        "funcion": nombre,
        "contrato": {
            "casos": [
                {
                    "id": "descuento_normal",
                    "descripcion": "Aplica el porcentaje al precio",
                    "entrada": {"precio": 100.0, "porcentaje": 20.0},
                    "valor_esperado": 80.0,
                    "origen": "docstring",
                }
            ]
        },
        "codigo": "def valida(): ...",
        "traza": None,
        "intentos": [
            {
                "intento": 1,
                "decision": "retry",
                "estado_sandbox": "fallo",
                "tipo_fallo": "error_test",
                "laundering_detectado": False,
                "feedback": f"ImportError en {RUTA_ABSOLUTA} con OPENAI_API_KEY={SECRETO}",
                "ejecucion": None,
            },
            {
                "intento": 2,
                "decision": "bug_detectado",
                "estado_sandbox": "fallo",
                "tipo_fallo": "bug_codigo",
                "laundering_detectado": False,
                "feedback": "x" * 2000 + " assert 75.0 == 80.0",
                "ejecucion": {
                    "casos": [
                        {
                            "nombre": "test_descuento_normal",
                            "resultado": "fallo",
                            "esperado": "80.0",
                            "obtenido": "75.0",
                        }
                    ]
                },
            },
        ],
    }


def _corrida(*nombres, **cambios):
    results = {
        "run_id": RUN_ID,
        "objetivos": [_objetivo(n, **cambios) for n in nombres],
    }
    detalle = {"run_id": RUN_ID, "funciones": [_funcion(n) for n in nombres]}
    return results, detalle


class ClienteGuardaPrompts(FakeLLMClient):
    """IA simulada que guarda los prompts y puede contar tokens."""

    def __init__(self, tokens=(0, 0), **kwargs):
        super().__init__(modelo="modelo-explicador", **kwargs)
        self.prompts: list[str] = []
        self.tokens = tokens

    def generar(self, prompt, rol="generator"):
        self.prompts.append(prompt)
        respuesta = super().generar(prompt, rol)
        respuesta.tokens_entrada, respuesta.tokens_salida = self.tokens
        return respuesta


class ClienteQueFalla:
    def generar(self, prompt, rol="generator"):
        raise RuntimeError(f"HTTP 500 con clave {SECRETO}")


class ClienteLento:
    def __init__(self):
        self.soltar = threading.Event()

    def generar(self, prompt, rol="generator"):
        self.soltar.wait(5)
        return RespuestaLLM("{}", 0, 0, 0.0, "modelo-explicador")


def _redactor(cliente=None, tracker=None, **opciones):
    opciones.setdefault("tiempo_maximo_s", 5)
    return RedactorIA(
        cliente or ClienteGuardaPrompts(),
        tracker or TokenTracker(),
        PRECIO,
        es_simulado=True,
        **opciones,
    )


def _explicar(*nombres, redactor=None, **cambios):
    results, detalle = _corrida(*nombres, **cambios)
    docstrings = {(MODULO, n): DOCSTRING for n in nombres}
    return explicar_corrida(results, detalle, redactor or _redactor(), docstrings)


def _unica(resultado):
    (explicacion,) = resultado.datos["explicaciones"]
    return explicacion


# --- Respuesta válida --------------------------------------------------------------


def test_explicacion_valida_lleva_origen_ia_y_modelo():
    resultado = _explicar("valida")

    explicacion = _unica(resultado)
    assert explicacion["origen"] == "ia"
    assert explicacion["modelo"] == "modelo-explicador"
    assert explicacion["decision"] == "bug_detectado"
    assert explicacion["que_paso"].startswith("En los 2 intentos")
    assert explicacion["run_id"] == RUN_ID
    assert resultado.respaldos == []
    contracts.validar_explicaciones(
        resultado.datos, results_confiables=_corrida("valida")[0]
    )


def test_sin_grabacion_la_ia_simulada_repite_la_decision():
    explicacion = _unica(_explicar("otra_funcion", decision="stalled"))
    assert explicacion["origen"] == "ia"
    assert explicacion["decision"] == "stalled"


# --- Respaldo con la plantilla -----------------------------------------------------


@pytest.mark.parametrize(
    ("objetivo", "motivo"),
    [
        ("json_invalido", "no es JSON"),
        ("decision_distinta", "decision"),
        ("relaja_asercion", "relajar"),
    ],
)
def test_respuesta_no_valida_usa_la_plantilla(objetivo, motivo):
    resultado = _explicar(objetivo)

    explicacion = _unica(resultado)
    assert explicacion["origen"] == "plantilla"
    assert explicacion["modelo"] is None
    assert explicacion["decision"] == "bug_detectado"
    (respaldo,) = resultado.respaldos
    assert respaldo.startswith(f"{objetivo}: ")
    assert motivo in respaldo


def test_error_del_cliente_usa_la_plantilla_sin_filtrar_la_clave():
    resultado = _explicar("valida", redactor=_redactor(ClienteQueFalla()))

    assert _unica(resultado)["origen"] == "plantilla"
    (respaldo,) = resultado.respaldos
    assert "RuntimeError" in respaldo
    assert SECRETO not in respaldo


def test_tiempo_agotado_usa_la_plantilla():
    cliente = ClienteLento()
    try:
        resultado = _explicar(
            "valida", redactor=_redactor(cliente, tiempo_maximo_s=0.05)
        )
    finally:
        cliente.soltar.set()

    assert _unica(resultado)["origen"] == "plantilla"
    assert "tiempo agotado" in resultado.respaldos[0]


def test_corrida_cancelada_usa_la_plantilla_sin_llamar():
    cliente = ClienteGuardaPrompts()
    resultado = _explicar("valida", redactor=_redactor(cliente, cancelado=lambda: True))

    assert _unica(resultado)["origen"] == "plantilla"
    assert cliente.prompts == []


# --- Presupuesto -------------------------------------------------------------------


def test_presupuesto_de_tokens_agotado_no_llama_al_llm():
    tracker = TokenTracker()
    tracker.registrar("generator", "m", 900, 50)
    cliente = ClienteGuardaPrompts()
    resultado = _explicar(
        "valida", redactor=_redactor(cliente, tracker, max_tokens=1000)
    )

    assert _unica(resultado)["origen"] == "plantilla"
    assert "presupuesto de tokens" in resultado.respaldos[0]
    assert cliente.prompts == []
    assert tracker.total_tokens == 950


def test_tope_en_usd_agotado_no_llama_al_llm():
    tracker = TokenTracker()
    tracker.registrar("generator", "m", 10, 10, costo_usd=0.99999)
    cliente = ClienteGuardaPrompts()
    resultado = _explicar("valida", redactor=_redactor(cliente, tracker, tope_usd=1.0))

    assert _unica(resultado)["origen"] == "plantilla"
    assert "tope de gasto" in resultado.respaldos[0]
    assert cliente.prompts == []


def test_corta_cuando_la_siguiente_llamada_pasaria_el_tope_de_tokens():
    tracker = TokenTracker()
    cliente = ClienteGuardaPrompts(tokens=(2500, 200))
    redactor = _redactor(cliente, tracker, max_tokens=4000)

    resultado = _explicar("valida", "otra_funcion", redactor=redactor)

    origenes = [e["origen"] for e in resultado.datos["explicaciones"]]
    assert origenes == ["ia", "plantilla"]
    assert tracker.total_tokens <= 4000


# --- Tokens y costo ----------------------------------------------------------------


def test_registra_tokens_y_costo_como_agente_explicador():
    tracker = TokenTracker()
    cliente = ClienteGuardaPrompts(tokens=(1000, 200))
    _explicar("valida", redactor=_redactor(cliente, tracker))

    (llamada,) = tracker.llamadas
    assert llamada.agente == "explicador"
    assert llamada.funcion == "valida"
    assert llamada.costo_usd == PRECIO.costo(1000, 200)
    assert tracker.totales_por_agente()["explicador"]["llamadas"] == 1


# --- Entrada: todos los intentos y sin secretos ------------------------------------


def _entrada_enviada(cliente):
    (prompt,) = cliente.prompts
    linea = next(
        lin for lin in prompt.splitlines() if lin.startswith(MARCA_EXPLICACION)
    )
    return prompt, json.loads(linea[len(MARCA_EXPLICACION) :])


def test_la_entrada_incluye_todos_los_intentos_y_no_tiene_secretos():
    cliente = ClienteGuardaPrompts()
    _explicar("valida", redactor=_redactor(cliente))
    prompt, entrada = _entrada_enviada(cliente)

    assert [i["intento"] for i in entrada["traza"]] == [1, 2]
    assert [i["tipo_fallo"] for i in entrada["traza"]] == ["error_test", "bug_codigo"]
    assert all(len(i["feedback"]) <= LARGO_MAXIMO_FEEDBACK for i in entrada["traza"])
    assert entrada["traza"][1]["feedback"].endswith("assert 75.0 == 80.0")
    assert entrada["docstring"] == DOCSTRING
    assert entrada["casos"][0]["valor_esperado"] == 80.0
    assert entrada["primer_caso_fallido"] == {
        "caso": "test_descuento_normal",
        "esperado": "80.0",
        "obtenido": "75.0",
    }
    assert entrada["cobertura"] == {"lineas": 80.0, "ramas": 50.0}
    assert entrada["laundering_detectado"] is False
    # Sin claves, sin rutas absolutas y sin el código del proyecto.
    assert SECRETO not in prompt
    assert "C:\\" not in prompt and "Users" not in prompt
    assert "def valida" not in prompt


def test_entrada_sin_detalle_se_arma_con_results():
    entrada = entrada_ia(_objetivo())
    assert entrada["traza"] == []
    assert entrada["primer_caso_fallido"] is None
    assert entrada["decision"] == "bug_detectado"


def test_redactar_lanza_el_motivo_si_no_hay_explicacion():
    with pytest.raises(SinExplicacionIA, match="no es JSON"):
        _redactor().redactar(_objetivo("json_invalido"), _funcion("json_invalido"))
