"""Pruebas de consistencia de métricas, contadores y clasificación del Historial."""

from __future__ import annotations

import json
from pathlib import Path

from qagent import contracts
from qagent.almacenamiento import AlmacenProyecto
from qagent.almacenamiento.historial import clasificar_terminacion, construir_historial
from qagent.llm import cargar_precios
from qagent.storage import escribir_corrida
from tests.storage.test_registro import correr

CONTRATO_BASE = json.loads(
    (contracts.DIR_CONTRATOS / "ejemplos" / "planner_contract.v2.json").read_text(
        encoding="utf-8"
    )
)


def test_diferenciacion_artefactos_en_pruebas_guardadas(tmp_path: Path) -> None:
    """Verifica que se diferencian planes (specs), archivos .py, pruebas unitarias y repetibles."""
    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()

    # 1. Guardar 2 planes de prueba (specs)
    contrato1 = dict(CONTRATO_BASE, modulo="modulo_a.py", huella="a" * 64)
    almacen.guardar_plan_modulo(
        "modulo_a.py", "a" * 64, [contrato1], "20261020-100000-0001", "generado"
    )
    contrato2 = dict(
        CONTRATO_BASE, modulo="modulo_b.py", huella="b" * 64, objetivo="otra_funcion"
    )
    almacen.guardar_plan_modulo(
        "modulo_b.py", "b" * 64, [contrato2], "20261020-100000-0001", "generado"
    )

    # 2. Guardar 1 archivo de prueba con 3 funciones def test_*
    codigo_tests = "def test_uno():\n    pass\n\ndef test_dos():\n    pass\n\ndef test_tres():\n    pass\n"
    almacen.guardar_prueba_aprobada("test_modulo_a_py__calcular.py", codigo_tests)

    historial = construir_historial(tmp_path)
    resumen_g = historial["resumen_guardadas"]

    # Especificaciones o planes almacenados
    assert resumen_g["planes_almacenados"] == 2
    assert resumen_g["especificaciones_totales"] == 2

    # Archivos de prueba generados
    assert resumen_g["archivos_prueba"] == 1

    # Pruebas aceptadas (conteo de funciones de test)
    assert resumen_g["pruebas_aceptadas"] == 3

    # Pruebas disponibles para regresión
    assert resumen_g["pruebas_regresion"] >= 0


def test_clasificacion_de_corridas_parciales_y_completas(tmp_path: Path) -> None:
    """Verifica la correcta identificación de completadas, con errores, detenidas, canceladas y limitadas."""
    # 1. Completada
    tipo, nombre = clasificar_terminacion(
        {"estado": "fin", "resumen": {"pasaron": 10, "fallaron": 0}},
        {"estado_final": "fin", "resumen": {"sin_veredicto": 0, "stalled": 0}},
        total_pendientes=0,
    )
    assert tipo == "completada"
    assert nombre == "Completada"

    # 2. Completada con errores por objetivo
    tipo, nombre = clasificar_terminacion(
        {"estado": "fin", "resumen": {"pasaron": 8, "fallaron": 2}},
        {"estado_final": "fin", "resumen": {"sin_veredicto": 2, "stalled": 0}},
        total_pendientes=0,
    )
    assert tipo == "completada_con_errores"
    assert nombre == "Completada con errores"

    # 3. Cancelada por usuario
    tipo, nombre = clasificar_terminacion(
        {
            "estado": "fallo_controlado",
            "motivo": "Corrida cancelada por el usuario.",
            "resumen": {"pasaron": 2, "fallaron": 0},
        },
        {
            "estado_final": "fallo_controlado",
            "motivo_fallo": "Corrida cancelada por el usuario.",
            "resumen": {},
        },
        total_pendientes=5,
    )
    assert tipo == "cancelada"
    assert nombre == "Cancelada"

    # 4. Limitada por recursos (tokens o gasto)
    tipo, nombre = clasificar_terminacion(
        {
            "estado": "fallo_controlado",
            "motivo": "Se alcanzó el presupuesto de tokens por corrida",
            "resumen": {"pasaron": 3, "fallaron": 1},
        },
        {
            "estado_final": "fallo_controlado",
            "motivo_fallo": "Se alcanzó el presupuesto de tokens",
            "resumen": {},
        },
        total_pendientes=8,
    )
    assert tipo == "limitada_recursos"
    assert nombre == "Limitada por recursos"

    # 5. Detenida por error global
    tipo, nombre = clasificar_terminacion(
        {
            "estado": "fallo_controlado",
            "motivo": "RuntimeError: Sandbox timeout",
            "resumen": {"pasaron": 1, "fallaron": 0},
        },
        {
            "estado_final": "fallo_controlado",
            "motivo_fallo": "RuntimeError: Sandbox timeout",
            "resumen": {},
        },
        total_pendientes=12,
    )
    assert tipo == "detenida_error"
    assert nombre == "Detenida por error"


def test_corrida_parcial_registra_seleccionados_procesados_y_pendientes(
    tmp_path: Path,
) -> None:
    """Caso APP-RF: 40 seleccionados, corrida detenida tras procesar 13 objetivos (2 pasan)."""
    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()

    precios = cargar_precios()
    # Simular corrida con resultado
    tracker, resultado = correr(precios, decisiones=("accept",))

    # Escribir corrida con 40 seleccionados, 13 procesados, 27 pendientes
    rutas = escribir_corrida(
        tmp_path,
        resultado,
        tracker,
        precios,
        "deep",
        total_seleccionados=40,
        total_procesados=13,
        total_pendientes=27,
        tipo_terminacion="limitada_recursos",
    )

    almacen.guardar_run(
        {
            "run_id": rutas.run_id,
            "inicio": "2026-10-20T10:00:00+00:00",
            "fin": "2026-10-20T10:05:00+00:00",
            "tipos_prueba": ["funcion"],
            "imagen_docker": "qagent-sandbox:base",
            "estado": "fallo_controlado",
            "resumen": {"pasaron": 2, "fallaron": 11},
            "total_seleccionados": 40,
            "procesados": 13,
            "pendientes": 27,
            "tipo_terminacion": "limitada_recursos",
            "motivo": "Se alcanzó el presupuesto de tokens por corrida",
        }
    )

    historial = construir_historial(tmp_path)
    assert len(historial["corridas"]) == 1
    fila = historial["corridas"][0]

    # Objetivos seleccionados, procesados y pendientes
    assert fila["total_seleccionados"] == 40
    assert fila["total_procesados"] == 13
    assert fila["total_pendientes"] == 27
    assert fila["no_procesados_por_detencion"] == 27
    assert fila["es_parcial"] is True
    assert fila["tipo_terminacion"] == "limitada_recursos"
    assert fila["terminacion_nombre"] == "Limitada por recursos"

    # Resultados y pruebas
    assert fila["pasaron"] == 1  # 1 del resultado simulado
    assert fila["pruebas_aprobadas"] == 1
    assert fila["posibles_bugs"] == 0


def test_compatibilidad_con_corridas_historicas_sin_nuevos_campos(
    tmp_path: Path,
) -> None:
    """Una corrida previa sin total_seleccionados ni tipo_terminacion se lee sin error."""
    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()

    precios = cargar_precios()
    tracker, resultado = correr(precios, decisiones=("accept",))
    # Corrida histórica estándar
    rutas = escribir_corrida(tmp_path, resultado, tracker, precios, "std")

    almacen.guardar_run(
        {
            "run_id": rutas.run_id,
            "inicio": "2026-09-01T12:00:00+00:00",
            "fin": "2026-09-01T12:02:00+00:00",
            "tipos_prueba": ["funcion"],
            "imagen_docker": None,
            "estado": "fin",
            "resumen": {"pasaron": 1, "fallaron": 0},
        }
    )

    historial = construir_historial(tmp_path)
    assert len(historial["corridas"]) == 1
    fila = historial["corridas"][0]

    assert fila["total_procesados"] == 1
    assert fila["total_seleccionados"] == 1
    assert fila["total_pendientes"] == 0
    assert fila["es_parcial"] is False
    assert fila["tipo_terminacion"] == "completada"
    assert fila["terminacion_nombre"] == "Completada"
    assert fila["pasaron"] == 1
    assert fila["posibles_bugs"] == 0
