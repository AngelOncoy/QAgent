"""Issue #195: presentación consistente de comparaciones entre corridas."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from qagent import contracts
from qagent.almacenamiento import AlmacenProyecto
from qagent.almacenamiento.historial import construir_historial
from qagent.storage.exportar_informe import (
    construir_html_informe,
    construir_pdf_informe,
    datos_informe,
    exportar_informe,
    extraer_texto_pdf,
)
from qagent.storage.registro import escribir_corrida
from qagent.storage.vista_comparacion import (
    cargar_vista_comparacion,
    vista_comparacion,
)
from tests.storage.test_registro import correr, precios  # noqa: F401

ORIGEN = "20261103-120000-a195"
VERIFICACION = "20261103-121000-b195"


def _ejemplo() -> dict:
    ruta = contracts.DIR_CONTRATOS / "ejemplos" / "run_comparison.v1.json"
    dato = json.loads(ruta.read_text(encoding="utf-8"))
    dato["run_origen_id"] = ORIGEN
    dato["run_verificacion_id"] = VERIFICACION
    item = dato["comparaciones"][0]
    item["objetivo"].update(modulo="modulo_simulado.py", nombre="duplicar")
    item["prueba"]["id"] = "modulo_simulado_py__duplicar"
    item["prueba"]["archivo"] = "test_modulo_simulado_py__duplicar.py"
    item["prueba"]["run_origen_id"] = ORIGEN
    item["estado_anterior"]["referencia_resultado"] = f"runs/{ORIGEN}/results.json"
    item["estado_posterior"]["referencia_resultado"] = (
        f"runs/{VERIFICACION}/results.json"
    )
    return dato


def _con_cuatro_estados(repeticiones: int = 1) -> dict:
    dato = _ejemplo()
    base = dato["comparaciones"][0]
    casos = [
        ("corregido", "bug_detectado", "accept", None),
        ("sigue_fallando", "bug_detectado", "bug_detectado", None),
        ("regresion", "accept", "bug_detectado", None),
        ("no_comparable", "accept", "accept", "La firma cambió"),
    ]
    items = []
    casos = casos * repeticiones
    for indice, (resultado, antes, ahora, motivo) in enumerate(casos, start=1):
        item = copy.deepcopy(base)
        item["objetivo"]["nombre"] = f"objetivo_{indice}"
        item["prueba"]["id"] = f"prueba_{indice}"
        item["prueba"]["archivo"] = f"test_objetivo_{indice}.py"
        item["estado_anterior"]["decision"] = antes
        item["estado_posterior"]["decision"] = ahora
        item["resultado"] = resultado
        item["motivo"] = (
            motivo
            + "; información histórica insuficiente con descripción extensa y Unicode áéíóú."
            if motivo and repeticiones > 1
            else motivo
        )
        if resultado == "no_comparable":
            item["firma_verificacion"] = "(valor: str) -> str"
            item["prueba"]["huella_verificacion"] = "b" * 64
            if repeticiones > 1:
                item["estado_posterior"].update(
                    decision="requiere_corrida_nueva",
                    confiable=False,
                    referencia_resultado=None,
                    observado=None,
                )
        items.append(item)
    dato["comparaciones"] = items
    return dato


@pytest.fixture
def proyecto_comparado(tmp_path: Path, precios):  # noqa: F811
    almacen = AlmacenProyecto(tmp_path)
    tracker_origen, resultado_origen = correr(precios, decisiones=("bug_detectado",))
    tracker_verificacion, resultado_verificacion = correr(
        precios, decisiones=("accept",)
    )
    escribir_corrida(
        tmp_path,
        resultado_origen,
        tracker_origen,
        precios,
        "deep",
        run_id=ORIGEN,
    )
    escribir_corrida(
        tmp_path,
        resultado_verificacion,
        tracker_verificacion,
        precios,
        "verify_fix",
        run_id=VERIFICACION,
    )
    for run_id, hora, pasaron, fallaron in (
        (ORIGEN, "12:00:00", 0, 1),
        (VERIFICACION, "12:10:00", 1, 0),
    ):
        almacen.guardar_run(
            {
                "run_id": run_id,
                "inicio": f"2026-11-03T{hora}+00:00",
                "fin": f"2026-11-03T{hora}+00:00",
                "tipos_prueba": ["funcion"],
                "imagen_docker": "qagent-sandbox:base",
                "estado": "fin",
                "resumen": {"pasaron": pasaron, "fallaron": fallaron},
            }
        )
    almacen.guardar_comparacion(_ejemplo())
    return tmp_path


def test_modelo_compartido_presenta_los_cuatro_estados_sin_ocultarlos() -> None:
    vista = vista_comparacion(_con_cuatro_estados())

    assert vista["resumen"] == {
        "total_original": 4,
        "total_actual": 4,
        "total_ejecutadas": 4,
        "aprobadas_original": 2,
        "fallidas_original": 2,
        "aprobadas_actual": 2,
        "fallidas_actual": 2,
        "corregidos": 1,
        "siguen_fallando": 1,
        "regresiones": 1,
        "no_comparables": 1,
        "contadores_completos": True,
    }
    assert [item["etiqueta"] for item in vista["comparaciones"]] == [
        "Corregido",
        "Sigue fallando",
        "Regresión",
        "No comparable",
    ]
    assert "quinto estado neutro" in vista["comparaciones"][-1]["explicacion"]


def test_carga_y_historial_vinculan_la_verificacion_con_su_origen(
    proyecto_comparado: Path,
) -> None:
    vista = cargar_vista_comparacion(proyecto_comparado, VERIFICACION, "verify_fix")
    historial = construir_historial(proyecto_comparado)
    fila = next(
        item for item in historial["corridas"] if item["run_id"] == VERIFICACION
    )

    assert vista and vista["disponible"] is True
    assert vista["run_origen_id"] == ORIGEN
    assert fila["run_origen_id"] == ORIGEN
    assert fila["comparacion"]["resumen"]["corregidos"] == 1


def test_corrida_normal_no_recibe_una_comparacion_inventada(tmp_path: Path) -> None:
    assert cargar_vista_comparacion(tmp_path, ORIGEN, "deep") is None


def test_verificacion_sin_comparacion_explica_la_ausencia(
    proyecto_comparado: Path,
) -> None:
    ruta = (
        proyecto_comparado
        / ".qagent"
        / "comparaciones"
        / VERIFICACION
        / f"{ORIGEN}.json"
    )
    ruta.unlink()

    vista = cargar_vista_comparacion(proyecto_comparado, VERIFICACION, "verify_fix")
    assert vista and vista["disponible"] is False
    assert "no tiene una comparación" in vista["motivo"]


def test_comparacion_corrupta_no_rompe_la_vista(proyecto_comparado: Path) -> None:
    ruta = (
        proyecto_comparado
        / ".qagent"
        / "comparaciones"
        / VERIFICACION
        / f"{ORIGEN}.json"
    )
    ruta.write_text("{contenido roto", encoding="utf-8")

    vista = cargar_vista_comparacion(proyecto_comparado, VERIFICACION, "verify_fix")
    assert vista and vista["disponible"] is False
    assert "corruptos" in vista["motivo"]


def test_rechaza_objetivo_o_proyecto_ajeno(proyecto_comparado: Path) -> None:
    almacen = AlmacenProyecto(proyecto_comparado)
    ruta = almacen.carpeta_comparaciones / VERIFICACION / f"{ORIGEN}.json"
    dato = almacen.leer_comparacion(ORIGEN, VERIFICACION)
    dato["comparaciones"][0]["objetivo"]["nombre"] = "objetivo_ajeno"
    dato["comparaciones"][0]["prueba"]["id"] = "modulo_simulado_py__objetivo_ajeno"
    ruta.write_text(json.dumps(dato), encoding="utf-8")
    vista = cargar_vista_comparacion(proyecto_comparado, VERIFICACION, "verify_fix")
    assert vista and vista["disponible"] is False
    assert "objetivo ajeno" in vista["motivo"]

    ruta.write_text(json.dumps(_ejemplo()), encoding="utf-8")
    results = almacen.carpeta_run(VERIFICACION) / "results.json"
    contenido = json.loads(results.read_text(encoding="utf-8"))
    contenido["proyecto"] = str(proyecto_comparado / "otro-proyecto")
    results.write_text(json.dumps(contenido), encoding="utf-8")
    vista = cargar_vista_comparacion(proyecto_comparado, VERIFICACION, "verify_fix")
    assert vista and vista["disponible"] is False
    assert "otro proyecto" in vista["motivo"]


@pytest.mark.parametrize("formato", ["md", "html", "json", "pdf"])
def test_exportaciones_incluyen_la_misma_comparacion(
    proyecto_comparado: Path, formato: str
) -> None:
    resultado = exportar_informe(
        proyecto_comparado, run_id=VERIFICACION, formato=formato
    )
    ruta = Path(resultado["ruta"])
    if formato == "pdf":
        texto = extraer_texto_pdf(ruta.read_bytes())
    else:
        texto = ruta.read_text(encoding="utf-8")

    assert ORIGEN in texto
    assert VERIFICACION in texto
    assert "Corregido" in texto or '"corregidos": 1' in texto


def test_html_escapa_texto_del_contrato(proyecto_comparado: Path) -> None:
    dato = _ejemplo()
    dato["comparaciones"][0]["objetivo"]["nombre"] = "<script>alert(1)</script>"
    dato["comparaciones"][0]["motivo"] = "No se puede comparar"
    # El estado corregido exige motivo nulo; usamos no comparable para probar texto externo.
    item = dato["comparaciones"][0]
    item["resultado"] = "no_comparable"
    item["estado_anterior"]["decision"] = "accept"
    item["estado_posterior"]["decision"] = "accept"
    datos = datos_informe(proyecto_comparado, VERIFICACION)
    datos["comparacion"] = vista_comparacion(dato)
    html = construir_html_informe(datos)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_pdf_con_todos_los_estados_unicode_y_varias_paginas(
    proyecto_comparado: Path,
) -> None:
    datos = datos_informe(proyecto_comparado, VERIFICACION)
    datos["comparacion"] = vista_comparacion(_con_cuatro_estados(repeticiones=8))

    contenido = construir_pdf_informe(datos)
    texto = extraer_texto_pdf(contenido)

    assert contenido.startswith(b"%PDF-1.4")
    assert contenido.count(b"/Type /Page ") > 1
    assert "Corregido" in texto
    assert "Sigue fallando" in texto
    assert "Regresión" in texto
    assert "No comparable" in texto
    assert "insuficiente" in texto
