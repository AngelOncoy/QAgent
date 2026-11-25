"""Permisos de las carpetas montadas en Linux (#309), sin Docker."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from qagent.sandbox import ejecucion


@pytest.fixture
def chmods(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    """Simula POSIX y registra el modo pedido para cada ruta, sin cambiar nada."""
    pedidos: dict[str, int] = {}
    monkeypatch.setattr(ejecucion.os, "name", "posix")
    monkeypatch.setattr(
        ejecucion.os, "chmod", lambda ruta, modo: pedidos.__setitem__(str(ruta), modo)
    )
    return pedidos


def _arbol(raiz: Path) -> tuple[Path, Path]:
    (raiz / "src/main/java").mkdir(parents=True)
    archivo = raiz / "src/main/java/A.java"
    archivo.write_text("class A {}", encoding="utf-8")
    return raiz / "src", archivo


def test_copia_escribible_por_el_usuario_del_contenedor(tmp_path: Path, chmods) -> None:
    """Maven necesita crear target/ en la copia: carpetas rwx y archivos rw para todos."""
    carpeta, archivo = _arbol(tmp_path / "copia")
    ejecucion.abrir_permisos(tmp_path / "copia", escritura=True)
    assert chmods[str(tmp_path / "copia")] & 0o777 == 0o777
    assert chmods[str(carpeta)] & 0o777 == 0o777
    assert chmods[str(archivo)] & 0o666 == 0o666


def test_tests_solo_legibles(tmp_path: Path, chmods) -> None:
    """Los tests se montan de solo lectura: basta con poder leerlos y recorrerlos."""
    carpeta, archivo = _arbol(tmp_path / "tests")
    original = os.stat(archivo).st_mode
    ejecucion.abrir_permisos(tmp_path / "tests", escritura=False)
    assert chmods[str(carpeta)] & 0o755 == 0o755
    # Solo se añade lectura: el modo pedido es el original más 0o644, sin escritura.
    assert chmods[str(archivo)] == original | 0o644
    assert not (chmods[str(archivo)] & ~original) & stat.S_IWOTH


def test_no_sigue_enlaces(tmp_path: Path, chmods) -> None:
    """Un enlace del proyecto no permite cambiar permisos fuera de la copia."""
    _arbol(tmp_path / "copia")
    fuera = tmp_path / "fuera.txt"
    fuera.write_text("x", encoding="utf-8")
    try:
        os.symlink(fuera, tmp_path / "copia/enlace")
    except OSError:
        pytest.skip("este sistema no permite crear enlaces simbólicos sin privilegios")
    ejecucion.abrir_permisos(tmp_path / "copia", escritura=True)
    assert str(tmp_path / "copia/enlace") not in chmods
    assert str(fuera) not in chmods


def test_fuera_de_posix_no_toca_nada(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(ejecucion.os, "name", "nt")
    llamadas = []
    monkeypatch.setattr(ejecucion.os, "chmod", lambda *a: llamadas.append(a))
    _arbol(tmp_path / "copia")
    ejecucion.abrir_permisos(tmp_path / "copia", escritura=True)
    assert llamadas == []
