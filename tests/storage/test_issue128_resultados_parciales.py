"""Consistencia de resultados parciales e Historial de la issue #128."""

from __future__ import annotations

import json
from pathlib import Path

from qagent.almacenamiento import AlmacenProyecto
from qagent.almacenamiento.historial import construir_historial
from qagent.llm import cargar_precios
from qagent.storage import escribir_corrida
from qagent.storage.exportar_informe import (
    construir_html_informe,
    construir_markdown_informe,
    datos_informe,
)
from qagent.storage.vista_ejecucion import vista_ejecucion
from qagent.storage.vista_reporte import vista_reporte
from tests.storage.test_registro import correr


def _corrida_parcial(tmp_path: Path) -> tuple[AlmacenProyecto, str, dict]:
    """Persiste una corrida con un aprobado, un omitido y dos pendientes."""
    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()
    run_id = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
    precios = cargar_precios()
    tracker, resultado = correr(precios, decisiones=("accept",))
    omitidos = [
        {
            "modulo": resultado.modulo,
            "objetivo": "sin_oraculo",
            "tipo": "funcion",
            "motivo": "No hay un resultado esperado verificable.",
        }
    ]
    rutas = escribir_corrida(
        tmp_path,
        resultado,
        tracker,
        precios,
        "deep",
        run_id=run_id,
        inicio="2026-10-26T10:00:00+00:00",
        fin="2026-10-26T10:00:05+00:00",
        duracion_s=5.0,
        total_seleccionados=4,
        total_elegibles=3,
        total_procesados=1,
        total_pendientes=2,
        tipo_terminacion="cancelada",
        objetivos_omitidos=1,
        omitidos=omitidos,
    )
    almacen.finalizar_run(
        run_id,
        "fallo_controlado",
        pasaron=1,
        fallaron=0,
        total_seleccionados=4,
        total_elegibles=3,
        total_procesados=1,
        total_pendientes=2,
        objetivos_omitidos=1,
        tipo_terminacion="cancelada",
        motivo="Corrida cancelada por el usuario.",
        duracion_s=5.0,
    )
    return almacen, run_id, json.loads(rutas.results.read_text(encoding="utf-8"))


def test_contadores_coinciden_en_run_results_vistas_historial_y_reportes(
    tmp_path: Path,
) -> None:
    """Escenarios C/F: todas las capas conservan las mismas unidades y totales."""
    almacen, run_id, results = _corrida_parcial(tmp_path)
    run = almacen.leer_run(run_id)
    ejecucion = vista_ejecucion(results)
    reporte = vista_reporte(results, None)
    historial = construir_historial(tmp_path)["corridas"][0]
    esperado = (4, 3, 1, 1, 2)

    assert (
        run["total_seleccionados"],
        run["total_elegibles"],
        run["procesados"],
        run["objetivos_omitidos"],
        run["pendientes"],
    ) == esperado
    for datos in (results, results["resumen"], ejecucion, reporte, historial):
        assert (
            datos["total_seleccionados"],
            datos["total_elegibles"],
            datos["total_procesados"],
            datos.get("total_omitidos", datos.get("objetivos_omitidos")),
            datos["total_pendientes"],
        ) == esperado

    datos = datos_informe(tmp_path, run_id)
    markdown = construir_markdown_informe(datos)
    html = construir_html_informe(datos)
    texto = "4 seleccionados · 3 elegibles · 1 procesados · 1 omitidos · 2 pendientes"
    assert texto in markdown
    assert texto in html
    assert datos["duracion_total_s"] == 5.0


def test_historial_solo_cuenta_como_aprobado_un_accept(tmp_path: Path) -> None:
    """Un sandbox OK no convierte por sí solo un objetivo estancado en aprobado."""
    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()
    run_id = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
    precios = cargar_precios()
    tracker, resultado = correr(precios, decisiones=("stalled",))
    resultado.objetivos[0].revisiones[-1]["estado_sandbox"] = "ok"
    escribir_corrida(
        tmp_path,
        resultado,
        tracker,
        precios,
        "deep",
        run_id=run_id,
        total_seleccionados=1,
        total_elegibles=1,
        total_procesados=1,
        total_pendientes=0,
        tipo_terminacion="completada_con_errores",
        objetivos_omitidos=0,
        omitidos=[],
    )
    almacen.finalizar_run(
        run_id,
        "fin",
        pasaron=0,
        fallaron=1,
        total_seleccionados=1,
        total_elegibles=1,
        total_procesados=1,
        total_pendientes=0,
        objetivos_omitidos=0,
        tipo_terminacion="completada_con_errores",
    )

    fila = construir_historial(tmp_path)["corridas"][0]
    assert fila["pasaron"] == 0
    assert fila["pruebas_aprobadas"] == 0
    assert fila["errores_tecnicos"] == 1


def test_corrida_historica_deriva_elegibles_sin_inventar_metricas() -> None:
    """Escenario E: los campos nuevos son opcionales y cero no equivale a ausencia."""
    precios = cargar_precios()
    tracker, resultado = correr(precios, decisiones=("accept",))
    results = {
        "run_id": "20261026-100000-0001",
        "fecha": "2026-09-01T10:00:00+00:00",
        "perfil": "deep",
        "es_simulado": True,
        "estado_final": "fin",
        "motivo_fallo": None,
        "modelos": {},
        "objetivos": [],
        "resumen": {
            "total_funciones": 0,
            "pass_rate": 0.0,
            "cobertura_lineas_promedio": None,
            "cobertura_ramas_promedio": None,
            "costo_total_usd": 0.0,
            "total_tokens": 0,
            "por_agente": {},
        },
    }
    vista = vista_ejecucion(results)
    assert vista["total_seleccionados"] == 0
    assert vista["total_elegibles"] == 0
    assert vista["total_procesados"] == 0
    assert vista["total_pendientes"] == 0
    assert vista["duracion_total_s"] is None
    assert vista["indicadores"]["costo"]["tokens_total"] == 0
    assert tracker.total_tokens > 0 and resultado.objetivos  # fixture controlado usado


def test_frontend_distingue_todas_las_categorias_sin_mezclar_denominadores() -> None:
    """Escenario F: Monitor, Resultados e Historial usan el vocabulario acordado."""
    raiz = Path(__file__).resolve().parents[2] / "src/qagent/frontend/componentes"
    monitor = (raiz / "monitor/monitor.js").read_text(encoding="utf-8")
    ejecucion = (raiz / "ejecucion/ejecucion.js").read_text(encoding="utf-8")
    historial = (raiz / "historial/historial.js").read_text(encoding="utf-8")

    assert "procesados · ${omitidos} omitidos · ${pendientes} pendientes" in monitor
    assert "${pasaron} / ${procesados}" in ejecucion
    assert "seleccionados · ${elegibles} elegibles" in ejecucion
    assert "${noSeProbaron} y ${quedaronPendientes}" in ejecucion
    assert "etiquetasResumen[k][c === 1 ? 0 : 1]" in ejecucion
    assert "objetivos aprobados de ${proc} procesados" in historial
    assert "procesados con veredicto" not in historial
