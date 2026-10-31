"""Script de medición del Explicador (SPK #167), siempre con la IA simulada.

El script es el único que llama a una API real, y solo lo corre una persona; aquí se
prueba con la IA simulada y con clientes falsos (0 tokens, sin red).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from qagent.agents.explicador import RedactorIA, SinExplicacionIA
from qagent.llm.modelos import RespuestaLLM
from qagent.llm.precios import PrecioAgente
from qagent.llm.tracker import TokenTracker
from qagent.storage.exportar_informe import sanitizar_secretos

RUTA = Path(__file__).resolve().parents[2] / "bench_explicador" / "medir_explicador.py"
PRECIO = PrecioAgente("explicador", "openai", "modelo-prueba", 0.10, 0.50)


@pytest.fixture(scope="module")
def medir():
    spec = importlib.util.spec_from_file_location("medir_explicador", RUTA)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo  # dataclasses lo necesita
    spec.loader.exec_module(modulo)
    yield modulo
    sys.modules.pop(spec.name, None)


class ClienteFijo:
    """Responde siempre el mismo texto, con tokens conocidos."""

    def __init__(self, contenido: str) -> None:
        self.contenido = contenido

    def generar(self, prompt: str, rol: str = "") -> RespuestaLLM:
        return RespuestaLLM(self.contenido, 1000, 200, 0.0, "modelo-prueba")


def _motivo(medir, contenido: str) -> str:
    """El motivo real por el que RedactorIA descarta una respuesta del LLM."""
    results, detalle = medir.leer_casos()
    objetivo, funcion = next(
        (o, f) for o, f in medir.hallazgos(results, detalle) if o["decision"]
    )
    redactor = RedactorIA(
        ClienteFijo(contenido), TokenTracker(), PRECIO, tiempo_maximo_s=5
    )
    with pytest.raises(SinExplicacionIA) as error:
        redactor.redactar(objetivo, funcion)
    return str(error.value)


def _respuesta(decision: str, que_hacer: str = "Revisa la función.") -> str:
    return json.dumps(
        {
            "decision": decision,
            "resumen": "La función no cumple lo que promete.",
            "que_se_esperaba": "Lo que dice su documentación.",
            "que_paso": "Devolvió otro valor en los tres intentos.",
            "que_hacer": que_hacer,
        }
    )


def test_la_medicion_simulada_deja_metricas_respuestas_y_resumen(
    medir, tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("QAGENT_FAKE_LLM", "1")
    salida = tmp_path / "resultados"

    datos = medir.main(
        [
            "--salida",
            str(salida),
            "--config-local",
            str(tmp_path / "no-existe.toml"),
            "--repeticiones",
            "2",
        ]
    )

    assert datos["es_simulado"] is True
    assert {p.name for p in salida.iterdir()} == {
        "metricas.json",
        "respuestas.json",
        "resumen.md",
    }
    filas = {f["modelo"]: f for f in datos["por_modelo"]}
    assert "plantilla" in filas and len(filas) >= 3  # plantilla + 2 modelos
    for fila in filas.values():
        assert fila["explicaciones"] in (6, 12)
        assert fila["descartadas_pct"] == 0.0
    assert all(c["respeta_topes"] for c in datos["corridas"])
    assert all(
        r["respeta_tope"]
        for topes in datos["prueba_topes"].values()
        for r in topes.values()
    )
    resumen = (salida / "resumen.md").read_text(encoding="utf-8")
    assert "[SIMULADO]" in resumen and "[MEDIDO]" not in resumen.split("## Por")[2]


def test_los_resultados_no_traen_rutas_de_la_maquina(medir, tmp_path, monkeypatch):
    monkeypatch.setenv("QAGENT_FAKE_LLM", "1")
    salida = tmp_path / "resultados"
    local = str(tmp_path / "no-existe.toml")
    medir.main(
        ["--salida", str(salida), "--config-local", local, "--repeticiones", "1"]
    )

    for archivo in salida.iterdir():
        texto = archivo.read_text(encoding="utf-8")
        assert str(Path.home()) not in texto, archivo.name
        assert "AppData" not in texto and "/home/" not in texto, archivo.name


@pytest.mark.parametrize(
    ("contenido", "categoria"),
    [
        ("No puedo responder en JSON.", "json_invalido"),
        ('["no es un objeto"]', "json_invalido"),
        ('{"decision": "bug_detectado"}', "json_invalido"),
        (_respuesta("stalled"), "decision_distinta"),  # distinta de results.json
        (_respuesta("accept"), "decision_distinta"),  # fuera del enum del contrato
        (
            _respuesta("bug_detectado", "Conviene relajar la aserción para que pase."),
            "relaja_asercion",
        ),
    ],
)
def test_clasifica_los_descartes_con_los_mensajes_reales(
    medir, contenido, categoria
) -> None:
    assert medir.clasificar_descarte(_motivo(medir, contenido)) == categoria


def test_clasifica_tiempo_agotado_presupuesto_y_error_del_llm(medir) -> None:
    assert medir.clasificar_descarte(
        "el LLM no respondió en 60 s (tiempo agotado)"
    ) == ("tiempo_agotado")
    assert medir.clasificar_descarte("se alcanzó el tope de gasto (US$ 1.00)") == (
        "presupuesto"
    )
    assert medir.clasificar_descarte("el LLM falló: ConnectionError: x") == "error_llm"


def test_detecta_rutas_absolutas_y_claves_en_la_entrada(medir) -> None:
    clave = "sk-proj-" + "A1b2C3d4" * 6
    assert sanitizar_secretos(clave) != clave  # el patrón que se quiere detectar

    assert medir.problemas_de_entrada({"traza": [{"feedback": "todo bien"}]}) == []
    assert medir.problemas_de_entrada({"x": "/home/ana/proyecto/a.py"})
    assert medir.problemas_de_entrada({"x": "C:\\Users\\ana\\a.py"})
    assert medir.problemas_de_entrada({"x": [f"OPENAI_API_KEY={clave}"]})


def test_los_casos_fijos_no_llevan_rutas_ni_claves_al_llm(medir) -> None:
    results, detalle = medir.leer_casos()

    for objetivo, funcion in medir.hallazgos(results, detalle):
        entrada = medir.entrada_ia(objetivo, funcion)
        assert medir.problemas_de_entrada(entrada) == [], objetivo["funcion"]


def test_con_topes_minimos_no_llama_al_llm(medir) -> None:
    results, detalle = medir.leer_casos()
    casos = medir.hallazgos(results, detalle)

    topes = medir.probar_topes(PRECIO, casos, {})

    for resultado in topes.values():
        assert resultado == {
            "llamadas_al_llm": 0,
            "cortes_por_tope": len(casos),
            "hallazgos": len(casos),
            "respeta_tope": True,
        }


def test_mide_tokens_costo_y_descartes_por_explicacion(medir, monkeypatch) -> None:
    results, detalle = medir.leer_casos()
    casos = medir.hallazgos(results, detalle)
    respuestas = {
        o["funcion"]: _respuesta(o["decision"] or "sin_veredicto") for o, _ in casos
    }
    respuestas["calcular_envio"] = "texto sin JSON"

    class ClientePorObjetivo:
        def generar(self, prompt: str, rol: str = "") -> RespuestaLLM:
            nombre = next(n for n in respuestas if f'"objetivo": "{n}"' in prompt)
            return RespuestaLLM(respuestas[nombre], 1000, 200, 0.0, "modelo-prueba")

    monkeypatch.setattr(medir, "crear_cliente", lambda *a, **k: ClientePorObjetivo())

    class Presupuesto:
        max_tokens_por_corrida = None
        tope_por_corrida_usd = 1.0

    mediciones, corridas = medir.medir_modelo(
        PRECIO,
        casos,
        {},
        claves=None,
        simulado=False,
        repeticiones=1,
        tiempo_maximo_s=5,
        presupuesto=Presupuesto(),
        run_id=None,
    )

    assert len(mediciones) == len(casos) == 6
    assert all(m.tokens_entrada == 1000 and m.tokens_salida == 200 for m in mediciones)
    assert all(m.costo_usd == PRECIO.costo(1000, 200) for m in mediciones)
    [descartada] = [m for m in mediciones if m.descarte]
    assert (descartada.objetivo, descartada.descarte) == (
        "calcular_envio",
        "json_invalido",
    )
    assert descartada.respuesta_descartada == "texto sin JSON"
    assert all(m.respuesta_descartada is None for m in mediciones if not m.descarte)
    assert corridas[0]["tokens"] == 6 * 1200 and corridas[0]["respeta_topes"]
    [fila] = medir.resumir(mediciones, corridas, None)
    assert fila["descartadas_pct"] == round(100 / 6, 1)
    assert fila["descartes"] == {"json_invalido": 1}


def test_el_costo_de_la_corrida_real_no_cuenta_al_explicador(medir, tmp_path) -> None:
    log = tmp_path / "log.json"
    llamadas = [
        ("planner", 1000, 500, 0.01),
        ("generator", 2000, 400, 0.02),
        ("explicador", 900, 300, 0.005),
    ]
    log.write_text(
        json.dumps(
            {
                "run_id": "r1",
                "es_simulado": False,
                "llamadas": [
                    {
                        "agente": a,
                        "prompt_tokens": e,
                        "completion_tokens": s,
                        "costo_usd": c,
                        "es_estimado": False,
                    }
                    for a, e, s, c in llamadas
                ],
            }
        ),
        encoding="utf-8",
    )

    real = medir.costo_corrida_real(log)

    assert real["tokens"] == 3900
    assert real["costo_usd"] == pytest.approx(0.03)
    assert set(real["por_agente"]) == {"planner", "generator"}


def test_mide_modelos_del_catalogo_con_sus_precios(medir) -> None:
    elegidos = medir.del_catalogo(
        [
            "deepseek/deepseek-flash",
            "deepseek/deepseek-v4-pro",
            "deepseek/deepseek-flash",
        ]
    )

    precios = [precio for _, precio in elegidos]
    assert [(p.proveedor, p.modelo) for p in precios] == [
        ("deepseek", "deepseek-flash"),
        ("deepseek", "deepseek-v4-pro"),
    ]
    flash = medir.catalogo()["deepseek"].modelo("deepseek-flash")
    assert (precios[0].entrada_usd_m, precios[0].salida_usd_m) == (
        flash.entrada_usd_m,
        flash.salida_usd_m,
    )
    assert all(p.agente == "explicador" for p in precios)


@pytest.mark.parametrize(
    ("modelo", "mensaje"),
    [
        ("nadie/modelo", "no está en el catálogo"),
        ("deepseek/no-existe", "no tiene el modelo 'no-existe'"),
        ("deepseek", "no tiene el modelo ''"),
    ],
)
def test_un_modelo_fuera_del_catalogo_dice_cuales_hay(medir, modelo, mensaje) -> None:
    with pytest.raises(SystemExit, match=mensaje):
        medir.del_catalogo([modelo])


def test_con_modelo_del_catalogo_no_mide_los_de_config(
    medir, tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("QAGENT_FAKE_LLM", "1")

    datos = medir.main(
        [
            "--salida",
            str(tmp_path / "resultados"),
            "--config-local",
            str(tmp_path / "no-existe.toml"),
            "--repeticiones",
            "1",
            "--modelo",
            "deepseek/deepseek-flash",
            "deepseek/deepseek-v4-pro",
        ]
    )

    assert [f["modelo"] for f in datos["por_modelo"]] == [
        "plantilla",
        "deepseek-flash",
        "deepseek-v4-pro",
    ]
    assert set(datos["prueba_topes"]) == {"deepseek-flash", "deepseek-v4-pro"}


def test_modelos_y_modelo_no_van_juntos(medir) -> None:
    with pytest.raises(SystemExit):
        medir.argumentos(
            ["--modelos", "planner", "--modelo", "deepseek/deepseek-flash"]
        )


def test_guarda_y_muestra_la_respuesta_que_relaja_una_asercion(
    medir, tmp_path, monkeypatch
) -> None:
    """Para documentar cada descarte: qué dijo el modelo y por qué se cortó."""
    relaja = _respuesta(
        "bug_detectado", "Conviene cambiar el valor esperado por el que devuelve."
    )

    class ClienteQueRelaja:
        def generar(self, prompt: str, rol: str = "") -> RespuestaLLM:
            return RespuestaLLM(relaja, 1000, 200, 0.0, "modelo-prueba")

    monkeypatch.setenv("QAGENT_FAKE_LLM", "1")
    monkeypatch.setattr(medir, "crear_cliente", lambda *a, **k: ClienteQueRelaja())
    salida = tmp_path / "resultados"

    datos = medir.main(
        [
            "--salida",
            str(salida),
            "--config-local",
            str(tmp_path / "no-existe.toml"),
            "--repeticiones",
            "1",
            "--modelo",
            "deepseek/deepseek-flash",
        ]
    )

    relajadas = [d for d in datos["descartadas"] if d["descarte"] == "relaja_asercion"]
    assert relajadas and all(d["respuesta"] == relaja for d in relajadas)
    respuestas = json.loads((salida / "respuestas.json").read_text(encoding="utf-8"))
    assert any(r["respuesta_descartada"] == relaja for r in respuestas)
    resumen = (salida / "resumen.md").read_text(encoding="utf-8")
    assert "## Respuestas descartadas" in resumen
    assert "cambiar el valor esperado por el que devuelve" in resumen


def test_un_error_del_llm_no_guarda_respuesta(medir, monkeypatch) -> None:
    results, detalle = medir.leer_casos()
    casos = medir.hallazgos(results, detalle)[:1]

    class ClienteQueFalla:
        def generar(self, prompt: str, rol: str = "") -> RespuestaLLM:
            raise RuntimeError("sin red")

    class Presupuesto:
        max_tokens_por_corrida = None
        tope_por_corrida_usd = None

    monkeypatch.setattr(medir, "crear_cliente", lambda *a, **k: ClienteQueFalla())

    [medicion], _ = medir.medir_modelo(
        PRECIO,
        casos,
        {},
        claves=None,
        simulado=False,
        repeticiones=1,
        tiempo_maximo_s=5,
        presupuesto=Presupuesto(),
        run_id=None,
    )

    assert medicion.descarte == "error_llm"
    assert medicion.respuesta_descartada is None
