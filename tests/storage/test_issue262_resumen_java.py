"""#262: resultados legibles sin Explicador, con evidencia técnica preservada."""

import copy

import pytest

from qagent.llm import cargar_precios
from qagent.storage import escribir_corrida
from qagent.storage.informe_pdf import _explicacion
from qagent.storage.resumen_prueba import resumir_prueba
from qagent.storage.vista_ejecucion import leer_results
from qagent.storage.vista_reporte import leer_detalle, vista_reporte
from tests.storage.test_registro import correr


@pytest.mark.parametrize(
    ("estado", "esperado", "obtenido", "fragmento"),
    [
        ("bug_detectado", "2.5", "2.0", "esperaba 2.5 y obtuvo 2.0"),
        ("bug_detectado", 118, 82, "esperaba 118 y obtuvo 82"),
        ("bug_detectado", 0, False, "esperaba 0 y obtuvo false"),
        ("sin_veredicto", 2.5, 2, "no demuestra un defecto"),
        ("aprobado", None, None, "Pasaron los casos ejecutados"),
        ("rechazado_laundering", None, None, "debilitaba"),
        ("estancado", None, None, "intentos permitidos"),
        ("requiere_corrida_nueva", None, None, "El código cambió"),
    ],
)
def test_resumen_respeta_el_veredicto_y_los_valores_registrados(
    estado, esperado, obtenido, fragmento
) -> None:
    """Un fallo técnico con valores aparentes no se transforma en un bug."""
    funcion = {
        "estado": estado,
        "ejecucion": {
            "casos": [
                {"resultado": "fallo", "esperado": esperado, "obtenido": obtenido}
            ]
        },
        "intentos": [{"feedback": "[INFO] MAVEN_LOG_EXTENSO" * 100}],
    }
    original = copy.deepcopy(funcion)
    resumen = resumir_prueba(funcion, "humo")
    assert fragmento in resumen
    assert "MAVEN_LOG_EXTENSO" not in resumen
    assert funcion == original


def test_bug_sin_valores_no_inventa_cifras() -> None:
    """Las corridas antiguas pueden carecer de casos estructurados."""
    assert resumir_prueba({"estado": "bug_detectado"}) == (
        "Una prueba ejecutada detectó una diferencia con el comportamiento esperado."
    )


def test_humo_aclara_el_alcance_del_aprobado() -> None:
    """Un caso que pasa no se presenta como prueba exhaustiva del método."""
    texto = resumir_prueba({"estado": "aprobado"}, "humo")
    assert "un caso normal" in texto
    assert "no garantiza" in texto


def test_reabrir_resultados_anteriores_resume_sin_llamar_a_ia(tmp_path) -> None:
    """El reporte y el exportador usan el resumen, pero conservan el feedback técnico."""
    precios = cargar_precios()
    tracker, resultado = correr(precios, decisiones=("bug_detectado",))
    rutas = escribir_corrida(tmp_path, resultado, tracker, precios, "humo")
    results = leer_results(tmp_path, rutas.run_id)
    detalle = leer_detalle(tmp_path, rutas.run_id)
    marca = "[INFO] MAVEN_LOG_EXTENSO"
    detalle["funciones"][0]["intentos"][-1]["feedback"] = marca
    original = copy.deepcopy(detalle)
    antes = len(tracker.llamadas)
    [funcion] = vista_reporte(results, detalle)["funciones"]
    assert funcion["resumen_ejecucion"] == resumir_prueba(funcion, "humo")
    assert marca not in _explicacion(funcion)
    assert funcion["intentos"][-1]["feedback"] == marca
    assert detalle == original
    assert len(tracker.llamadas) == antes

    simple = {"resumen": "Explicación ya guardada", "origen": "plantilla"}
    [con_explicador] = vista_reporte(
        results,
        detalle,
        {(funcion["modulo"], funcion["funcion"]): simple},
    )["funciones"]
    assert _explicacion(con_explicador).startswith("Explicación ya guardada")
