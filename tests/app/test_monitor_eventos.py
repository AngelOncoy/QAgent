"""Traducción de los eventos de la corrida a filas del Monitor (HU-09)."""

from __future__ import annotations

from pyagent.app.monitor_eventos import LARGO_MAXIMO, a_evento_bitacora, a_fila_monitor


def evento(**cambios) -> dict:
    base = {
        "agente": "reviewer",
        "archivo": "bench/banco_mvp.py",
        "funcion": "clasificar_edad",
        "mensaje": "Ejecutando en sandbox (intento 1)",
        "estado": "ejecutar_revisar",
        "tipo": "agente",
        "hora": "2026-10-10T02:00:00-05:00",
        "datos": None,
        "progreso": {"hechos": 1, "total": 6},
    }
    return {**base, **cambios}


def test_las_transiciones_internas_no_se_muestran() -> None:
    assert a_fila_monitor(evento(agente="orquestador", tipo="transicion")) is None


def test_fila_normal_lleva_lugar_texto_y_progreso() -> None:
    fila = a_fila_monitor(evento())

    assert fila["a"] == "reviewer"
    assert (fila["f"], fila["fn"]) == ("bench/banco_mvp.py", "clasificar_edad")
    assert (fila["hechos"], fila["total"]) == (1, 6)
    assert fila["guard"] is None


def test_bug_detectado_es_alerta_de_oraculo() -> None:
    fila = a_fila_monitor(
        evento(tipo="veredicto", datos={"decision": "bug_detectado", "intento": 1})
    )

    assert fila["a"] == "oracle"
    assert fila["guard"][1] == "BUG"
    assert "bug" in fila["t"]


def test_estancado_muestra_la_etiqueta_de_hu14() -> None:
    etiqueta = "Estancado 3/3 · límite de intentos"
    fila = a_fila_monitor(
        evento(
            tipo="veredicto",
            mensaje=etiqueta,
            datos={"decision": "stalled", "intento": 3, "etiqueta": etiqueta},
        )
    )

    assert fila["a"] == "stuck"
    assert fila["guard"] == [etiqueta, "ESTANCADO"]


def test_laundering_es_alerta_del_guardian() -> None:
    fila = a_fila_monitor(
        evento(mensaje="Reintento: ... 🔴 ASSERTION LAUNDERING DETECTADO: ...")
    )

    assert fila["a"] == "guard"
    assert fila["guard"][1] == "RECHAZADA"


def test_el_texto_largo_se_recorta() -> None:
    fila = a_fila_monitor(evento(mensaje="x" * 5000))

    assert len(fila["t"]) == LARGO_MAXIMO
    assert fila["t"].endswith("…")


def test_avisos_del_orquestador_y_fallos() -> None:
    aviso = a_fila_monitor(evento(agente="orquestador", funcion=None))
    fallo = a_fila_monitor(evento(agente="orquestador", tipo="fallo"))

    assert aviso["a"] == "sistema"
    assert fallo["a"] == "stuck"


def test_formato_para_la_consola() -> None:
    fila = a_fila_monitor(
        evento(tipo="veredicto", datos={"decision": "bug_detectado", "intento": 1})
    )

    linea = a_evento_bitacora(fila)

    assert linea["tipo"] == "oracle"  # tipo de alerta: sale como WARNING
    assert linea["progreso"] == "1/6"
    assert "[Oráculo" in linea["mensaje"]
