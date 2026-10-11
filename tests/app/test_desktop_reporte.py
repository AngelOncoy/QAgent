"""El puente entrega al Reporte los datos de la corrida (HU-21)."""

from __future__ import annotations

import pytest

pytest.importorskip("webview")

from pyagent.app.desktop import DesktopAPI
from pyagent.llm import cargar_precios
from pyagent.storage import escribir_corrida
from tests.storage.test_registro import correr


def test_obtener_reporte_de_la_ultima_corrida(tmp_path) -> None:
    precios = cargar_precios()
    tracker, resultado = correr(precios)
    rutas = escribir_corrida(tmp_path, resultado, tracker, precios, "deep")

    reporte = DesktopAPI().obtener_reporte(str(tmp_path))

    assert reporte["ok"] is True
    assert reporte["run_id"] == rutas.run_id
    assert reporte["detalle_disponible"] is True
    assert len(reporte["funciones"][0]["controles"]) == 5


def test_sin_resultados_devuelve_el_motivo(tmp_path) -> None:
    assert DesktopAPI().obtener_reporte(str(tmp_path))["ok"] is False
