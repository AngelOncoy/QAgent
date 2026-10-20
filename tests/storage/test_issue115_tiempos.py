"""#115: los tiempos medidos llegan a results.json, las vistas y el Historial."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from qagent.almacenamiento import AlmacenProyecto
from qagent.almacenamiento.historial import construir_historial
from qagent.contracts import RUN_LOG, validar
from qagent.storage.vista_ejecucion import vista_ejecucion

EJEMPLO = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "qagent"
    / "contracts"
    / "ejemplos"
    / "run_log.results.json"
)


def _results() -> dict:
    return json.loads(EJEMPLO.read_text(encoding="utf-8"))


def test_run_log_acepta_tiempos_medidos() -> None:
    datos = _results()
    datos.update(
        inicio="2026-10-20T12:00:00Z",
        fin="2026-10-20T12:01:05Z",
        duracion_s=65.0,
        duracion_etapas={
            "planner": 1.0,
            "generator": 2.0,
            "reviewer": 3.0,
            "sandbox": 4.0,
            "pytest": 5.0,
        },
    )
    objetivo = datos["objetivos"][0]
    objetivo.update(
        inicio="2026-10-20T12:00:10Z",
        fin="2026-10-20T12:00:50Z",
        duracion_generacion_s=2.0,
        duracion_revision_s=3.0,
        duracion_sandbox_s=4.0,
        duracion_pytest_s=5.0,
        tiempos_intentos=[
            {
                "intento": 1,
                "duracion_s": 5.5,
                "generacion_s": 2.0,
                "revision_s": 3.0,
                "sandbox_s": 4.0,
                "pytest_s": 5.0,
            }
        ],
    )

    validar(RUN_LOG, datos)


def test_run_log_antiguo_sin_tiempos_sigue_siendo_valido() -> None:
    validar(RUN_LOG, _results())


def test_vista_ejecucion_expone_el_total_y_las_etapas() -> None:
    datos = _results()
    datos.update(
        inicio="2026-10-20T12:00:00Z",
        fin="2026-10-20T12:01:05Z",
        duracion_s=65.0,
        duracion_etapas={
            "planner": 1.0,
            "generator": 2.0,
            "reviewer": 3.0,
            "sandbox": 4.0,
            "pytest": 5.0,
        },
    )
    datos["objetivos"][0].update(
        duracion_generacion_s=2.0,
        duracion_revision_s=3.0,
        duracion_sandbox_s=4.0,
        duracion_pytest_s=5.0,
    )

    vista = vista_ejecucion(datos)

    assert vista["inicio"] == "2026-10-20T12:00:00Z"
    assert vista["fin"] == "2026-10-20T12:01:05Z"
    assert vista["duracion_total_s"] == 65.0
    assert vista["duracion_etapas"]["planner"] == 1.0
    prueba = vista["modulos"][0]["pruebas"][0]
    assert prueba["duracion_pytest_s"] == 5.0
    assert prueba["duracion_sandbox_s"] == 4.0


def test_vista_ejecucion_de_corrida_antigua_no_inventa_etapas() -> None:
    vista = vista_ejecucion(_results())

    assert vista["duracion_total_s"] is None
    assert "duracion_pytest_s" not in vista["modulos"][0]["pruebas"][0]


def test_historial_muestra_la_duracion_guardada(tmp_path: Path) -> None:
    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()
    inicio = datetime(2026, 10, 20, 12, 0, 0).astimezone()
    run = almacen.crear_run(ahora=inicio)
    almacen.finalizar_run(
        run["run_id"],
        "fin",
        2,
        0,
        ahora=inicio + timedelta(seconds=42),
        duracion_s=41.5,
    )

    [fila] = construir_historial(tmp_path)["corridas"]

    assert fila["duracion_s"] == 41.5
    assert fila["inicio"] == inicio.isoformat(timespec="seconds")
    assert fila["fin"] is not None


def test_historial_antiguo_sin_duracion_muestra_vacio(tmp_path: Path) -> None:
    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()
    inicio = datetime(2026, 10, 20, 12, 0, 0).astimezone()
    run = almacen.crear_run(ahora=inicio)
    almacen.finalizar_run(
        run["run_id"],
        "fin",
        1,
        0,
        ahora=inicio + timedelta(seconds=30),
    )

    [fila] = construir_historial(tmp_path)["corridas"]

    assert fila["duracion_s"] is None
