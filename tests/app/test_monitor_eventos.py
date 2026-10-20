"""Traducción de los eventos de la corrida a filas del Monitor (HU-09)."""

from __future__ import annotations

from qagent.app.monitor_eventos import LARGO_MAXIMO, a_evento_bitacora, a_fila_monitor


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
    # Un fallo controlado no es el límite de reintentos del Reviewer («stuck»).
    assert fallo["a"] == "fallo"
    assert fallo["guard"] == ["Fallo controlado del módulo", "MÓDULO DETENIDO"]


def test_fallo_de_toda_la_corrida_se_distingue_del_de_un_modulo() -> None:
    fila = a_fila_monitor(
        evento(agente="orquestador", tipo="fallo", archivo=None, funcion=None)
    )

    assert fila["a"] == "fallo"
    assert fila["guard"] == ["Fallo controlado", "CORRIDA DETENIDA"]


def test_evento_del_modulo_no_muestra_funcion_sin_nombre() -> None:
    fila = a_fila_monitor(evento(agente="orquestador", tipo="fallo", funcion=None))

    assert fila["fn"] == ""
    assert fila["identificador"] is None
    assert fila["tipo_objetivo"] is None


def test_el_fallo_sale_como_alerta_en_la_consola() -> None:
    from qagent.app.bitacora import TIPOS_DE_ALERTA

    fila = a_fila_monitor(evento(agente="orquestador", tipo="fallo"))

    assert a_evento_bitacora(fila)["tipo"] in TIPOS_DE_ALERTA


def test_formato_para_la_consola() -> None:
    fila = a_fila_monitor(
        evento(tipo="veredicto", datos={"decision": "bug_detectado", "intento": 1})
    )

    linea = a_evento_bitacora(fila)

    assert linea["tipo"] == "oracle"  # tipo de alerta: sale como WARNING
    assert linea["progreso"] == "1/6"
    assert "[Oráculo" in linea["mensaje"]


def test_endpoint_conserva_metodo_ruta_tipo_y_progreso_oficial() -> None:
    fila = a_fila_monitor(
        evento(funcion="DELETE /items/1", progreso={"hechos": 2, "total": 5})
    )

    assert fila["tipo_objetivo"] == "endpoint"
    assert fila["identificador"] == "DELETE /items/1"
    assert (fila["metodo"], fila["ruta"]) == ("DELETE", "/items/1")
    assert fila["porcentaje"] == 40


def test_texto_peligroso_del_evento_permanece_como_dato() -> None:
    fila = a_fila_monitor(
        evento(funcion="normal", mensaje='<img src=x onerror="alert(1)">')
    )

    assert fila["t"] == '<img src=x onerror="alert(1)">'
    assert fila["tipo_objetivo"] == "funcion"


def test_alerta_presupuesto_tokens_formatea_fila_watch() -> None:
    fila = a_fila_monitor(
        evento(
            agente="orquestador",
            tipo="aviso",
            mensaje="Aviso de presupuesto: se ha consumido el 85 % del límite de tokens.",
            datos={
                "alerta_presupuesto": True,
                "tokens": 8500,
                "limite_tokens": 10000,
                "tokens_acumulados": 8500,
                "tokens_reales": 5000,
                "tokens_estimados": 3500,
            },
        )
    )

    assert fila is not None
    assert fila["a"] == "watch"
    assert fila["guard"] == ["Aviso de presupuesto", "LÍMITE TOKENS"]
    assert fila["tokens_acumulados"] == 8500
    assert fila["tokens_reales"] == 5000
    assert fila["tokens_estimados"] == 3500
    assert fila["limite_tokens"] == 10000
