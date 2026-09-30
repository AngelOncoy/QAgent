"""Pruebas de la inspección de carpetas (HU-01)."""

import os

import pytest

from pyagent.app.project_loader import IGNORED_DIRS, FolderError, inspect_folder


def _touch(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x = 1\n", encoding="utf-8")


def test_cuenta_py_de_forma_recursiva(tmp_path):
    _touch(tmp_path / "main.py")
    _touch(tmp_path / "pkg" / "mod.py")
    _touch(tmp_path / "pkg" / "sub" / "otro.py")
    _touch(tmp_path / "README.md")

    info = inspect_folder(tmp_path)

    assert info.py_count == 3
    assert info.has_python
    assert info.nombre == tmp_path.name
    assert info.ruta == str(tmp_path.resolve())


def test_carpeta_vacia_no_tiene_py(tmp_path):
    info = inspect_folder(tmp_path)

    assert info.py_count == 0
    assert not info.has_python


def test_py_solo_dentro_de_venv_cuenta_como_sin_py(tmp_path):
    _touch(tmp_path / ".venv" / "Lib" / "site-packages" / "lib.py")
    _touch(tmp_path / "__pycache__" / "x.py")

    assert inspect_folder(tmp_path).py_count == 0


@pytest.mark.parametrize("ignored", sorted(IGNORED_DIRS))
def test_ignora_cada_carpeta_excluida(tmp_path, ignored):
    _touch(tmp_path / ignored / "a.py")
    _touch(tmp_path / "ok.py")

    assert inspect_folder(tmp_path).py_count == 1


def test_detecta_requirements(tmp_path):
    _touch(tmp_path / "app.py")
    assert not inspect_folder(tmp_path).has_requirements

    (tmp_path / "requirements.txt").write_text("pytest\n", encoding="utf-8")
    assert inspect_folder(tmp_path).has_requirements


def test_carpeta_inexistente_lanza_error_en_espanol(tmp_path):
    with pytest.raises(FolderError, match="no existe"):
        inspect_folder(tmp_path / "no-esta")


def test_archivo_en_lugar_de_carpeta_lanza_error(tmp_path):
    archivo = tmp_path / "a.py"
    _touch(archivo)

    with pytest.raises(FolderError, match="no es una carpeta"):
        inspect_folder(archivo)


def test_no_sigue_enlaces_simbolicos(tmp_path):
    externo = tmp_path / "externo"
    _touch(externo / "fuera.py")
    proyecto = tmp_path / "proyecto"
    proyecto.mkdir()
    try:
        os.symlink(externo, proyecto / "enlace", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("El sistema no permite crear enlaces simbólicos")

    assert inspect_folder(proyecto).py_count == 0


def test_sin_permiso_de_lectura_lanza_error_claro(tmp_path, monkeypatch):
    def _denegado(path):
        raise PermissionError(13, "Acceso denegado", str(path))

    monkeypatch.setattr("pyagent.app.project_loader.os.scandir", _denegado)

    with pytest.raises(FolderError, match="No tienes permiso de lectura"):
        inspect_folder(tmp_path)
