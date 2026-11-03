"""Integración Playwright/Chromium real; nunca forma parte de una prueba simulada."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from qagent.e2e.ejecucion import ejecutar_humo_e2e
from qagent.e2e.modelos import ConfiguracionE2E

FIXTURE = Path(__file__).parents[1] / "fixtures" / "issue186_e2e"


@pytest.mark.docker
def test_playwright_real_detecta_exitos_y_fallos_con_capturas(tmp_path: Path) -> None:
    project = tmp_path / "web"
    shutil.copytree(FIXTURE, project)
    result = ejecutar_humo_e2e(
        project,
        config=ConfiguracionE2E(
            startup_timeout_s=20, route_timeout_s=8, total_timeout_s=90
        ),
    )
    by_path = {route["path"]: route for route in result["routes"]}
    assert by_path["/"]["status"] == "cumple"
    assert by_path["/otro"]["status"] == "cumple"
    assert by_path["/error-http"]["http_status"] == 500
    assert by_path["/error-js"]["page_errors"]
    assert by_path["/vacia"]["visible_content"] is False
    assert by_path["/red-externa"]["request_errors"]
    for route in by_path.values():
        if route["status"] == "falla":
            assert route["screenshot"]
            screenshot = (
                project / ".qagent" / "runs" / result["run_id"] / route["screenshot"]
            )
            assert screenshot.is_file() and screenshot.stat().st_size > 0
    assert result["tokens"] == 0
    assert result["limits"]["network"] == "none"


@pytest.mark.docker
def test_app_que_no_arranca_queda_sin_veredicto_y_con_log(tmp_path: Path) -> None:
    project = tmp_path / "web-no-start"
    shutil.copytree(FIXTURE, project)
    (project / ".qagent").mkdir()
    (project / ".qagent/e2e.json").write_text(
        json.dumps({"start_command": ["node", "archivo-inexistente.js"]}),
        encoding="utf-8",
    )
    result = ejecutar_humo_e2e(
        project,
        config=ConfiguracionE2E(startup_timeout_s=3, total_timeout_s=15),
    )
    assert result["status"] == "sin_veredicto"
    assert result["startup"]["ready"] is False
    assert result["startup"]["reason"]
    assert result["startup"]["log"]
    assert result["summary"]["no_verdict"] == result["summary"]["total"] == 6
    assert result["routes"] == []
