"""Regresión de #190: auditoría con un repositorio Git padre controlado."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from qagent.config.auditoria import archivos_del_repositorio, buscar_claves

RAIZ = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="Requiere Git")


def _entorno_aislado() -> dict[str, str]:
    """Quita ajustes externos de Git sin cambiar el entorno de la sesión."""
    entorno = os.environ.copy()
    for nombre in (
        "GIT_CEILING_DIRECTORIES",
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_COMMON_DIR",
    ):
        entorno.pop(nombre, None)
    entorno["QAGENT_FAKE_LLM"] = "1"
    return entorno


@pytest.fixture
def repositorio_padre(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Crea un Git independiente; restaura sus variables tras cada prueba."""
    entorno = _entorno_aislado()
    for nombre in os.environ.keys() - entorno.keys():
        monkeypatch.delenv(nombre)
    padre = tmp_path / "repositorio-padre"
    padre.mkdir()
    subprocess.run(
        ["git", "init", "--quiet", str(padre)],
        check=True,
        capture_output=True,
        env=entorno,
        timeout=30,
    )
    return padre


def test_ocho_pruebas_con_git_padre_sin_configuracion_manual(
    repositorio_padre: Path,
) -> None:
    """Las ocho pruebas pasan aunque Git descubra un padre fuera del escenario."""
    temporales = repositorio_padre / "temporales"
    temporales.mkdir()
    entorno = _entorno_aislado()
    descubrimiento = subprocess.run(
        ["git", "-C", str(temporales), "rev-parse", "--show-toplevel"],
        check=True,
        capture_output=True,
        text=True,
        env=entorno,
        timeout=30,
    )
    assert Path(descubrimiento.stdout.strip()).resolve() == repositorio_padre.resolve()
    archivos = subprocess.run(
        ["git", "-C", str(temporales), "ls-files", "-z"],
        check=True,
        capture_output=True,
        env=entorno,
        timeout=30,
    )
    assert archivos.stdout == b""  # Condición que antes ocultaba los valores ficticios.
    resultado = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/config/test_auditoria.py",
            "-q",
            "--basetemp",
            str(temporales),
        ],
        check=False,
        cwd=RAIZ,
        capture_output=True,
        text=True,
        env=entorno,
        timeout=180,
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    print("Git padre controlado; sin configuración manual de Git:", flush=True)
    print(resultado.stdout, flush=True)


def test_auditoria_conserva_archivos_versionados_y_excluye_env_local(
    repositorio_padre: Path,
) -> None:
    """Detecta solo el valor ficticio versionado, sin examinar el .env local."""
    valor = "aB1c" * 5
    for nombre in ("versionado.py", "no_versionado.py", ".env"):
        (repositorio_padre / nombre).write_text(
            f'SECRET = "{valor}"\n', encoding="utf-8"
        )
    subprocess.run(
        ["git", "-C", str(repositorio_padre), "add", "--", "versionado.py"],
        check=True,
        capture_output=True,
        env=_entorno_aislado(),
        timeout=30,
    )
    assert archivos_del_repositorio(repositorio_padre) == [
        repositorio_padre / "versionado.py"
    ]
    hallazgos = buscar_claves(repositorio_padre)
    assert [(h.archivo, h.linea) for h in hallazgos] == [("versionado.py", 1)]
    assert valor not in str(hallazgos)
    print(
        "Auditoría: detección versionada conservada; .env local excluido.", flush=True
    )
