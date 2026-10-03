"""Pruebas de la validación de carpetas locales (HU-01)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pyagent.analysis import analizar_proyecto
from pyagent.app.proyecto_local import SIN_ARCHIVOS_PY, inspeccionar_carpeta


def _crear(
    raiz: Path, relativa: str, contenido: str = "def f():\n    return 1\n"
) -> None:
    """Crea un archivo (y sus carpetas) dentro de ``raiz``."""
    ruta = raiz / relativa
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(contenido, encoding="utf-8")


def test_carpeta_con_py_es_valida(tmp_path: Path) -> None:
    proyecto = tmp_path / "ecommerce-core"
    _crear(proyecto, "app.py")
    _crear(proyecto, "services/pagos.py")

    resultado = inspeccionar_carpeta(str(proyecto))

    assert resultado == {
        "ok": True,
        "nombre": "ecommerce-core",
        "ruta": os.path.abspath(proyecto),
        "cantidad_py": 2,
        "error": None,
    }


def test_carpeta_vacia_no_es_valida(tmp_path: Path) -> None:
    resultado = inspeccionar_carpeta(str(tmp_path))

    assert resultado["ok"] is False
    assert resultado["cantidad_py"] == 0
    assert resultado["error"] == "Esta carpeta no contiene archivos .py"


def test_carpeta_sin_py_pero_con_otros_archivos(tmp_path: Path) -> None:
    _crear(tmp_path, "index.html", "<html></html>")
    _crear(tmp_path, "README.md", "# hola")

    resultado = inspeccionar_carpeta(str(tmp_path))

    assert resultado["ok"] is False
    assert resultado["error"] == SIN_ARCHIVOS_PY


@pytest.mark.parametrize(
    "relativa",
    [
        ".venv/lib/modulo.py",
        "venv/lib/modulo.py",
        "tests/test_algo.py",
        "__pycache__/x.py",
        "node_modules/paquete/x.py",
        ".git/hooks/x.py",
        "mi_paquete.egg-info/x.py",
        "mutants/x.py",
    ],
)
def test_py_solo_en_carpetas_ignoradas_cuenta_como_sin_py(
    tmp_path: Path, relativa: str
) -> None:
    _crear(tmp_path, relativa)

    resultado = inspeccionar_carpeta(str(tmp_path))

    assert resultado["ok"] is False
    assert resultado["cantidad_py"] == 0
    assert resultado["error"] == SIN_ARCHIVOS_PY


def test_mismo_criterio_de_exclusion_que_el_analizador(tmp_path: Path) -> None:
    for relativa in (
        "main.py",
        "pkg/__init__.py",
        "pkg/util.py",
        "tests/test_main.py",
        ".venv/x.py",
        "build.egg-info/x.py",
        "pkg/__pycache__/util.py",
        "notas.txt",
    ):
        _crear(tmp_path, relativa)

    resultado = inspeccionar_carpeta(str(tmp_path))

    assert resultado["cantidad_py"] == 3
    assert resultado["cantidad_py"] == len(analizar_proyecto(tmp_path)["modulos"])


def test_carpeta_inexistente_da_error_claro(tmp_path: Path) -> None:
    ruta = tmp_path / "no-existe"

    resultado = inspeccionar_carpeta(str(ruta))

    assert resultado["ok"] is False
    assert resultado["error"] == f"La carpeta no existe: {os.path.abspath(ruta)}"
    assert "Traceback" not in resultado["error"]


def test_ruta_que_es_un_archivo_da_error_claro(tmp_path: Path) -> None:
    _crear(tmp_path, "solo.py")

    resultado = inspeccionar_carpeta(str(tmp_path / "solo.py"))

    assert resultado["ok"] is False
    assert resultado["error"].startswith("La ruta no es una carpeta:")


def test_ruta_vacia_da_error_claro() -> None:
    resultado = inspeccionar_carpeta("   ")

    assert resultado["ok"] is False
    assert resultado["error"] == "No se indicó ninguna carpeta."


def test_carpeta_sin_permisos_da_error_claro(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _crear(tmp_path, "app.py")

    def _denegar(_ruta: object) -> None:
        raise PermissionError("acceso denegado")

    monkeypatch.setattr("pyagent.app.proyecto_local.os.scandir", _denegar)

    resultado = inspeccionar_carpeta(str(tmp_path))

    assert resultado["ok"] is False
    assert resultado["error"].startswith("No hay permisos para leer la carpeta:")
