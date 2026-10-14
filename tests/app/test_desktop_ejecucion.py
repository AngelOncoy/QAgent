"""El puente entrega a la vista Ejecución los datos de results.json (HU-18)."""

from __future__ import annotations

import pytest

pytest.importorskip("webview")

from qagent.app.desktop import DesktopAPI
from qagent.llm import cargar_precios
from qagent.storage import escribir_corrida
from tests.storage.test_registro import correr


def test_obtener_ejecucion_de_la_ultima_corrida(tmp_path) -> None:
    precios = cargar_precios()
    tracker, resultado = correr(precios)
    rutas = escribir_corrida(tmp_path, resultado, tracker, precios, "deep")

    vista = DesktopAPI().obtener_ejecucion(str(tmp_path))

    assert vista["ok"] is True
    assert vista["run_id"] == rutas.run_id
    assert set(vista["indicadores"]) == {
        "pass_rate",
        "cobertura",
        "iteraciones",
        "costo",
        "mutation_score",
    }


def test_sin_resultados_devuelve_el_motivo(tmp_path) -> None:
    vista = DesktopAPI().obtener_ejecucion(str(tmp_path))

    assert vista == {
        "ok": False,
        "motivo": "Este proyecto todavía no tiene corridas con resultados.",
    }
