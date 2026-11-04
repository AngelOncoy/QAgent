"""Conexiones con imagen, adaptadores, API e interfaz."""

from __future__ import annotations

from pathlib import Path

from qagent.lenguajes import REGISTRO
from qagent.sandbox.imagen import DOCKERFILE_NAVEGADOR, RECETAS, receta_de
from qagent.sandbox.modelos import IMAGEN_NAVEGADOR


def test_imagen_navegador_fijada_y_separada() -> None:
    recipe = receta_de(IMAGEN_NAVEGADOR)
    dockerfile = DOCKERFILE_NAVEGADOR.read_text(encoding="utf-8")
    assert recipe.imagen == "qagent-sandbox:navegador"
    assert "mcr.microsoft.com/playwright:v1.64.1-noble" in dockerfile
    assert "playwright@1.64.1" in dockerfile
    assert "USER pwuser" in dockerfile


def test_otras_corridas_no_seleccionan_navegador() -> None:
    assert (
        REGISTRO.adaptador_para("python").entorno_sandbox().imagen != IMAGEN_NAVEGADOR
    )
    assert (
        REGISTRO.adaptador_para("javascript").entorno_sandbox().imagen
        != IMAGEN_NAVEGADOR
    )
    assert (
        REGISTRO.adaptador_para("typescript").entorno_sandbox().imagen
        != IMAGEN_NAVEGADOR
    )
    assert REGISTRO.adaptador_para("java").entorno_sandbox().imagen != IMAGEN_NAVEGADOR
    assert IMAGEN_NAVEGADOR in RECETAS


def test_runner_bloquea_red_y_conserva_capturas() -> None:
    runner = (
        Path(__file__).parents[2] / "src/qagent/sandbox/navegador/runner.mjs"
    ).read_text(encoding="utf-8")
    assert "allowedHost" in runner and "route.abort('blockedbyclient')" in runner
    assert "page.screenshot" in runner and "pageerror" in runner
    assert "consoleErrors" in runner and "visible_content" in runner


def test_frontend_exige_accion_voluntaria_y_abre_historial() -> None:
    root = Path(__file__).parents[2] / "src/qagent/frontend/componentes"
    prepare = (root / "config-pruebas/config-pruebas.js").read_text(encoding="utf-8")
    history = (root / "historial/historial.js").read_text(encoding="utf-8")
    assert 'onclick="ejecutarE2E()"' in prepare
    assert "window.confirm" in prepare
    assert "api.ejecutar_e2e" in prepare
    assert "fila.es_e2e" in history and "abrirResultadoE2E" in history
