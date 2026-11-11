"""Issue 266 (C1 y C2) contra el backend real, sin Docker ni red.

C1: con el orquestador real, los endpoints seleccionados cuentan en `total_seleccionados`,
se procesan y llegan a Resultados con su propio estado (el fallo de la revisión de QA era
de los datos de demostración). C2: un objetivo estancado no deja la corrida «completada».
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from qagent.almacenamiento import AlmacenProyecto
from qagent.config import cargar_configuracion
from qagent.config.carga import RUTA_CONFIG
from qagent.orchestrator.corrida import (
    ResumenCorrida,
    ejecutar_corrida,
    tipo_terminacion,
)
from qagent.sandbox import ResultadoSandbox
from qagent.storage.vista_ejecucion import leer_results, vista_ejecucion

BANCO_API = Path(__file__).resolve().parents[2] / "bench_api"
COBERTURA = {
    "totals": {"percent_covered": 90.0, "num_branches": 2, "covered_branches": 2}
}


def _ejecutor_ok(imagen, ruta_proyecto, ruta_tests, modulo_cov) -> ResultadoSandbox:
    return ResultadoSandbox(
        exit_code=0, stdout="1 passed", stderr="", coverage=COBERTURA, duracion_s=0.01
    )


@pytest.fixture
def proyecto(tmp_path: Path) -> AlmacenProyecto:
    carpeta = tmp_path / "api"
    shutil.copytree(BANCO_API, carpeta, ignore=shutil.ignore_patterns("*.md"))
    almacen = AlmacenProyecto(carpeta)
    almacen.inicializar()
    return almacen


def test_c1_los_endpoints_se_cuentan_procesan_y_llegan_a_resultados(proyecto) -> None:
    config = cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config
    eventos: list[dict] = []
    run_id = proyecto.crear_run(tipos_prueba=["endpoint"])["run_id"]
    resumen = ejecutar_corrida(
        proyecto.raiz,
        "std",
        config,
        None,
        simulado=True,
        al_evento=eventos.append,
        run_id=run_id,
        preparar_imagen=lambda ruta: "imagen-prueba",
        ejecutor=_ejecutor_ok,
    )

    vista = vista_ejecucion(leer_results(proyecto.raiz, resumen.run_id))
    pruebas = [p for m in vista["modulos"] for p in m["pruebas"]]
    endpoints = [p for p in pruebas if p["tipo"] == "endpoint"]
    assert endpoints, "la corrida real debe procesar los endpoints"
    # Cada endpoint seleccionado cuenta y llega a Resultados con su propio estado.
    assert resumen.total_seleccionados == len(endpoints) + resumen.objetivos_omitidos
    assert resumen.total_procesados == len(pruebas)
    assert all(p["estado"] for p in endpoints)
    # El progreso en vivo cuenta sobre lo seleccionado, endpoints incluidos.
    totales = {
        e["progreso"]["total"] for e in eventos if e.get("progreso", {}).get("total")
    }
    assert totales == {resumen.total_seleccionados}


@pytest.mark.parametrize(
    ("cambios", "esperado"),
    [
        ({}, "completada"),
        ({"estancadas": 1}, "completada_con_errores"),
        ({"sin_veredicto": 1}, "completada_con_errores"),
        ({"total_pendientes": 2}, "detenida_error"),
    ],
)
def test_c2_lo_estancado_no_deja_la_corrida_completada(cambios, esperado) -> None:
    resumen = ResumenCorrida(run_id="r", estado="fin", motivo=None, total_funciones=3)
    for campo, valor in cambios.items():
        setattr(resumen, campo, valor)
    assert tipo_terminacion(resumen) == esperado
