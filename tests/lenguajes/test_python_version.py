"""Pruebas unitarias sin Docker de la detección y resolución de versiones de Python (ADR-013)."""

from __future__ import annotations

from pathlib import Path

import pytest

from qagent.config import SandboxPython
from qagent.lenguajes.python import PythonAdapter
from qagent.lenguajes.python_version import (
    VersionPythonNoSoportada,
    detectar_declaracion_version,
    elegir_version_python,
    resolver_version_python_proyecto,
)
from qagent.sandbox.modelos import IMAGEN_BASE

SOPORTADAS = ("3.10", "3.11", "3.12", "3.13", "3.14")


# --- Detección en archivos --------------------------------------------------


def test_detectar_desde_python_version_simple(tmp_path: Path) -> None:
    (tmp_path / ".python-version").write_text("3.12\n", encoding="utf-8")
    resultado = detectar_declaracion_version(tmp_path)
    assert resultado == (".python-version", "3.12")


def test_detectar_desde_python_version_con_patch_y_prefijo(tmp_path: Path) -> None:
    (tmp_path / ".python-version").write_text("cpython-3.12.3\n", encoding="utf-8")
    resultado = detectar_declaracion_version(tmp_path)
    assert resultado == (".python-version", "3.12.3")


def test_detectar_desde_pyproject_toml(tmp_path: Path) -> None:
    contenido = """\
[project]
name = "demo"
version = "0.1.0"
requires-python = ">=3.10, <3.13"
"""
    (tmp_path / "pyproject.toml").write_text(contenido, encoding="utf-8")
    resultado = detectar_declaracion_version(tmp_path)
    assert resultado == ("pyproject.toml", ">=3.10, <3.13")


def test_detectar_desde_setup_cfg(tmp_path: Path) -> None:
    contenido = """\
[metadata]
name = demo

[options]
python_requires = >=3.11
"""
    (tmp_path / "setup.cfg").write_text(contenido, encoding="utf-8")
    resultado = detectar_declaracion_version(tmp_path)
    assert resultado == ("setup.cfg", ">=3.11")


def test_precedencia_python_version_sobre_pyproject_y_setup_cfg(
    tmp_path: Path,
) -> None:
    (tmp_path / ".python-version").write_text("3.10\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nrequires-python = ">=3.12"\n', encoding="utf-8"
    )
    (tmp_path / "setup.cfg").write_text(
        "[options]\npython_requires = >=3.13\n", encoding="utf-8"
    )

    resultado = detectar_declaracion_version(tmp_path)
    assert resultado == (".python-version", "3.10")


def test_precedencia_pyproject_sobre_setup_cfg(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nrequires-python = ">=3.12"\n', encoding="utf-8"
    )
    (tmp_path / "setup.cfg").write_text(
        "[options]\npython_requires = >=3.13\n", encoding="utf-8"
    )

    resultado = detectar_declaracion_version(tmp_path)
    assert resultado == ("pyproject.toml", ">=3.12")


def test_sin_declaracion_devuelve_none(tmp_path: Path) -> None:
    assert detectar_declaracion_version(tmp_path) is None


# --- Reglas de elección y rangos -------------------------------------------


def test_sin_declaracion_elige_version_por_defecto() -> None:
    assert elegir_version_python(None, SOPORTADAS, "3.11") == "3.11"
    assert elegir_version_python("", SOPORTADAS, "3.11") == "3.11"


def test_version_exacta_soportada() -> None:
    assert elegir_version_python("3.10", SOPORTADAS) == "3.10"
    assert elegir_version_python("3.12", SOPORTADAS) == "3.12"
    assert elegir_version_python("3.12.4", SOPORTADAS) == "3.12"


def test_rango_abierto_elige_la_mas_alta_de_la_lista() -> None:
    # >=3.10 es satisfecho por 3.10..3.14 -> elige 3.14
    assert elegir_version_python(">=3.10", SOPORTADAS) == "3.14"
    # >=3.12 es satisfecho por 3.12..3.14 -> elige 3.14
    assert elegir_version_python(">=3.12", SOPORTADAS) == "3.14"


def test_rango_acotado_elige_la_mas_alta_que_lo_cumple() -> None:
    # >=3.10, <3.13 es satisfecho por 3.10, 3.11, 3.12 -> elige 3.12
    assert elegir_version_python(">=3.10, <3.13", SOPORTADAS) == "3.12"
    # >=3.11, <=3.12 es satisfecho por 3.11, 3.12 -> elige 3.12
    assert elegir_version_python(">=3.11, <=3.12", SOPORTADAS) == "3.12"
    # ==3.10.* -> elige 3.10
    assert elegir_version_python("==3.10.*", SOPORTADAS) == "3.10"


def test_version_fuera_de_rango_lanza_error_con_mensaje_claro() -> None:
    with pytest.raises(VersionPythonNoSoportada) as exc_info:
        elegir_version_python("3.9", SOPORTADAS)
    mensaje = str(exc_info.value)
    assert "El proyecto requiere Python 3.9" in mensaje
    assert "QAgent soporta Python 3.10–3.14" in mensaje
    assert "3.10, 3.11, 3.12, 3.13, 3.14" in mensaje


def test_rango_no_satisfecho_lanza_error_con_mensaje_claro() -> None:
    with pytest.raises(VersionPythonNoSoportada) as exc_info:
        elegir_version_python(">=3.15", SOPORTADAS)
    mensaje = str(exc_info.value)
    assert "El proyecto requiere Python >=3.15" in mensaje
    assert "QAgent soporta Python 3.10–3.14" in mensaje

    with pytest.raises(VersionPythonNoSoportada):
        elegir_version_python("<3.10", SOPORTADAS)


# --- Integración con PythonAdapter ------------------------------------------


def test_adaptador_resuelve_version_proyecto(tmp_path: Path) -> None:
    (tmp_path / ".python-version").write_text("3.12\n", encoding="utf-8")
    adaptador = PythonAdapter()
    version = adaptador.resolver_version_python(tmp_path)
    assert version == "3.12"


def test_adaptador_entorno_sandbox_con_ruta_genera_etiqueta_versionada(
    tmp_path: Path,
) -> None:
    (tmp_path / ".python-version").write_text("3.12\n", encoding="utf-8")
    adaptador = PythonAdapter()
    entorno = adaptador.entorno_sandbox(tmp_path)
    assert entorno.imagen == "qagent-sandbox:base-py3.12"


def test_adaptador_entorno_sandbox_con_ruta_por_defecto_conserva_base(
    tmp_path: Path,
) -> None:
    (tmp_path / ".python-version").write_text("3.11\n", encoding="utf-8")
    adaptador = PythonAdapter()
    entorno = adaptador.entorno_sandbox(tmp_path)
    assert entorno.imagen == IMAGEN_BASE


def test_adaptador_entorno_sandbox_sin_ruta_conserva_imagen_base() -> None:
    adaptador = PythonAdapter()
    entorno = adaptador.entorno_sandbox()
    assert entorno.imagen == IMAGEN_BASE


def test_resolver_con_config_personalizada(tmp_path: Path) -> None:
    (tmp_path / ".python-version").write_text("3.12\n", encoding="utf-8")
    cfg_limitada = SandboxPython(
        versiones_soportadas=("3.10", "3.11"), version_por_defecto="3.11"
    )
    with pytest.raises(VersionPythonNoSoportada):
        resolver_version_python_proyecto(tmp_path, config_sandbox=cfg_limitada)
