"""Reutilización estática acotada sin compartir objetos mutables ni decisiones."""

import json
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from unittest.mock import MagicMock

import pytest

from qagent.lenguajes import JavaAdapter, java_sesion
from qagent.lenguajes.java_generacion import contexto_java
from qagent.lenguajes.java_inferencia import ProveedorInferenciaJava
from qagent.lenguajes.java_revision import ReglasRevisionJava
from qagent.lenguajes.java_sesion import analizar_fuente, sesion_java
from qagent.recursos import recursos_actuales
from tests.agents.test_generator_java import FUENTE, preparar


def test_reutiliza_por_contenido_sin_contaminar_declaraciones(tmp_path):
    contrato = preparar(tmp_path)
    with sesion_java(tmp_path) as registro:
        primero = JavaAdapter().analizar(tmp_path)
        primero["modulos"][0]["funciones"][0]["firma"] = "contaminada"
        contexto = contexto_java(contrato, tmp_path)
        assert contexto["firma"] == contrato["firma"]
        assert not hasattr(analizar_fuente(FUENTE)[0], "edit")
        assert registro.resumen()["contadores"]["java_parseos"] == 1
    assert registro.resumen()["datos"]["cache_java"]["entradas_al_cierre"] == 0
    assert recursos_actuales() is None


def test_cambio_del_mismo_tamano_invalida_sin_confiar_en_mtime(tmp_path):
    contrato = preparar(tmp_path)
    archivo = tmp_path / contrato["modulo"]
    with sesion_java(tmp_path) as registro:
        assert (
            "* 2"
            in analizar_fuente(archivo.read_text(encoding="utf-8"))[
                0
            ].root_node.text.decode()
        )
        archivo.write_text(FUENTE.replace("* 2", "* 3"), encoding="utf-8")
        assert (
            "* 3"
            in analizar_fuente(archivo.read_text(encoding="utf-8"))[
                0
            ].root_node.text.decode()
        )
        assert registro.resumen()["contadores"]["java_parseos"] == 2


def test_rango_lee_solo_el_modulo_y_conserva_identidad_por_firma(tmp_path, monkeypatch):
    contrato = preparar(tmp_path)
    monkeypatch.setattr(
        JavaAdapter,
        "analizar",
        MagicMock(side_effect=AssertionError("Recorrido global redundante")),
    )
    rango = ReglasRevisionJava().rango_de_objetivo(
        tmp_path, contrato["modulo"], contrato["objetivo"]
    )
    assert rango == (4, 4)
    assert (
        ReglasRevisionJava().rango_de_objetivo(
            tmp_path, contrato["modulo"], "Banco.otra"
        )
        is None
    )


def test_cache_lru_acotada_y_sin_rechazar_fuentes_al_expulsar(tmp_path, monkeypatch):
    monkeypatch.setattr(java_sesion, "MAX_ENTRADAS", 2)
    with sesion_java(tmp_path) as registro:
        for i in range(5):
            assert analizar_fuente(FUENTE.replace("Banco", f"Banco{i}"))[2]
        assert registro.resumen()["contadores"]["java_cache_expulsiones"] == 3
    assert registro.resumen()["datos"]["cache_java"]["entradas_al_cierre"] == 0


def test_payload_excesivo_no_se_retiene_ni_se_convierte_en_aprobacion(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(java_sesion, "MAX_BYTES", 1)
    with sesion_java(tmp_path) as registro:
        for _ in range(2):
            assert analizar_fuente(FUENTE)[2]
    assert registro.resumen()["contadores"]["java_cache_fuentes_no_retenidas"] == 2
    assert registro.resumen()["datos"]["cache_java"]["pico_payload_bytes"] == 0


def test_acceso_concurrente_calcula_una_vez_y_clona_declaraciones(tmp_path):
    with sesion_java(tmp_path) as registro:
        with ThreadPoolExecutor(max_workers=4) as pool:
            tareas = [
                pool.submit(copy_context().run, analizar_fuente, FUENTE)
                for _ in range(8)
            ]
            resultados = [t.result() for t in tareas]
        assert registro.resumen()["contadores"]["java_parseos"] == 1
        resultados[0][2][0]["firma"] = "mutada"
        assert all(r[2][0]["firma"] != "mutada" for r in resultados[1:])


def test_sesiones_concurrentes_no_comparten_fuentes_ni_cancelacion(tmp_path):
    def ejecutar(i):
        with sesion_java(tmp_path) as registro:
            nombre = f"Banco{i}"
            assert (
                analizar_fuente(FUENTE.replace("Banco", nombre))[2][0]["clase"]
                == nombre
            )
            assert not registro.cancelado()
        return registro.resumen()

    with ThreadPoolExecutor(max_workers=2) as pool:
        resultados = list(pool.map(ejecutar, [1, 2]))
    assert all(
        r["cerrado"] and r["contadores"]["java_parseos"] == 1 for r in resultados
    )


def test_error_no_deja_cache_global_y_siguiente_corrida_calcula_de_nuevo(tmp_path):
    with pytest.raises(ValueError), sesion_java(tmp_path) as registro:
        analizar_fuente(FUENTE)
        raise ValueError("controlado")
    assert registro.resumen()["cerrado"] and recursos_actuales() is None
    with sesion_java(tmp_path) as siguiente:
        analizar_fuente(FUENTE)
    assert siguiente.resumen()["contadores"]["java_parseos"] == 1


def test_trabajador_tardio_no_reabre_cache_ni_modifica_mediciones(tmp_path):
    with sesion_java(tmp_path) as registro:
        contexto = copy_context()
        analizar_fuente(FUENTE)
    cerrado = registro.resumen()
    contexto.run(analizar_fuente, FUENTE.replace("Banco", "Tardio"))
    assert registro.resumen() == cerrado


def test_limite_inferencia_se_declara_sin_aumentar_topes(tmp_path):
    preparar(
        tmp_path,
        fuente=FUENTE.replace("/** Devuelve el doble. @return dos veces x */", ""),
    )
    analisis = JavaAdapter().analizar(tmp_path)
    p = ProveedorInferenciaJava(tmp_path, analisis["modulos"], max_caracteres=1)
    with sesion_java(tmp_path) as registro:
        assert p.contexto("src/main/java/ejemplo/Banco.java", "Banco.duplicar") is None
    assert "tope de caracteres" in p.ultimo_limite
    assert registro.resumen()["datos"]["ultimo_limite_inferencia"] == p.ultimo_limite
    assert all(v is None for v in registro.resumen()["no_medidos"].values())
    json.dumps(registro.resumen())


def test_rangos_de_arrays_varargs_y_clase_anidada_con_crlf(tmp_path):
    archivo = tmp_path / "src/main/java/demo/Outer.java"
    archivo.parent.mkdir(parents=True)
    archivo.write_bytes(
        b"package demo;\r\npublic class Outer {\r\n"
        b"public static int f(int[] x) { return x.length; }\r\n"
        b"public static int f(String... x) { return x.length; }\r\n"
        b"public static class Inner {\r\npublic static int sano() { return 1; }\r\n}\r\n}\r\n"
    )
    esperados = {
        "Outer.f(int[])": (3, 3),
        "Outer.f(java.lang.String[])": (4, 4),
        "Outer.Inner.sano": (6, 6),
    }
    with sesion_java(tmp_path):
        for nombre, rango in esperados.items():
            assert (
                ReglasRevisionJava().rango_de_objetivo(
                    tmp_path, archivo.relative_to(tmp_path).as_posix(), nombre
                )
                == rango
            )
    assert (
        ReglasRevisionJava().rango_de_objetivo(tmp_path, "no-existe.java", "X.f")
        is None
    )


def test_indice_inferencia_se_construye_una_vez_por_fuente(tmp_path, monkeypatch):
    from qagent.lenguajes import java_inferencia

    preparar(
        tmp_path,
        fuente=FUENTE.replace("/** Devuelve el doble. @return dos veces x */", ""),
    )
    analisis = JavaAdapter().analizar(tmp_path)
    indexar = MagicMock(wraps=java_inferencia._metodos)
    monkeypatch.setattr(java_inferencia, "_metodos", indexar)
    p = ProveedorInferenciaJava(tmp_path, analisis["modulos"])
    for _ in range(2):
        assert (
            p.contexto("src/main/java/ejemplo/Banco.java", "Banco.duplicar") is not None
        )
    assert indexar.call_count == 1
