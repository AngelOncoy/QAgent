"""Pruebas de consistencia entre Monitor, Ejecución, Reporte e Historial en corridas parciales."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from qagent.almacenamiento import AlmacenProyecto
from qagent.almacenamiento.historial import construir_historial
from qagent.config import cargar_configuracion
from qagent.config.carga import RUTA_CONFIG
from qagent.orchestrator.corrida import ejecutar_corrida
from qagent.sandbox import ResultadoSandbox
from qagent.storage.vista_ejecucion import leer_results, vista_ejecucion
from qagent.storage.vista_reporte import leer_detalle, vista_reporte

BANCO = Path(__file__).resolve().parents[2] / "bench"
COBERTURA = {
    "totals": {"percent_covered": 80.0, "num_branches": 4, "covered_branches": 3}
}


def ejecutor_simulado(
    imagen, ruta_proyecto, ruta_tests, modulo_cov
) -> ResultadoSandbox:
    return ResultadoSandbox(
        exit_code=0, stdout="1 passed", stderr="", coverage=COBERTURA, duracion_s=0.05
    )


@pytest.fixture
def proyecto(tmp_path: Path) -> AlmacenProyecto:
    carpeta = tmp_path / "banco"
    shutil.copytree(
        BANCO, carpeta, ignore=shutil.ignore_patterns("*.md", "*.json", ".qagent")
    )
    almacen = AlmacenProyecto(carpeta)
    almacen.inicializar()
    return almacen


@pytest.fixture
def config():
    return cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config


def test_consistencia_corrida_parcial_por_cancelacion(proyecto, config) -> None:
    """Una corrida cancelada a mitad mantiene consistencia en Monitor, Ejecución, Reporte e Historial."""
    eventos: list[dict] = []
    veredictos_contados = 0

    def debe_cancelar() -> bool:
        return veredictos_contados >= 2

    def registrar_evento(ev: dict) -> None:
        nonlocal veredictos_contados
        eventos.append(ev)
        if ev.get("tipo") == "veredicto":
            veredictos_contados += 1

    run_id = proyecto.crear_run(tipos_prueba=["funcion"])["run_id"]
    resumen = ejecutar_corrida(
        proyecto.raiz,
        "deep",
        config,
        None,
        simulado=True,
        al_evento=registrar_evento,
        run_id=run_id,
        preparar_imagen=lambda ruta: "imagen-prueba",
        ejecutor=ejecutor_simulado,
        cancelado=debe_cancelar,
    )

    # 1. Orquestador
    assert resumen.total_seleccionados == 6
    assert resumen.total_procesados == 2
    assert resumen.total_pendientes == 4
    assert resumen.cancelada is True
    assert resumen.tipo_terminacion == "cancelada"

    # 2. Monitor: el progreso total siempre fue 6 (seleccionados)
    assert any(e.get("progreso", {}).get("total") == 6 for e in eventos)
    fin_evento = [e for e in eventos if e.get("tipo") == "fin"]
    assert len(fin_evento) >= 1
    assert "cancelada" in fin_evento[0]["mensaje"].lower()

    # 3. Archivo results.json persistido
    results = leer_results(proyecto.raiz, resumen.run_id)
    assert results["total_seleccionados"] == 6
    assert results["total_procesados"] == 2
    assert results["total_pendientes"] == 4
    assert results["tipo_terminacion"] == "cancelada"
    assert len(results["objetivos"]) == 2

    # 4. Vista Ejecución de pruebas
    ejec = vista_ejecucion(results)
    assert ejec["total_seleccionados"] == 6
    assert ejec["total_procesados"] == 2
    assert ejec["total_pendientes"] == 4
    assert ejec["es_parcial"] is True
    assert ejec["tipo_terminacion"] == "cancelada"

    # 5. Vista Reporte de auditoría
    detalle = leer_detalle(proyecto.raiz, resumen.run_id)
    rep = vista_reporte(results, detalle)
    assert rep["total_seleccionados"] == 6
    assert rep["total_procesados"] == 2
    assert rep["total_pendientes"] == 4
    assert rep["es_parcial"] is True
    assert rep["tipo_terminacion"] == "cancelada"

    # 6. Historial
    historial = construir_historial(proyecto.raiz)
    assert len(historial["corridas"]) == 1
    fila = historial["corridas"][0]
    assert fila["run_id"] == resumen.run_id
    assert fila["total_seleccionados"] == 6
    assert fila["total_procesados"] == 2
    assert fila["total_pendientes"] == 4
    assert fila["no_procesados_por_detencion"] == 4
    assert fila["es_parcial"] is True
    assert fila["tipo_terminacion"] == "cancelada"
    assert fila["terminacion_nombre"] == "Cancelada"
    assert fila["pasaron"] == 2


def test_consistencia_corrida_completa(proyecto, config) -> None:
    """Una corrida completa reporta pendientes 0 y tipo_terminacion completada."""
    eventos: list[dict] = []
    run_id = proyecto.crear_run(tipos_prueba=["funcion"])["run_id"]
    resumen = ejecutar_corrida(
        proyecto.raiz,
        "deep",
        config,
        None,
        simulado=True,
        al_evento=eventos.append,
        run_id=run_id,
        preparar_imagen=lambda ruta: "imagen-prueba",
        ejecutor=ejecutor_simulado,
    )

    assert resumen.total_seleccionados == 6
    assert resumen.total_procesados == 6
    assert resumen.total_pendientes == 0
    assert resumen.tipo_terminacion == "completada"

    results = leer_results(proyecto.raiz, resumen.run_id)
    assert results["total_seleccionados"] == 6
    assert results["total_procesados"] == 6
    assert results["total_pendientes"] == 0
    assert results["tipo_terminacion"] == "completada"

    ejec = vista_ejecucion(results)
    assert ejec["es_parcial"] is False
    assert ejec["total_pendientes"] == 0

    historial = construir_historial(proyecto.raiz)
    fila = historial["corridas"][0]
    assert fila["es_parcial"] is False
    assert fila["total_pendientes"] == 0
    assert fila["tipo_terminacion"] == "completada"
    assert fila["terminacion_nombre"] == "Completada"
