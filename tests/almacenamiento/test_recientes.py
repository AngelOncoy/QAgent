"""Pruebas del registro de proyectos recientes (HU-01)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pyagent.almacenamiento import recientes
from pyagent.proyectos.proyecto_local import inspeccionar_carpeta

MOMENTO = datetime(2026, 10, 3, 9, 30, 15, tzinfo=timezone.utc)


@pytest.fixture
def archivo(tmp_path: Path) -> Path:
    """Archivo de recientes temporal: nunca se toca el home real."""
    return tmp_path / "home" / ".pyagent" / "recientes.json"


def _abrir(ruta: Path, archivo: Path) -> dict:
    """Reproduce ``DesktopAPI.abrir_proyecto`` sin pywebview."""
    proyecto = inspeccionar_carpeta(str(ruta))
    if proyecto["ok"]:
        recientes.registrar(
            proyecto["nombre"], "local", proyecto["ruta"], archivo=archivo
        )
    return proyecto


def test_ruta_por_defecto_esta_en_el_home() -> None:
    assert recientes.ruta_por_defecto() == Path.home() / ".pyagent" / "recientes.json"


def test_evidencia_criterio_5_solo_se_registra_la_carpeta_con_py(
    tmp_path: Path, archivo: Path
) -> None:
    con_py = tmp_path / "con-py"
    (con_py / "pkg").mkdir(parents=True)
    (con_py / "pkg" / "modulo.py").write_text("x = 1\n", encoding="utf-8")
    vacia = tmp_path / "vacia"
    vacia.mkdir()

    assert _abrir(con_py, archivo)["ok"] is True
    assert _abrir(vacia, archivo)["ok"] is False

    guardadas = json.loads(archivo.read_text(encoding="utf-8"))
    rutas = [e["ruta"] for e in guardadas]
    assert rutas == [str(con_py)]
    assert str(vacia) not in rutas


def test_formato_de_la_entrada(archivo: Path) -> None:
    recientes.registrar(
        "demo", "local", r"C:\Proyectos\demo", archivo=archivo, ahora=MOMENTO
    )

    guardadas = json.loads(archivo.read_text(encoding="utf-8"))
    assert guardadas == [
        {
            "nombre": "demo",
            "origen": "local",
            "ruta": r"C:\Proyectos\demo",
            "url": None,
            "ultima_apertura": "2026-10-03T09:30:15+00:00",
        }
    ]


def test_registrar_crea_la_carpeta_y_escribe_utf8(archivo: Path) -> None:
    assert not archivo.parent.exists()

    recientes.registrar("café", "local", "/proyectos/café", archivo=archivo)

    assert "café" in archivo.read_text(encoding="utf-8")
    assert list(archivo.parent.iterdir()) == [archivo]  # sin temporales sueltos


def test_mas_reciente_primero(archivo: Path) -> None:
    recientes.registrar("a", "local", "/p/a", archivo=archivo)
    recientes.registrar(
        "b", "git", "/p/b", url="https://x.org/u/b.git", archivo=archivo
    )

    assert [e["nombre"] for e in recientes.cargar(archivo)] == ["b", "a"]


def test_misma_ruta_con_distinta_mayuscula_no_se_duplica_y_sube(
    archivo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Se fuerza el comportamiento de Windows para que la prueba valga en cualquier SO.
    monkeypatch.setattr(recientes.os.path, "normcase", str.lower)
    recientes.registrar("demo", "local", r"C:\Proyectos\Demo", archivo=archivo)
    recientes.registrar("otro", "local", r"C:\Proyectos\otro", archivo=archivo)

    recientes.registrar(
        "demo", "local", r"c:\proyectos\demo", archivo=archivo, ahora=MOMENTO
    )

    cargadas = recientes.cargar(archivo)
    assert [e["nombre"] for e in cargadas] == ["demo", "otro"]
    assert cargadas[0]["ruta"] == r"c:\proyectos\demo"
    assert cargadas[0]["ultima_apertura"] == "2026-10-03T09:30:15+00:00"


def test_rutas_equivalentes_tras_normalizar_no_se_duplican(archivo: Path) -> None:
    recientes.registrar("demo", "local", "/p/demo", archivo=archivo)
    recientes.registrar("demo", "local", "/p/x/../demo/", archivo=archivo)

    assert len(recientes.cargar(archivo)) == 1


def test_maximo_50_entradas(archivo: Path) -> None:
    for i in range(55):
        recientes.registrar(f"p{i}", "local", f"/p/{i}", archivo=archivo)

    cargadas = recientes.cargar(archivo)
    assert len(cargadas) == recientes.MAXIMO_RECIENTES == 50
    assert cargadas[0]["nombre"] == "p54"
    assert cargadas[-1]["nombre"] == "p5"


def test_cargar_archivo_ausente_devuelve_lista_vacia(archivo: Path) -> None:
    assert recientes.cargar(archivo) == []


@pytest.mark.parametrize("contenido", ["{no es json", "", '{"a": 1}', "42"])
def test_json_danado_no_rompe_y_se_reescribe(archivo: Path, contenido: str) -> None:
    archivo.parent.mkdir(parents=True)
    archivo.write_text(contenido, encoding="utf-8")

    assert recientes.cargar(archivo) == []
    recientes.registrar("demo", "local", "/p/demo", archivo=archivo)

    guardadas = json.loads(archivo.read_text(encoding="utf-8"))
    assert [e["nombre"] for e in guardadas] == ["demo"]


def test_entradas_invalidas_se_descartan(archivo: Path) -> None:
    valida = {
        "nombre": "ok",
        "origen": "local",
        "ruta": "/p/ok",
        "url": None,
        "ultima_apertura": "2026-10-03T09:30:15+00:00",
    }
    archivo.parent.mkdir(parents=True)
    archivo.write_text(
        json.dumps(
            [
                "texto",
                {"nombre": "sin-campos"},
                {**valida, "origen": "ftp"},
                {**valida, "ruta": ""},
                {**valida, "url": 3},
                valida,
            ]
        ),
        encoding="utf-8",
    )

    assert recientes.cargar(archivo) == [valida]


def test_origen_invalido_lanza_error(archivo: Path) -> None:
    with pytest.raises(ValueError, match="Origen no válido"):
        recientes.registrar("demo", "zip", "/p/demo", archivo=archivo)
    assert not archivo.exists()
