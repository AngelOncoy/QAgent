"""Registro predeterminado y esqueletos de JS/TS y Java (EN-17)."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from qagent import contracts
from qagent.lenguajes import (
    REGISTRO,
    JavaAdapter,
    JavaScriptAdapter,
    NoImplementado,
    TypeScriptAdapter,
    adaptador_para,
    detectar_lenguaje,
)

RAIZ_PAQUETE = Path(__file__).resolve().parents[2] / "src" / "qagent" / "lenguajes"


def test_hay_un_adaptador_por_cada_lenguaje_de_los_contratos() -> None:
    assert set(REGISTRO.lenguajes) == set(contracts.LENGUAJES)


@pytest.mark.parametrize("lenguaje", contracts.LENGUAJES)
def test_frameworks_del_adaptador_son_los_del_contrato(lenguaje: str) -> None:
    adaptador = adaptador_para(lenguaje)
    assert set(adaptador.frameworks_pruebas) == set(
        contracts.FRAMEWORKS_PRUEBAS[lenguaje]
    )
    assert set(adaptador.frameworks_app) == set(contracts.FRAMEWORKS_APP[lenguaje])


@pytest.mark.parametrize(
    ("archivos", "esperado"),
    [
        (["package.json", "src/index.js", "src/app.jsx"], "javascript"),
        (["package.json", "tsconfig.json", "src/a.ts", "src/b.tsx"], "typescript"),
        (["pom.xml", "src/main/java/App.java"], "java"),
        (["build.gradle.kts", "App.java"], "java"),
        (["main.py", "requirements.txt"], "python"),
    ],
)
def test_deteccion_basica_de_cada_lenguaje(archivos: list[str], esperado: str) -> None:
    assert REGISTRO.detectar_en(archivos)[0].lenguaje == esperado


def test_los_d_ts_no_cuentan_como_typescript() -> None:
    assert TypeScriptAdapter().detectar(["types/index.d.ts"]) is None


def test_proyecto_typescript_con_un_js_de_configuracion() -> None:
    detecciones = REGISTRO.detectar_en(
        ["package.json", "tsconfig.json", "jest.config.js", "src/a.ts", "src/b.ts"]
    )
    assert [d.lenguaje for d in detecciones] == ["typescript", "javascript"]


def test_detectar_lenguaje_en_disco(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "index.js").write_text("module.exports = {}", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "dep.ts").write_text("", encoding="utf-8")
    [deteccion] = detectar_lenguaje(tmp_path)
    assert deteccion.lenguaje == "javascript"


@pytest.mark.parametrize("clase", [JavaScriptAdapter, TypeScriptAdapter, JavaAdapter])
def test_los_esqueletos_avisan_lo_que_falta(clase: type, tmp_path: Path) -> None:
    with pytest.raises(NoImplementado, match=clase.lenguaje):
        clase().analizar(tmp_path)


def test_el_paquete_no_depende_de_la_interfaz() -> None:
    """La lógica no importa qagent.app ni webview (AGENTS.md)."""
    for archivo in RAIZ_PAQUETE.glob("*.py"):
        arbol = ast.parse(archivo.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                nombres = [a.name for a in nodo.names]
            elif isinstance(nodo, ast.ImportFrom):
                nombres = [nodo.module or ""]
            else:
                continue
            for nombre in nombres:
                assert not nombre.startswith(("qagent.app", "webview")), archivo.name


def test_importar_el_paquete_no_carga_la_interfaz() -> None:
    codigo = (
        "import sys, qagent.lenguajes; "
        "print(any(m.startswith(('qagent.app', 'webview')) for m in sys.modules))"
    )
    salida = subprocess.run(
        [sys.executable, "-c", codigo], capture_output=True, text=True, check=True
    )
    assert salida.stdout.strip() == "False"
