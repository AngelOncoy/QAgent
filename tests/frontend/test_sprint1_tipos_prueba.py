"""Contrato estructural de la seleccion unica de tipos de prueba (issue #67)."""

from __future__ import annotations

from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "src" / "qagent" / "frontend"


def leer(relativa: str) -> str:
    return (FRONTEND / relativa).read_text(encoding="utf-8")


def test_existen_exactamente_los_cuatro_tipos_y_un_valor_escalar() -> None:
    estado = leer("js/estado.js")

    assert "let testStrategy = 'unitaria'" in estado
    for clave in ("unitaria", "limites", "humo", "regresion"):
        assert f"k:'{clave}'" in estado


def test_tipo_de_prueba_usa_radios_y_no_seleccion_multiple() -> None:
    config = leer("componentes/config-pruebas/config-pruebas.js")

    assert "Tipo de prueba" in config
    assert 'type="radio"' in config
    assert 'name="testStrategy"' in config
    assert 'type="checkbox"' not in config
    assert "function pickTestStrategy" in config


def test_cambio_se_conserva_y_se_transmite_al_backend() -> None:
    config = leer("componentes/config-pruebas/config-pruebas.js")
    monitor = leer("componentes/monitor/monitor.js")

    assert "testStrategy = k" in config
    assert "renderTestTypes()" in config
    assert (
        "start_run(projectPath, profile, obtenerSeleccionObjetivos(), testStrategy)"
        in monitor
    )


def test_perfiles_legacy_no_duplican_humo_ni_regresion() -> None:
    estado = leer("js/estado.js")
    config = leer("componentes/config-pruebas/config-pruebas.js")

    assert "legacy:true" in estado
    assert "PROFILES.filter(p=>!p.legacy)" in config


def test_historial_ejecucion_e_informe_muestran_la_estrategia() -> None:
    historial = leer("componentes/historial/historial.js")
    ejecucion = leer("componentes/ejecucion/ejecucion.js")
    informe = leer("componentes/informe/informe.js")

    assert "h.estrategia_prueba" in historial
    assert "v.estrategia_prueba" in ejecucion
    assert "v.estrategia_prueba" in informe
