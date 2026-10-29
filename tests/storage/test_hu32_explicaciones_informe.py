"""La explicación del Explicador en el informe y en la pantalla de resultados (HU-32).

Si `explicaciones.json` existe y es válido, el Reporte, el PDF y la exportación la
usan; si no, siguen como antes.
"""

from __future__ import annotations

import json

import pytest

from qagent.storage.exportar_informe import (
    _salud_proyecto,
    construir_html_informe,
    construir_markdown_informe,
    construir_pdf_informe,
    datos_informe,
    extraer_texto_pdf,
)
from qagent.storage.informe_pdf import _explicacion
from qagent.storage.registro import ARCHIVO_EXPLICACIONES
from qagent.storage.vista_reporte import ETIQUETA_IA, etiqueta_ia, leer_explicaciones
from tests.orchestrator.test_hu32_explicador_corrida import (  # noqa: F401 — fixtures
    config,
    correr,
    proyecto,
)

SIMPLE = {
    "resumen": "Se encontró un posible error en la función f.",
    "que_se_esperaba": "Que f devolviera 80.",
    "que_paso": "La función f dio 75, pero debía dar 80.",
    "que_hacer": "Revisa el código de la función f.",
}


@pytest.fixture
def corrida(proyecto, config):  # noqa: F811
    resumen, carpeta = correr(proyecto, config)
    return proyecto.raiz, resumen.run_id, carpeta


def _results(carpeta):
    return json.loads((carpeta / "results.json").read_text(encoding="utf-8"))


def _escribir(carpeta, datos):
    (carpeta / ARCHIVO_EXPLICACIONES).write_text(
        json.dumps(datos, ensure_ascii=False), encoding="utf-8"
    )


# --- Lectura -------------------------------------------------------------------------


def test_lee_las_explicaciones_validas_por_modulo_y_objetivo(corrida):
    raiz, _, carpeta = corrida

    explicaciones = leer_explicaciones(raiz, _results(carpeta))

    assert sorted(f for _, f in explicaciones) == [
        "buscar_elemento_mayor",
        "calcular_descuento",
        "clasificar_edad",
    ]
    explicacion = next(iter(explicaciones.values()))
    assert set(explicacion) == {*SIMPLE, "origen", "modelo"}  # origen: #166
    assert (explicacion["origen"], explicacion["modelo"]) == ("plantilla", None)


def test_sin_archivo_no_hay_explicaciones(corrida):
    raiz, _, carpeta = corrida
    (carpeta / ARCHIVO_EXPLICACIONES).unlink()

    assert leer_explicaciones(raiz, _results(carpeta)) == {}


@pytest.mark.parametrize("contenido", ["{no es json", '{"version": "1"}'])
def test_un_archivo_invalido_se_ignora(corrida, contenido):
    raiz, _, carpeta = corrida
    (carpeta / ARCHIVO_EXPLICACIONES).write_text(contenido, encoding="utf-8")

    assert leer_explicaciones(raiz, _results(carpeta)) == {}


def test_se_ignora_la_que_no_coincide_con_results(corrida):
    raiz, _, carpeta = corrida
    datos = json.loads((carpeta / ARCHIVO_EXPLICACIONES).read_text(encoding="utf-8"))
    datos["explicaciones"][0]["decision"] = "stalled"  # results.json dice bug
    cambiada = datos["explicaciones"][0]["objetivo"]
    _escribir(carpeta, datos)

    explicaciones = leer_explicaciones(raiz, _results(carpeta))

    assert cambiada not in {f for _, f in explicaciones}
    assert len(explicaciones) == 2


# --- Reporte, PDF y exportación ------------------------------------------------------


def test_el_informe_usa_la_explicacion(corrida):
    raiz, run_id, _ = corrida

    datos = datos_informe(raiz, run_id)
    bugs = [f for f in datos["funciones"] if f["estado"] == "bug_detectado"]
    texto = _explicacion(bugs[0])
    markdown = construir_markdown_informe(datos)
    pdf = extraer_texto_pdf(construir_pdf_informe(datos))

    assert all(f["explicacion"] for f in bugs)
    assert texto.splitlines()[0] == bugs[0]["explicacion"]["resumen"]
    assert "Qué hacer:" in texto
    assert bugs[0]["explicacion"]["resumen"] in markdown
    assert "posible error" in pdf


def test_sin_explicaciones_el_informe_sigue_como_antes(corrida):
    raiz, run_id, carpeta = corrida
    (carpeta / ARCHIVO_EXPLICACIONES).unlink()

    datos = datos_informe(raiz, run_id)

    assert all(f["explicacion"] is None for f in datos["funciones"])
    assert "posible error" not in construir_markdown_informe(datos)


def test_explicacion_cae_al_feedback_sin_explicador():
    f = {"estado": "bug_detectado", "intentos": [{"feedback": "Comentario técnico"}]}

    assert _explicacion(f) == "Comentario técnico"
    assert _explicacion({**f, "explicacion": None}) == "Comentario técnico"
    assert _explicacion({**f, "explicacion": SIMPLE}).startswith(SIMPLE["resumen"])


def _bug(**cambios):
    return {
        "modulo": "m.py",
        "funcion": "f",
        "estado": "bug_detectado",
        "verde": False,
        "cobertura_lineas": 100.0,
        "cobertura_ramas": 100.0,
        **cambios,
    }


def test_salud_del_proyecto_usa_la_explicacion_de_cada_bug():
    salud = _salud_proyecto({"funciones": [_bug(explicacion=SIMPLE)]})
    texto = json.dumps(salud, ensure_ascii=False)

    assert SIMPLE["que_paso"] in texto
    assert SIMPLE["que_hacer"] in texto
    assert "no cumple el contrato esperado" not in texto


def test_salud_del_proyecto_sin_explicacion_sigue_como_antes():
    texto = json.dumps(_salud_proyecto({"funciones": [_bug()]}), ensure_ascii=False)

    assert "no cumple el contrato esperado" in texto


# --- «Explicación generada por IA» (#166) --------------------------------------------


def _a_ia(carpeta, modelo="modelo-explicador"):
    datos = json.loads((carpeta / ARCHIVO_EXPLICACIONES).read_text(encoding="utf-8"))
    for explicacion in datos["explicaciones"]:
        explicacion.update(origen="ia", modelo=modelo)
    _escribir(carpeta, datos)


def test_etiqueta_ia_solo_con_origen_ia():
    assert etiqueta_ia({**SIMPLE, "origen": "ia", "modelo": "m-1"}) == (
        f"{ETIQUETA_IA} (m-1)"
    )
    assert etiqueta_ia({**SIMPLE, "origen": "plantilla", "modelo": None}) is None
    assert etiqueta_ia(SIMPLE) is None
    assert etiqueta_ia(None) is None


def test_los_informes_muestran_explicacion_generada_por_ia(corrida):
    raiz, run_id, carpeta = corrida
    _a_ia(carpeta)

    datos = datos_informe(raiz, run_id)
    bugs = [f for f in datos["funciones"] if f["estado"] == "bug_detectado"]

    assert all(f["explicacion"]["origen"] == "ia" for f in bugs)
    assert f"{ETIQUETA_IA} (modelo-explicador)" in _explicacion(bugs[0])
    assert ETIQUETA_IA in construir_markdown_informe(datos)
    assert ETIQUETA_IA in construir_html_informe(datos)
    assert ETIQUETA_IA in extraer_texto_pdf(construir_pdf_informe(datos))


def test_con_plantilla_los_informes_no_dicen_ia(corrida):
    raiz, run_id, _ = corrida

    datos = datos_informe(raiz, run_id)

    assert ETIQUETA_IA not in construir_markdown_informe(datos)
    assert ETIQUETA_IA not in construir_html_informe(datos)
    assert ETIQUETA_IA not in extraer_texto_pdf(construir_pdf_informe(datos))
