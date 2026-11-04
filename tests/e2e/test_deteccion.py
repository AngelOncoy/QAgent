"""Detección, normalización y seguridad sin Docker."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qagent.e2e.deteccion import (
    detectar_plan_e2e,
    normalizar_ruta,
    validar_comando,
    validar_url_local,
)
from qagent.e2e.modelos import ConfiguracionE2E


def _project(tmp_path: Path, routes: list[str] | None = None) -> Path:
    routes = routes or ["/", "/salud"]
    (tmp_path / "package.json").write_text(
        json.dumps(
            {"scripts": {"start": "node app.js"}, "dependencies": {"express": "5.1.0"}}
        ),
        encoding="utf-8",
    )
    calls = "\n".join(
        f'app.get("{route}", (_req, res) => res.send("ok"));' for route in routes
    )
    (tmp_path / "app.js").write_text(
        f'import express from "express";\nconst app=express();\n{calls}',
        encoding="utf-8",
    )
    return tmp_path


@pytest.mark.parametrize(
    "route", ["/", "/docs", "/a/b", "/buscar?q=uno", "/x#fragment"]
)
def test_normaliza_rutas_locales(route: str) -> None:
    assert normalizar_ruta(route) == route


@pytest.mark.parametrize(
    "route",
    [
        "https://example.com",
        "//evil.test/x",
        "file:///etc/passwd",
        "ftp://x/a",
        "../x",
        "/a/../x",
        "/\\windows",
        "/x\nHost:evil",
    ],
)
def test_rechaza_rutas_externas_o_malformadas(route: str) -> None:
    with pytest.raises(ValueError):
        normalizar_ruta(route)


@pytest.mark.parametrize(
    "url,port,expected",
    [
        ("http://127.0.0.1:4173/", 4173, True),
        ("http://localhost:4173/a", 4173, True),
        ("http://example.com:4173/", 4173, False),
        ("file:///tmp/x", 4173, False),
        ("http://user:pass@localhost:4173/", 4173, False),
        ("http://localhost:3000/", 4173, False),
    ],
)
def test_valida_origen_local(url: str, port: int, expected: bool) -> None:
    assert validar_url_local(url, port) is expected


@pytest.mark.parametrize(
    "command", [["npm", "run", "start"], ["node", "server.js"], ["python", "app.py"]]
)
def test_acepta_comandos_estructurados(command: list[str]) -> None:
    assert validar_comando(command) == command


@pytest.mark.parametrize(
    "command",
    [["sh", "-c", "id"], ["node", "-e", "x"], ["cmd", "/c", "dir"], "npm start", []],
)
def test_no_ejecuta_comandos_arbitrarios(command: object) -> None:
    with pytest.raises(ValueError):
        validar_comando(command)


def test_detecta_varias_rutas_sin_duplicados_y_en_orden(tmp_path: Path) -> None:
    root = _project(tmp_path, ["/z", "/a", "/a"])
    plan = detectar_plan_e2e(root)
    assert [route["path"] for route in plan["routes"]] == ["/a", "/z"]
    assert plan["framework"] == "express"
    assert plan["start_command"] == ["npm", "run", "start"]


def test_ruta_dinamica_queda_sin_veredicto(tmp_path: Path) -> None:
    route = detectar_plan_e2e(_project(tmp_path, ["/usuarios/:id"]))["routes"][0]
    assert route["eligible"] is False
    assert "no inventa" in route["reason"]


def test_endpoint_json_no_se_confunde_con_pagina(tmp_path: Path) -> None:
    root = _project(tmp_path, ["/"])
    (root / "app.js").write_text(
        'import express from "express"; const app=express(); app.get("/api/items", (_req, res) => res.json({items: []}));',
        encoding="utf-8",
    )
    route = detectar_plan_e2e(root)["routes"][0]
    assert route["route_type"] == "api"
    assert route["eligible"] is False


def test_rutas_declaradas_y_tipos_no_pagina(tmp_path: Path) -> None:
    root = _project(tmp_path, ["/"])
    (root / ".qagent").mkdir()
    (root / ".qagent/e2e.json").write_text(
        json.dumps({"routes": ["/manual", {"path": "/api", "type": "api"}]}),
        encoding="utf-8",
    )
    routes = {item["path"]: item for item in detectar_plan_e2e(root)["routes"]}
    assert routes["/manual"]["eligible"] is True
    assert routes["/api"]["eligible"] is False


def test_limite_de_rutas_es_determinista(tmp_path: Path) -> None:
    root = _project(tmp_path, [f"/{index:02}" for index in range(10)])
    plan = detectar_plan_e2e(root, ConfiguracionE2E(max_routes=3))
    assert [route["path"] for route in plan["routes"]] == ["/00", "/01", "/02"]


def test_vite_detecta_index_y_comando_acotado(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"dev": "vite"}, "devDependencies": {"vite": "7.2.2"}}),
        encoding="utf-8",
    )
    (tmp_path / "index.html").write_text("<h1>hola</h1>", encoding="utf-8")
    (tmp_path / "main.js").write_text(
        "document.body.dataset.ready='1'", encoding="utf-8"
    )
    plan = detectar_plan_e2e(tmp_path)
    assert plan["routes"][0]["path"] == "/"
    assert plan["start_command"][:3] == ["npm", "run", "dev"]


def test_adaptador_sin_soporte_y_proyecto_sin_rutas(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("print('solo análisis')", encoding="utf-8")
    with pytest.raises(ValueError, match="JavaScript"):
        detectar_plan_e2e(tmp_path)


def test_limites_configurables_se_validan() -> None:
    ConfiguracionE2E(
        startup_timeout_s=2, route_timeout_s=3, total_timeout_s=10
    ).validate()
    with pytest.raises(ValueError):
        ConfiguracionE2E(max_routes=0).validate()
    with pytest.raises(ValueError):
        ConfiguracionE2E(memory="20g").validate()


def test_limites_declarados_se_aplican_sin_campos_arbitrarios(tmp_path: Path) -> None:
    root = _project(tmp_path)
    (root / ".qagent").mkdir()
    (root / ".qagent/e2e.json").write_text(
        json.dumps({"limits": {"max_routes": 1, "route_timeout_s": 4}}),
        encoding="utf-8",
    )
    assert len(detectar_plan_e2e(root)["routes"]) == 1
    (root / ".qagent/e2e.json").write_text(
        json.dumps({"limits": {"privileged": True}}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="desconocidos"):
        detectar_plan_e2e(root)
