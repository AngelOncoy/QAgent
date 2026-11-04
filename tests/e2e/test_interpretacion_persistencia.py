"""Interpretación, persistencia, informes e Historial sin Docker."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qagent import contracts
from qagent.almacenamiento.historial import construir_historial
from qagent.almacenamiento.proyecto import AlmacenProyecto
from qagent.e2e.ejecucion import _complete_result, leer_resultado_e2e
from qagent.e2e.informe import construir_html, construir_markdown
from qagent.e2e.modelos import ConfiguracionE2E


def _plan() -> dict:
    return {
        "version": "1",
        "language": "javascript",
        "framework": "express",
        "adapter": "JavaScriptAdapter",
        "start_command": ["npm", "run", "start"],
        "port": 4173,
        "routes": [
            {
                "path": "/",
                "source": "app.js:1",
                "route_type": "page",
                "eligible": True,
                "reason": None,
            }
        ],
    }


def _route(status: str = "cumple", **changes: object) -> dict:
    item = {
        "path": "/",
        "status": status,
        "http_status": 200,
        "final_url": "http://127.0.0.1:4173/",
        "console_errors": [],
        "page_errors": [],
        "request_errors": [],
        "visible_content": True,
        "screenshot": None,
        "duration_ms": 12,
        "reason": None,
    }
    item.update(changes)
    return item


@pytest.mark.parametrize(
    "status,route,expected",
    [
        ("cumple", _route(), (1, 0, 0)),
        (
            "falla",
            _route(
                "falla",
                http_status=500,
                screenshot="capturas/error.png",
                reason="HTTP 500",
            ),
            (0, 1, 0),
        ),
        (
            "falla",
            _route(
                "falla", console_errors=["boom"], reason="La consola registró errores."
            ),
            (0, 1, 0),
        ),
        (
            "falla",
            _route("falla", page_errors=["uncaught"], reason="excepción"),
            (0, 1, 0),
        ),
        ("falla", _route("falla", visible_content=False, reason="vacía"), (0, 1, 0)),
        (
            "sin_veredicto",
            _route(
                "sin_veredicto",
                http_status=None,
                final_url=None,
                visible_content=False,
                reason="timeout",
            ),
            (0, 0, 1),
        ),
    ],
)
def test_interpreta_estados_y_contadores(
    status: str, route: dict, expected: tuple[int, int, int]
) -> None:
    raw = {
        "status": status,
        "startup": {
            "ready": True,
            "exit_code": None,
            "port": 4173,
            "timeout_ms": 30000,
            "log": "ready",
            "reason": None,
        },
        "routes": [route],
        "duration_s": 0.2,
    }
    result = _complete_result(
        "20261103-120000-abcd",
        _plan(),
        ConfiguracionE2E(),
        "qagent-sandbox:navegador",
        raw,
        None,
        0.3,
    )
    assert (
        result["summary"]["passed"],
        result["summary"]["failed"],
        result["summary"]["no_verdict"],
    ) == expected
    contracts.validar_versionado(contracts.FAMILIA_E2E_RESULT, result)
    assert result["tokens"] == 0


def test_arranque_fallido_deja_todas_sin_veredicto() -> None:
    raw = {
        "status": "sin_veredicto",
        "startup": {
            "ready": False,
            "exit_code": 1,
            "port": 4173,
            "timeout_ms": 30000,
            "log": "falló",
            "reason": "no inició",
        },
        "routes": [],
        "duration_s": 0.1,
    }
    result = _complete_result(
        "20261103-120000-abcd",
        _plan(),
        ConfiguracionE2E(),
        "qagent-sandbox:navegador",
        raw,
        None,
        0.2,
    )
    assert result["summary"] == {"total": 1, "passed": 0, "failed": 0, "no_verdict": 1}
    assert result["startup"]["log"] == "falló"


def test_persistencia_aislada_historial_e_informes(tmp_path: Path) -> None:
    store = AlmacenProyecto(tmp_path)
    run = store.crear_run(["e2e_humo"], "qagent-sandbox:navegador")
    raw = {
        "status": "falla",
        "startup": {
            "ready": True,
            "exit_code": None,
            "port": 4173,
            "timeout_ms": 30000,
            "log": "ready",
            "reason": None,
        },
        "routes": [
            _route(
                "falla",
                http_status=500,
                screenshot="capturas/error.png",
                reason="HTTP 500",
            )
        ],
        "duration_s": 0.3,
    }
    result = _complete_result(
        run["run_id"],
        _plan(),
        ConfiguracionE2E(),
        "qagent-sandbox:navegador",
        raw,
        None,
        0.4,
    )
    folder = store.carpeta_run(run["run_id"])
    (folder / "e2e.json").write_text(json.dumps(result), encoding="utf-8")
    store.finalizar_run(
        run["run_id"],
        "fin",
        0,
        1,
        tipos_prueba=["e2e_humo"],
        total_seleccionados=1,
        total_procesados=1,
        tipo_terminacion="e2e_humo",
    )
    assert leer_resultado_e2e(tmp_path, run["run_id"])["status"] == "falla"
    row = construir_historial(tmp_path)["corridas"][0]
    assert row["es_e2e"] is True and row["perfil_nombre"] == "E2E de humo"
    assert "HTTP 500" in construir_markdown(result)
    assert "capturas/error.png" in construir_html(result)
    assert not (folder / "results.json").exists()


def test_compatibilidad_historial_anterior(tmp_path: Path) -> None:
    assert construir_historial(tmp_path)["corridas"] == []


def test_contrato_rechaza_resultado_incompleto() -> None:
    with pytest.raises(contracts.ContratoInvalido):
        contracts.validar_versionado(contracts.FAMILIA_E2E_RESULT, {"version": "1"})
