"""Persistencia por proyecto de la selección de Explorar."""

from __future__ import annotations

import json
from pathlib import Path

from qagent.proyectos.preferencias import (
    cargar_seleccion_objetivos,
    guardar_seleccion_objetivos,
)


def _seleccion(incluida: bool = False) -> dict:
    return {
        "version": 1,
        "modulos": [
            {
                "ruta": "app.py",
                "incluido": True,
                "funciones": [
                    {"nombre": "saludar", "incluido": incluida, "critico": False}
                ],
                "endpoints": [
                    {
                        "objetivo": "GET /salud",
                        "incluido": True,
                        "critico": True,
                    }
                ],
            }
        ],
    }


def test_guarda_y_recupera_seleccion_parcial_y_vacia(tmp_path: Path) -> None:
    guardar_seleccion_objetivos(tmp_path, _seleccion(False))

    assert cargar_seleccion_objetivos(tmp_path) == _seleccion(False)
    assert (tmp_path / ".qagent" / "seleccion_objetivos.json").is_file()


def test_dos_proyectos_conservan_preferencias_independientes(tmp_path: Path) -> None:
    primero, segundo = tmp_path / "uno", tmp_path / "dos"
    primero.mkdir()
    segundo.mkdir()
    guardar_seleccion_objetivos(primero, _seleccion(False))
    guardar_seleccion_objetivos(segundo, _seleccion(True))

    assert cargar_seleccion_objetivos(primero) != cargar_seleccion_objetivos(segundo)


def test_archivo_corrupto_o_version_desconocida_se_ignora(tmp_path: Path) -> None:
    carpeta = tmp_path / ".qagent"
    carpeta.mkdir()
    archivo = carpeta / "seleccion_objetivos.json"
    archivo.write_text("{roto", encoding="utf-8")
    assert cargar_seleccion_objetivos(tmp_path) is None

    archivo.write_text(json.dumps({"version": 99, "modulos": []}), encoding="utf-8")
    assert cargar_seleccion_objetivos(tmp_path) is None
