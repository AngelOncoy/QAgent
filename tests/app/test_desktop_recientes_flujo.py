"""Pruebas del flujo de proyectos recientes y estado de pruebas previas en DesktopAPI."""

from __future__ import annotations

from pathlib import Path

import pytest

from qagent.almacenamiento import AlmacenProyecto, recientes
from qagent.app import desktop


@pytest.fixture
def archivo_recientes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Aísla el archivo de recientes del home real."""
    archivo = tmp_path / "home" / ".qagent" / "recientes.json"
    monkeypatch.setattr(desktop.recientes, "ruta_por_defecto", lambda: archivo)
    return archivo


def _crear_proyecto(tmp_path: Path, nombre: str = "mi_proyecto") -> Path:
    carpeta = tmp_path / nombre
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "modulo.py").write_text(
        "def suma(a, b): return a + b\n", encoding="utf-8"
    )
    return carpeta


def test_abrir_proyecto_carpeta_registra_en_recientes_y_devuelve_estado(
    tmp_path: Path, archivo_recientes: Path
) -> None:
    """Abrir una carpeta registra origen 'local' y devuelve indicadores de pruebas."""
    carpeta = _crear_proyecto(tmp_path)
    api = desktop.DesktopAPI()

    res = api.abrir_proyecto(str(carpeta))

    assert res["ok"] is True
    assert res["ya_cargo_prueba"] is False
    assert res["tiene_pruebas"] is False
    assert res["tiene_corridas"] is False

    recientes_lista = recientes.cargar(archivo_recientes)
    assert len(recientes_lista) == 1
    assert recientes_lista[0]["origen"] == "local"
    assert recientes_lista[0]["nombre"] == carpeta.name
    assert recientes_lista[0]["ruta"] == str(carpeta)


def test_abrir_reciente_detecta_si_ya_cargo_prueba(
    tmp_path: Path, archivo_recientes: Path
) -> None:
    """abrir_reciente devuelve ya_cargo_prueba=True si el proyecto ya tiene corridas."""
    carpeta = _crear_proyecto(tmp_path)
    api = desktop.DesktopAPI()
    api.abrir_proyecto(str(carpeta))

    # Simulamos una corrida en el almacén del proyecto
    almacen = AlmacenProyecto(str(carpeta))
    run = almacen.crear_run(["funcion"])
    almacen.finalizar_run(run["run_id"], "fin", 1, 0)
    recientes.registrar_corrida(str(carpeta), archivo=archivo_recientes)

    res = api.abrir_reciente(str(carpeta))

    assert res["ok"] is True
    assert res["origen"] == "local"
    assert res["tiene_corridas"] is True
    assert res["ya_cargo_prueba"] is True
    assert res["ultima_corrida"] is not None


def test_abrir_reciente_git_conserva_origen_y_url(
    tmp_path: Path, archivo_recientes: Path
) -> None:
    """Un proyecto clonado con Git conserva origen 'git' y url al reabrirse."""
    carpeta = _crear_proyecto(tmp_path, "repo_git")
    url = "https://github.com/usuario/repo_git.git"
    recientes.registrar(
        carpeta.name, "git", str(carpeta), url=url, archivo=archivo_recientes
    )

    api = desktop.DesktopAPI()
    res = api.abrir_reciente(str(carpeta))

    assert res["ok"] is True
    assert res["origen"] == "git"
    assert res["url"] == url
    assert res["ya_cargo_prueba"] is False
