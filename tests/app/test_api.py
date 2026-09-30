"""Pruebas del puente Api sin pywebview (HU-01).

Incluye la evidencia del criterio 5: una carpeta con .py queda en
recientes.json y una carpeta vacía no.
"""

import json
import shutil

import pytest

from pyagent.app.api import Api
from pyagent.app.project_loader import MSG_SIN_PY


@pytest.fixture
def archivo(tmp_path):
    return tmp_path / "home" / ".pyagent" / "recientes.json"


@pytest.fixture
def con_py(tmp_path):
    carpeta = tmp_path / "con_py"
    (carpeta / "pkg").mkdir(parents=True)
    (carpeta / "pkg" / "calc.py").write_text("def suma(a, b):\n    return a + b\n", "utf-8")
    (carpeta / "requirements.txt").write_text("", "utf-8")
    return carpeta


@pytest.fixture
def vacia(tmp_path):
    carpeta = tmp_path / "vacia"
    carpeta.mkdir()
    return carpeta


def _rutas(archivo):
    if not archivo.exists():
        return []
    return [e["ruta"] for e in json.loads(archivo.read_text(encoding="utf-8"))]


def test_criterio_5_evidencia(archivo, con_py, vacia):
    api = Api(recent_path=archivo)

    assert api.open_project(str(con_py))["ok"]
    resultado_vacia = api.open_project(str(vacia))

    assert not resultado_vacia["ok"]
    assert resultado_vacia["error"] == MSG_SIN_PY
    assert _rutas(archivo) == [str(con_py.resolve())]


def test_inspect_no_escribe_recientes(archivo, con_py):
    resultado = Api(recent_path=archivo).inspect_folder(str(con_py))

    assert resultado["ok"]
    assert resultado["py_count"] == 1
    assert resultado["has_requirements"] is True
    assert not archivo.exists()


def test_inspect_carpeta_vacia_da_mensaje_exacto(archivo, vacia):
    resultado = Api(recent_path=archivo).inspect_folder(str(vacia))

    assert resultado["ok"] is False
    assert resultado["error"] == "Esta carpeta no contiene archivos .py"
    assert resultado["py_count"] == 0


def test_py_solo_en_venv_no_se_guarda(archivo, tmp_path):
    carpeta = tmp_path / "solo_venv"
    (carpeta / ".venv").mkdir(parents=True)
    (carpeta / ".venv" / "x.py").write_text("", "utf-8")

    assert not Api(recent_path=archivo).open_project(str(carpeta))["ok"]
    assert _rutas(archivo) == []


def test_pick_folder_cancelado(archivo):
    assert Api(recent_path=archivo, folder_picker=lambda: None).pick_folder() == {"cancelado": True}


def test_pick_folder_devuelve_ruta(archivo, con_py):
    api = Api(recent_path=archivo, folder_picker=lambda: str(con_py))

    assert api.pick_folder() == {"cancelado": False, "ruta": str(con_py)}


def test_revalidar_reciente_que_ya_no_existe(archivo, con_py):
    api = Api(recent_path=archivo)
    api.open_project(str(con_py))
    ruta = api.list_recent()[0]["ruta"]
    shutil.rmtree(con_py)

    resultado = api.open_project(ruta)

    assert not resultado["ok"]
    assert "no existe" in resultado["error"]
    assert api.remove_recent(ruta) == []
    assert api.list_recent() == []


def test_reabrir_reciente_no_duplica(archivo, con_py):
    api = Api(recent_path=archivo)
    api.open_project(str(con_py))
    api.open_project(str(con_py))

    assert len(api.list_recent()) == 1
