"""Script de medición del Recomendador (SPK #201), siempre con la IA simulada.

El script es el único (junto con el del Explicador) que llama a una API real, y solo lo
corre una persona; aquí se prueba con la IA simulada y con clientes falsos (0 tokens,
sin red).
"""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from qagent.agents.recomendador_ia import RecomendadorIA
from qagent.llm.modelos import RespuestaLLM
from qagent.llm.precios import PrecioAgente
from qagent.llm.tracker import TokenTracker

RUTA = (
    Path(__file__).resolve().parents[2] / "bench_recomendador" / "medir_recomendador.py"
)
PRECIO = PrecioAgente("recomendador", "openai", "modelo-prueba", 0.10, 0.50)


@pytest.fixture(scope="module")
def medir():
    spec = importlib.util.spec_from_file_location("medir_recomendador", RUTA)
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


def _recomendador(cliente) -> RecomendadorIA:
    return RecomendadorIA(cliente, TokenTracker(), PRECIO, tiempo_maximo_s=5)


def _respuesta(*tipos: str) -> str:
    return json.dumps(
        {"recomendaciones": [{"tipo_prueba": t, "motivo": f"Por {t}."} for t in tipos]}
    )


def test_hay_tres_proyectos_de_muestra_con_recomendaciones_distintas(medir):
    proyectos = medir.leer_proyectos()

    assert set(proyectos) == {"fastapi", "mixto", "solo_funciones"}
    tipos = {
        nombre: [r["tipo_prueba"] for r in reglas["recomendaciones"]]
        for nombre, (_, reglas) in proyectos.items()
    }
    assert tipos["solo_funciones"] == ["funcion", "mutacion"]
    assert tipos["fastapi"] == ["endpoint", "mutacion"]
    assert tipos["mixto"] == ["endpoint", "funcion", "mutacion"]


def test_mide_tokens_costo_latencia_y_cambios_de_orden_y_motivo(medir):
    proyeccion, reglas = medir.leer_proyectos()["mixto"]
    # Las reglas dan endpoint, funcion y mutacion: la IA los reordena y omite uno.
    cliente = ClienteFijo(_respuesta("funcion", "endpoint"))

    m = medir.medir_una("mixto", proyeccion, reglas, "m", 1, _recomendador(cliente))

    assert m.usada and m.descarte is None
    assert (m.tokens_entrada, m.tokens_salida) == (1000, 200)
    assert m.costo_usd == pytest.approx(0.0002)  # 1000 × 0,10 + 200 × 0,50 por millón
    assert m.latencia_s >= 0
    assert m.orden_cambia
    assert m.tipos_omitidos == ["mutacion"]
    assert m.motivo_cambia


def test_sin_cambios_cuando_la_ia_repite_las_reglas(medir):
    proyeccion, reglas = medir.leer_proyectos()["solo_funciones"]
    igual = json.dumps(
        {
            "recomendaciones": [
                {"tipo_prueba": r["tipo_prueba"], "motivo": r["motivo"]}
                for r in reglas["recomendaciones"]
            ]
        }
    )

    m = medir.medir_una(
        "solo_funciones", proyeccion, reglas, "m", 1, _recomendador(ClienteFijo(igual))
    )

    assert m.usada
    assert not m.orden_cambia and not m.tipos_omitidos and not m.motivo_cambia


@pytest.mark.parametrize(
    ("contenido", "descarte"),
    [
        ("no es json", "json_invalido"),
        (_respuesta("funcion", "funcion"), "contrato_invalido"),
        (_respuesta("endpoint"), "tipo_no_permitido"),  # solo_funciones no tiene
        (_respuesta(), "sin_recomendaciones"),
    ],
)
def test_una_respuesta_descartada_cuenta_su_consumo_y_su_motivo(
    medir, contenido, descarte
):
    proyeccion, reglas = medir.leer_proyectos()["solo_funciones"]

    m = medir.medir_una(
        "solo_funciones",
        proyeccion,
        reglas,
        "m",
        1,
        _recomendador(ClienteFijo(contenido)),
    )

    assert not m.usada
    assert m.descarte == descarte
    assert m.tokens_entrada == 1000  # el consumo cuenta aunque se descarte
    assert m.respuesta_descartada


def test_clasifica_los_motivos_de_descarte(medir):
    assert medir.clasificar_descarte("el LLM no respondió (tiempo agotado)") == (
        "tiempo_agotado"
    )
    assert medir.clasificar_descarte("el LLM falló: ConnectionError: x") == "error_llm"
    assert medir.clasificar_descarte("algo raro") == "otro"


def test_la_entrada_no_lleva_rutas_absolutas_ni_claves(medir):
    for proyeccion, reglas in medir.leer_proyectos().values():
        from qagent.agents.recomendador_ia import entrada_ia

        assert medir.problemas_de_entrada(entrada_ia(proyeccion, reglas)) == []

    sucia = {"ruta": "C:\\Users\\alguien\\proyecto", "clave": "sk-" + "x" * 32}
    assert len(medir.problemas_de_entrada(sucia)) == 2


def test_resumir_calcula_percentiles_y_conteos(medir):
    proyeccion, reglas = medir.leer_proyectos()["mixto"]
    mediciones = [
        medir.medir_una(
            "mixto",
            proyeccion,
            reglas,
            "m",
            i,
            _recomendador(ClienteFijo(_respuesta("funcion", "endpoint"))),
        )
        for i in range(1, 4)
    ]

    resumen = medir.resumir(mediciones)

    assert resumen["llamadas"] == 3 and resumen["usadas"] == 3
    assert resumen["tokens_entrada"] == 3000
    assert resumen["cambia_orden"] == 3 and resumen["omite_tipos"] == 3
    assert resumen["latencia_p95_s"] >= resumen["latencia_p50_s"]


def test_corre_completa_con_la_ia_simulada_y_deja_los_archivos(
    medir, tmp_path, monkeypatch
):
    monkeypatch.setenv("QAGENT_FAKE_LLM", "1")
    salida = tmp_path / "resultados"

    datos = medir.main(
        ["--repeticiones", "1", "--salida", str(salida), "--config-local", "no.toml"]
    )

    assert datos["simulado"]
    for nombre in ("metricas.json", "respuestas.json", "resumen.md"):
        assert (salida / nombre).is_file()
    resumen = (salida / "resumen.md").read_text(encoding="utf-8")
    assert "[SIMULADO]" in resumen
    assert "no sirven para decidir" in resumen
    metricas = json.loads((salida / "metricas.json").read_text(encoding="utf-8"))
    assert set(metricas["proyectos"]) == {"fastapi", "mixto", "solo_funciones"}


def test_ningun_resultado_lleva_claves(medir, tmp_path, monkeypatch):
    monkeypatch.setenv("QAGENT_FAKE_LLM", "1")
    secreto = "sk-" + "x" * 32

    medir.escribir(tmp_path, "r.md", f"Usó {secreto} para llamar", None)

    assert secreto not in (tmp_path / "r.md").read_text(encoding="utf-8")


def test_la_planilla_a_ciegas_oculta_el_origen_y_se_puntua(
    medir, tmp_path, monkeypatch
):
    monkeypatch.setenv("QAGENT_FAKE_LLM", "1")
    medir.main(
        ["--repeticiones", "1", "--salida", str(tmp_path), "--config-local", "no.toml"]
    )
    revision = tmp_path / "revision"
    planilla = revision / "planilla.csv"
    texto = planilla.read_text(encoding="utf-8-sig")
    assert "ia:" not in texto  # el origen solo está en clave.json
    clave = json.loads((revision / "clave.json").read_text(encoding="utf-8"))
    assert all(set(v) == {"A", "B"} for v in clave.values())

    with open(planilla, encoding="utf-8-sig", newline="") as f:
        filas = list(csv.DictReader(f, delimiter=";"))
    assert filas
    # Una persona prefiere siempre la opción de la IA y la puntúa más alto.
    for fila in filas:
        lado_ia = "A" if clave[fila["caso"]]["A"].startswith("ia:") else "B"
        fila["util_A"], fila["util_B"] = ("3", "2") if lado_ia == "A" else ("2", "3")
        fila["preferida"] = lado_ia
    with open(
        revision / "planilla-ana.csv", "w", encoding="utf-8-sig", newline=""
    ) as f:
        escritor = csv.DictWriter(f, list(filas[0]), delimiter=";")
        escritor.writeheader()
        escritor.writerows(filas)

    datos = medir.puntuar(tmp_path)

    assert datos["revisores"] == 1
    assert datos["utilidad_promedio"] == {"reglas": 2.0, "ia": 3.0}
    assert datos["preferencias"] == {"ia": len(filas)}
    assert (revision / "resultado.md").is_file()


def test_puntuar_pide_completar_la_planilla(medir, tmp_path, monkeypatch):
    monkeypatch.setenv("QAGENT_FAKE_LLM", "1")
    medir.main(
        ["--repeticiones", "1", "--salida", str(tmp_path), "--config-local", "no.toml"]
    )
    revision = tmp_path / "revision"
    (revision / "planilla-ana.csv").write_text(
        (revision / "planilla.csv").read_text(encoding="utf-8-sig"),
        encoding="utf-8-sig",
    )

    with pytest.raises(SystemExit, match="falta un 1, 2 o 3"):
        medir.puntuar(tmp_path)
