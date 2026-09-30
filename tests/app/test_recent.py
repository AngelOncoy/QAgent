"""Pruebas de la lista de proyectos recientes (HU-01)."""

import json
import logging
from datetime import datetime, timezone

import pytest

from pyagent.app.project_loader import ProjectInfo
from pyagent.app.recent import MAX_RECENT, add_recent, load_recent, remove_recent


def _info(tmp_path, nombre, py_count=1):
    ruta = tmp_path / nombre
    return ProjectInfo(nombre=nombre, ruta=str(ruta), py_count=py_count, has_requirements=False)


@pytest.fixture
def archivo(tmp_path):
    return tmp_path / "home" / ".pyagent" / "recientes.json"


def test_sin_archivo_la_lista_esta_vacia(archivo):
    assert load_recent(archivo) == []


def test_agrega_y_crea_la_carpeta(tmp_path, archivo):
    momento = datetime(2026, 9, 30, 10, 0, tzinfo=timezone.utc)

    add_recent(_info(tmp_path, "demo"), archivo, now=momento)

    datos = json.loads(archivo.read_text(encoding="utf-8"))
    assert datos == [
        {
            "nombre": "demo",
            "ruta": str(tmp_path / "demo"),
            "py_count": 1,
            "has_requirements": False,
            "ultimo_uso": "2026-09-30T10:00:00+00:00",
        }
    ]


def test_no_guarda_proyectos_sin_py(tmp_path, archivo):
    with pytest.raises(ValueError):
        add_recent(_info(tmp_path, "vacio", py_count=0), archivo)

    assert not archivo.exists()


def test_sin_duplicados_actualiza_fecha_y_sube_al_primer_lugar(tmp_path, archivo):
    t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2026, 2, 1, tzinfo=timezone.utc)
    add_recent(_info(tmp_path, "a"), archivo, now=t1)
    add_recent(_info(tmp_path, "b"), archivo, now=t1)

    add_recent(_info(tmp_path, "a"), archivo, now=t2)

    lista = load_recent(archivo)
    assert [e["nombre"] for e in lista] == ["a", "b"]
    assert lista[0]["ultimo_uso"] == t2.isoformat(timespec="seconds")


def test_limite_de_diez_mas_reciente_primero(tmp_path, archivo):
    for i in range(MAX_RECENT + 3):
        add_recent(_info(tmp_path, f"p{i}"), archivo)

    lista = load_recent(archivo)
    assert len(lista) == MAX_RECENT
    assert lista[0]["nombre"] == f"p{MAX_RECENT + 2}"
    assert "p0" not in [e["nombre"] for e in lista]


def test_json_corrupto_no_rompe_y_se_reinicia(tmp_path, archivo, caplog):
    archivo.parent.mkdir(parents=True)
    archivo.write_text("{esto no es json", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        assert load_recent(archivo) == []
    assert "recientes.json" in caplog.text

    add_recent(_info(tmp_path, "nuevo"), archivo)
    assert [e["nombre"] for e in load_recent(archivo)] == ["nuevo"]


def test_formato_inesperado_se_trata_como_vacio(archivo):
    archivo.parent.mkdir(parents=True)
    archivo.write_text('{"ruta": "x"}', encoding="utf-8")

    assert load_recent(archivo) == []


def test_utf8_con_tildes(tmp_path, archivo):
    add_recent(_info(tmp_path, "gestión-año"), archivo)

    assert "gestión-año" in archivo.read_text(encoding="utf-8")
    assert load_recent(archivo)[0]["nombre"] == "gestión-año"


def test_no_deja_temporales(tmp_path, archivo):
    add_recent(_info(tmp_path, "a"), archivo)

    assert [p.name for p in archivo.parent.iterdir()] == ["recientes.json"]


def test_quitar_reciente(tmp_path, archivo):
    add_recent(_info(tmp_path, "a"), archivo)
    add_recent(_info(tmp_path, "b"), archivo)

    remove_recent(str(tmp_path / "a"), archivo)

    assert [e["nombre"] for e in load_recent(archivo)] == ["b"]
