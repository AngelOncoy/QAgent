"""Migración de las carpetas de datos de PyAgent a QAgent (`.pyagent/` → `.qagent/`).

Quien ya usó versiones anteriores no debe perder corridas, specs, pruebas aprobadas ni
proyectos recientes al actualizar.
"""

from __future__ import annotations

from pathlib import Path

from pyagent.almacenamiento import AlmacenProyecto, recientes
from pyagent.almacenamiento.proyecto import CARPETA, migrar_carpeta_anterior
from pyagent.sandbox.ejecucion import EXCLUIDOS_DE_LA_COPIA
from pyagent.storage.registro import CARPETA_RUNS


def _carpeta_anterior_con_datos(raiz: Path) -> Path:
    anterior = raiz / ".pyagent"
    (anterior / "specs").mkdir(parents=True)
    (anterior / "specs" / "pricing.spec.json").write_text("{}", encoding="utf-8")
    return anterior


def test_los_nombres_nuevos_son_qagent():
    assert CARPETA == ".qagent"
    assert CARPETA_RUNS == Path(".qagent") / "runs"
    assert recientes.ruta_por_defecto() == Path.home() / ".qagent" / "recientes.json"


def test_inicializar_migra_la_carpeta_anterior_sin_perder_datos(tmp_path: Path):
    _carpeta_anterior_con_datos(tmp_path)

    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()

    assert not (tmp_path / ".pyagent").exists()
    assert (tmp_path / ".qagent" / "specs" / "pricing.spec.json").read_text(
        encoding="utf-8"
    ) == "{}"
    assert almacen.existe()


def test_no_pisa_una_carpeta_qagent_existente(tmp_path: Path):
    _carpeta_anterior_con_datos(tmp_path)
    (tmp_path / ".qagent").mkdir()

    assert migrar_carpeta_anterior(tmp_path) is False
    assert (tmp_path / ".pyagent" / "specs" / "pricing.spec.json").exists()
    assert list((tmp_path / ".qagent").iterdir()) == []


def test_sin_carpeta_anterior_no_hace_nada(tmp_path: Path):
    assert migrar_carpeta_anterior(tmp_path) is False
    assert list(tmp_path.iterdir()) == []


def test_migra_los_recientes_del_home(tmp_path: Path):
    (tmp_path / ".pyagent").mkdir()
    (tmp_path / ".pyagent" / "recientes.json").write_text("[]", encoding="utf-8")

    assert recientes.migrar_carpeta_anterior(tmp_path) is True
    assert (tmp_path / ".qagent" / "recientes.json").read_text(encoding="utf-8") == "[]"
    assert not (tmp_path / ".pyagent").exists()


def test_recientes_no_pisa_un_home_ya_migrado(tmp_path: Path):
    (tmp_path / ".pyagent").mkdir()
    (tmp_path / ".qagent").mkdir()

    assert recientes.migrar_carpeta_anterior(tmp_path) is False
    assert (tmp_path / ".pyagent").is_dir()


def test_el_sandbox_no_copia_ninguna_de_las_dos_carpetas():
    assert ".qagent" in EXCLUIDOS_DE_LA_COPIA
    assert ".pyagent" in EXCLUIDOS_DE_LA_COPIA
