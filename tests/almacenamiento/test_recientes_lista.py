"""Pruebas de los proyectos recientes en la Bienvenida (HU-03). Sin Docker ni API."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pyagent.almacenamiento import recientes

MOMENTO = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def archivo(tmp_path: Path) -> Path:
    """Archivo de recientes temporal: nunca se toca el home real."""
    return tmp_path / "home" / ".pyagent" / "recientes.json"


def _abrir_proyectos(tmp_path: Path, archivo: Path, cantidad: int) -> list[str]:
    """Crea carpetas y las registra en orden: la primera queda como la más antigua."""
    rutas = []
    for i in range(cantidad):
        carpeta = tmp_path / f"proyecto{i:02d}"
        carpeta.mkdir()
        recientes.registrar(carpeta.name, "local", str(carpeta), archivo=archivo)
        rutas.append(str(carpeta))
    return rutas


def test_sin_archivo_la_lista_esta_vacia(archivo: Path) -> None:
    assert recientes.listar(archivo) == []


def test_muestra_nombre_origen_ruta_y_ultima_corrida(
    tmp_path: Path, archivo: Path
) -> None:
    carpeta = tmp_path / "repo"
    carpeta.mkdir()
    recientes.registrar(
        "repo", "git", str(carpeta), "https://x.org/u/repo.git", archivo=archivo
    )
    sin_corrida = recientes.listar(archivo)[0]
    assert sin_corrida["ultima_corrida"] is None

    recientes.registrar_corrida(str(carpeta), MOMENTO, archivo=archivo)
    [p] = recientes.listar(archivo)
    assert (p["nombre"], p["origen"], p["ruta"]) == ("repo", "git", str(carpeta))
    assert p["ultima_corrida"] == "2026-10-01T09:00:00+00:00"
    assert p["encontrada"] is True


def test_evidencia_criterio_4_con_11_proyectos_lista_los_10_mas_recientes(
    tmp_path: Path, archivo: Path
) -> None:
    rutas = _abrir_proyectos(tmp_path, archivo, 11)

    lista = recientes.listar(archivo)

    assert [p["ruta"] for p in lista] == rutas[:0:-1]  # del más nuevo al 2.º más viejo
    assert rutas[0] not in [p["ruta"] for p in lista]


def test_evidencia_criterio_4_carpeta_renombrada_se_marca_no_encontrada(
    tmp_path: Path, archivo: Path
) -> None:
    rutas = _abrir_proyectos(tmp_path, archivo, 3)
    Path(rutas[1]).rename(tmp_path / "otro_nombre")

    estado = {p["ruta"]: p["encontrada"] for p in recientes.listar(archivo)}

    assert estado == {rutas[0]: True, rutas[1]: False, rutas[2]: True}


def test_quitar_no_borra_la_carpeta_y_reaparece_el_siguiente(
    tmp_path: Path, archivo: Path
) -> None:
    rutas = _abrir_proyectos(tmp_path, archivo, 11)

    assert recientes.quitar(rutas[5], archivo) is True

    lista = [p["ruta"] for p in recientes.listar(archivo)]
    assert len(lista) == 10 and rutas[5] not in lista and rutas[0] in lista
    assert Path(rutas[5]).is_dir()
    assert recientes.quitar(rutas[5], archivo) is False


def test_quitar_con_otra_mayuscula_en_la_ruta_no_deja_basura(
    archivo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(recientes.os.path, "normcase", str.lower)  # como en Windows
    recientes.registrar("demo", "local", r"C:\Proyectos\Demo", archivo=archivo)

    assert recientes.quitar(r"c:\proyectos\demo", archivo) is True
    assert recientes.cargar(archivo) == []


def test_reabrir_sube_el_proyecto_y_conserva_origen_y_ultima_corrida(
    tmp_path: Path, archivo: Path
) -> None:
    carpeta = tmp_path / "repo"
    carpeta.mkdir()
    recientes.registrar(
        "repo", "git", str(carpeta), "https://x.org/u/repo.git", archivo=archivo
    )
    recientes.registrar_corrida(str(carpeta), MOMENTO, archivo=archivo)
    _abrir_proyectos(tmp_path, archivo, 2)  # ahora "repo" es el más antiguo

    res = recientes.abrir(str(carpeta), archivo)

    assert res["ok"] is True
    primero = recientes.listar(archivo)[0]
    assert primero["ruta"] == str(carpeta)
    assert primero["origen"] == "git"
    assert primero["url"] == "https://x.org/u/repo.git"
    assert primero["ultima_corrida"] == "2026-10-01T09:00:00+00:00"


def test_abrir_una_carpeta_inexistente_falla_y_no_altera_el_orden(
    tmp_path: Path, archivo: Path
) -> None:
    rutas = _abrir_proyectos(tmp_path, archivo, 2)
    Path(rutas[0]).rename(tmp_path / "movida")

    res = recientes.abrir(rutas[0], archivo)

    assert res["ok"] is False and res["motivo"] == "no_encontrada"
    assert recientes.listar(archivo)[0]["ruta"] == rutas[1]


def test_abrir_un_proyecto_que_no_esta_en_la_lista(
    tmp_path: Path, archivo: Path
) -> None:
    res = recientes.abrir(str(tmp_path), archivo)

    assert res["ok"] is False and res["motivo"] == "no_en_lista"
    assert not archivo.exists()


def test_registrar_corrida_de_un_proyecto_desconocido_devuelve_false(
    archivo: Path,
) -> None:
    assert recientes.registrar_corrida("/p/nada", MOMENTO, archivo=archivo) is False
    assert not archivo.exists()


def test_el_formato_de_hu01_no_cambia_si_no_hay_corridas(archivo: Path) -> None:
    recientes.registrar("demo", "local", "/p/demo", archivo=archivo, ahora=MOMENTO)

    [entrada] = json.loads(archivo.read_text(encoding="utf-8"))

    assert "ultima_corrida" not in entrada


def test_ultima_corrida_con_tipo_invalido_se_ignora(archivo: Path) -> None:
    valida = {
        "nombre": "demo",
        "origen": "local",
        "ruta": "/p/demo",
        "url": None,
        "ultima_apertura": "2026-10-03T09:30:15+00:00",
    }
    archivo.parent.mkdir(parents=True)
    archivo.write_text(json.dumps([{**valida, "ultima_corrida": 5}]), encoding="utf-8")

    assert recientes.listar(archivo)[0]["ultima_corrida"] is None
