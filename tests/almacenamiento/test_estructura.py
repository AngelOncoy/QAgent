"""EN-07 (criterio 1): estructura `.pyagent/` dentro del proyecto abierto."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from pyagent.almacenamiento import AlmacenProyecto
from pyagent.almacenamiento.proyecto import CONTENIDO_GITIGNORE
from pyagent.app import desktop


def test_no_toca_el_disco_hasta_inicializar(tmp_path: Path):
    almacen = AlmacenProyecto(tmp_path)

    assert not almacen.existe()
    assert list(tmp_path.iterdir()) == []


def test_inicializar_crea_runs_specs_tests_y_gitignore(tmp_path: Path):
    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()

    carpeta = tmp_path / ".pyagent"
    assert almacen.existe()
    assert sorted(p.name for p in carpeta.iterdir()) == [
        ".gitignore",
        "runs",
        "specs",
        "tests",
    ]
    assert all((carpeta / n).is_dir() for n in ("runs", "specs", "tests"))
    lineas = (carpeta / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "runs/" in lineas
    assert "specs/" not in lineas and "tests/" not in lineas


def test_inicializar_es_idempotente(tmp_path: Path):
    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()
    (almacen.carpeta_specs / "a.json").write_text("{}", encoding="utf-8")

    almacen.inicializar()
    almacen.inicializar()

    assert (almacen.carpeta_specs / "a.json").read_text(encoding="utf-8") == "{}"
    gitignore = almacen.carpeta / ".gitignore"
    assert gitignore.read_text(encoding="utf-8") == CONTENIDO_GITIGNORE


def test_inicializar_respeta_un_gitignore_editado_por_el_usuario(tmp_path: Path):
    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()
    gitignore = almacen.carpeta / ".gitignore"
    gitignore.write_text("runs/\nspecs/\n", encoding="utf-8")

    almacen.inicializar()

    assert gitignore.read_text(encoding="utf-8") == "runs/\nspecs/\n"


# --- Integración con el puente de escritorio ---------------------------------------


@pytest.fixture
def api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> desktop.DesktopAPI:
    """Puente sin ventana y con recientes en un home temporal (nunca el real)."""
    archivo = tmp_path / "home" / ".pyagent" / "recientes.json"
    monkeypatch.setattr(desktop.recientes, "ruta_por_defecto", lambda: archivo)
    return desktop.DesktopAPI()


def _proyecto(tmp_path: Path) -> Path:
    carpeta = tmp_path / "proyecto"
    carpeta.mkdir()
    (carpeta / "calc.py").write_text("def sumar(a, b):\n    return a + b\n")
    return carpeta


def test_abrir_proyecto_crea_pyagent(api, tmp_path: Path):
    carpeta = _proyecto(tmp_path)

    assert api.abrir_proyecto(str(carpeta))["ok"]

    assert (carpeta / ".pyagent" / "runs").is_dir()


def test_abrir_reciente_crea_pyagent_si_falta(api, tmp_path: Path):
    carpeta = _proyecto(tmp_path)
    api.abrir_proyecto(str(carpeta))
    shutil.rmtree(carpeta / ".pyagent")

    assert api.abrir_reciente(str(carpeta))["ok"]

    assert (carpeta / ".pyagent" / "specs").is_dir()


def test_si_no_se_puede_crear_pyagent_el_proyecto_se_abre_igual(
    api, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    def falla(self):
        raise PermissionError("carpeta de solo lectura")

    monkeypatch.setattr(AlmacenProyecto, "inicializar", falla)
    carpeta = _proyecto(tmp_path)

    assert api.abrir_proyecto(str(carpeta))["ok"]
    assert not (carpeta / ".pyagent").exists()
