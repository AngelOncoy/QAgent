"""Los informes no presentan una expectativa inferida como especificación independiente."""

import copy

import pytest

from qagent.storage.exportar_informe import (
    construir_html_informe,
    construir_markdown_informe,
    construir_pdf_informe,
    datos_informe,
    extraer_texto_pdf,
)
from qagent.storage.respaldo_inferido import datos_para_informe, respuesta_con_respaldo
from tests.storage.test_exportar_informe import corrida_con_specs  # noqa: F401
from tests.storage.test_registro import precios  # noqa: F401


@pytest.mark.parametrize("formato", ["md", "html", "pdf"])
def test_fallo_inferido_es_hallazgo_en_todos_los_informes(corrida_con_specs, formato):  # noqa: F811
    raiz, rutas = corrida_con_specs
    datos = datos_informe(raiz, rutas.run_id)
    for funcion in datos["funciones"]:
        funcion.update(
            estado="bug_detectado",
            respaldo="inferido",
            evidencia_inferida=["cuerpo"],
            verde=False,
        )
    original = copy.deepcopy(datos)
    texto = (
        construir_markdown_informe(datos)
        if formato == "md"
        else construir_html_informe(datos)
        if formato == "html"
        else extraer_texto_pdf(construir_pdf_informe(datos))
    )
    assert "hallazgo a revisar" in texto.lower()
    assert "sin contrato documentado" in texto.lower()
    assert "defecto confirmado" not in texto.lower()
    assert "cuerpo" in texto
    assert datos == original


def test_presentacion_no_altera_decisiones_originales():
    datos = {
        "funciones": [
            {
                "estado": "bug_detectado",
                "respaldo": "inferido",
                "intentos": [{"decision": "bug_detectado"}],
            }
        ]
    }
    vista = datos_para_informe(datos)
    assert vista["funciones"][0]["estado"] == "hallazgo_inferido"
    assert datos["funciones"][0]["estado"] == "bug_detectado"
    assert datos["funciones"][0]["intentos"][0]["decision"] == "bug_detectado"


def test_informe_mixto_conserva_bugs_documentados_y_hallazgos():
    funciones = [
        {"estado": "bug_detectado"},
        {"estado": "hallazgo_inferido", "respaldo": "inferido"},
    ]
    titulo = respuesta_con_respaldo(
        "1 posible bug. Empieza por Calc.documentado.", funciones
    )
    assert "1 posible bug" in titulo and "Calc.documentado" in titulo
    assert "1 hallazgo(s) de regresión inferida" in titulo
    assert "1 con contrato y 1 de regresión" in titulo
