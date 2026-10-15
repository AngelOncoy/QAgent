"""Lectura del junit.xml de pytest (EN-17): casos, dónde y por qué falló.

Las grabaciones de `grabaciones/` son salidas reales de pytest sobre mini proyectos con
bugs sembrados; así el parser se prueba sin Docker ni red.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from qagent.sandbox import JUnitInvalido, parsear_junit, recortar_salida
from qagent.sandbox.informe_pytest import LIMITE_SALIDA

GRABACIONES = Path(__file__).parent / "grabaciones"


def _informe(nombre: str):
    xml = (GRABACIONES / f"{nombre}.junit.xml").read_text(encoding="utf-8")
    return parsear_junit(xml)


def _caso(informe, nombre: str):
    return next(c for c in informe.casos if c.nombre == nombre)


def test_todo_pasa_cuenta_los_casos_y_no_trae_fallos():
    informe = _informe("todo_pasa")

    assert (informe.total, informe.pasaron, informe.fallaron) == (2, 2, 0)
    assert all(c.paso and c.traza is None and c.pila == [] for c in informe.casos)
    assert informe.inicio == "2026-10-15T10:00:00.000000"


def test_una_asercion_fallida_dice_donde_que_y_los_valores():
    informe = _informe("falla_assert")
    caso = _caso(informe, "test_doble_de_cuatro")

    assert (informe.pasaron, informe.fallaron) == (1, 1)
    assert caso.resultado == "fallo"
    assert caso.tipo_error == "AssertionError"
    assert (caso.archivo, caso.linea) == ("tests/test_generado.py", 4)
    assert caso.codigo == "assert doble(4) == 8"
    assert (caso.obtenido, caso.operador, caso.esperado) == ("12", "==", "8")
    assert "where 12 = doble(4)" in caso.mensaje


def test_una_excepcion_en_el_codigo_marca_la_linea_del_proyecto_y_el_test_que_la_llamo():
    caso = _caso(_informe("excepcion_en_codigo"), "test_dividir_por_cero_devuelve_none")

    assert caso.tipo_error == "ZeroDivisionError"
    assert (caso.archivo, caso.linea, caso.codigo) == ("modulo.py", 6, "return a / b")
    llamada, lanzamiento = caso.pila
    assert (llamada.archivo, llamada.linea) == ("tests/test_generado.py", 6)
    assert llamada.codigo == "assert dividir(1, 0) is None"
    assert (lanzamiento.archivo, lanzamiento.linea) == ("modulo.py", 6)
    assert caso.esperado is None and caso.obtenido is None


def test_pytest_raises_que_no_lanza_indica_la_excepcion_esperada():
    caso = _caso(_informe("raises_no_lanzada"), "test_suma_lanza_valueerror")

    assert caso.resultado == "fallo"
    assert caso.esperado == "se lanza ValueError"
    assert caso.obtenido == "no se lanzó ninguna excepción"
    assert caso.codigo == "with pytest.raises(ValueError):"


def test_un_error_de_coleccion_es_error_y_no_fallo():
    informe = _informe("error_coleccion")
    caso = informe.casos[0]

    assert (informe.errores, informe.fallaron, informe.pasaron) == (1, 0, 0)
    assert caso.resultado == "error"
    assert caso.tipo_error == "ImportError"
    assert (caso.archivo, caso.linea) == ("tests/test_generado.py", 2)
    assert caso.codigo == "from modulo import no_existe"
    assert "no_existe" in caso.traza


def test_mixto_separa_paso_fallo_y_omitido():
    informe = _informe("mixto")

    assert (informe.total, informe.pasaron, informe.fallaron, informe.omitidos) == (
        3,
        1,
        1,
        1,
    )
    omitido = _caso(informe, "test_omitido")
    assert omitido.resultado == "omitido" and omitido.mensaje == "pendiente"


def test_a_dict_es_serializable():
    import json

    datos = _informe("mixto").a_dict()

    assert json.loads(json.dumps(datos))["fallaron"] == 1
    assert datos["casos"][2]["pila"][0]["archivo"] == "tests/test_generado.py"


@pytest.mark.parametrize("xml", ["", "   ", "<testsuites>", "no es xml"])
def test_un_xml_vacio_o_mal_formado_se_rechaza(xml):
    with pytest.raises(JUnitInvalido):
        parsear_junit(xml)


def test_un_xml_con_entidades_no_se_lee():
    peligroso = '<?xml version="1.0"?><!DOCTYPE a [<!ENTITY x "y">]><testsuites>&x;</testsuites>'

    with pytest.raises(JUnitInvalido):
        parsear_junit(peligroso)


def test_un_xml_demasiado_grande_se_rechaza():
    with pytest.raises(JUnitInvalido):
        parsear_junit("<a>" + "x" * 2_100_000 + "</a>")


def test_la_salida_larga_conserva_inicio_y_final():
    texto = "INICIO" + "x" * (LIMITE_SALIDA * 2) + "RESUMEN FINAL"

    recortada = recortar_salida(texto)

    assert recortada.startswith("INICIO") and recortada.endswith("RESUMEN FINAL")
    assert "caracteres omitidos" in recortada
    assert len(recortada) < LIMITE_SALIDA + 100


def test_la_salida_corta_no_se_toca():
    assert recortar_salida("1 passed") == "1 passed"
    assert recortar_salida("") == ""
