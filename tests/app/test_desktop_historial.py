"""Puente de escritorio para Historial y descarga ZIP de HU-24."""

from __future__ import annotations

import json
from zipfile import ZipFile

import pytest

pytest.importorskip("webview")

from qagent import contracts
from qagent.almacenamiento import AlmacenProyecto
from qagent.app.desktop import DesktopAPI


class VentanaFalsa:
    """Diálogo de guardado controlado para no abrir una ventana en la prueba."""

    def __init__(self, destino) -> None:
        self.destino = destino
        self.nombre_propuesto = None

    def create_file_dialog(self, _tipo, **opciones):
        self.nombre_propuesto = opciones["save_filename"]
        return [str(self.destino)]


def test_historial_consulta_spec_y_la_descarga_como_zip(tmp_path) -> None:
    contrato = json.loads(
        (contracts.DIR_CONTRATOS / "ejemplos" / "planner_contract.v2.json").read_text(
            encoding="utf-8"
        )
    )
    almacen = AlmacenProyecto(tmp_path)
    run = almacen.crear_run()
    plan = almacen.guardar_plan_modulo(
        contrato["modulo"],
        contrato["huella"],
        [contrato],
        run["run_id"],
        "generado",
    )
    almacen.registrar_specs_run(
        run["run_id"],
        [
            {
                "modulo": plan["modulo"],
                "huella": plan["huella"],
                "run_origen": plan["run_origen"],
                "estado": "generado",
            }
        ],
    )
    almacen.finalizar_run(run["run_id"], "fin", 1, 0)
    api = DesktopAPI()
    destino = tmp_path / "descarga.zip"
    ventana = VentanaFalsa(destino)
    api.set_window(ventana)

    historial = api.obtener_historial(str(tmp_path))
    descarga = api.descargar_specs_zip(str(tmp_path), contrato["modulo"])

    assert historial["ok"] is True
    assert historial["corridas"][0]["specs"][0]["huella"] == contrato["huella"]
    assert historial["specs"][0]["run_origen"] == run["run_id"]
    assert descarga["ok"] is True
    assert descarga["ruta"] == str(destino)
    assert ventana.nombre_propuesto.endswith(".spec.zip")
    with ZipFile(destino) as archivo:
        assert archivo.namelist() == [historial["specs"][0]["archivo"]]


def test_historial_lista_pruebas_guardadas_y_las_descarga_como_zip(tmp_path) -> None:
    almacen = AlmacenProyecto(tmp_path)
    almacen.guardar_prueba_aprobada(
        "test_total.py", "def test_uno():\n    pass\n\n\ndef test_dos():\n    pass\n"
    )
    almacen.guardar_prueba_aprobada("test_tax.py", "async def test_tres():\n    pass\n")
    api = DesktopAPI()
    destino = tmp_path / "pruebas.zip"
    ventana = VentanaFalsa(destino)
    api.set_window(ventana)

    historial = api.obtener_historial(str(tmp_path))
    descarga = api.descargar_pruebas_zip(str(tmp_path))

    assert historial["pruebas_guardadas"] == [
        {"archivo": "test_tax.py", "pruebas": 1},
        {"archivo": "test_total.py", "pruebas": 2},
    ]
    assert descarga["ok"] is True
    assert ventana.nombre_propuesto == f"pruebas_{tmp_path.name}.zip"
    with ZipFile(destino) as archivo:
        assert archivo.namelist() == ["test_tax.py", "test_total.py"]


def test_descargar_pruebas_sin_pruebas_guardadas_explica_el_motivo(tmp_path) -> None:
    api = DesktopAPI()
    api.set_window(VentanaFalsa(tmp_path / "nada.zip"))

    resultado = api.descargar_pruebas_zip(str(tmp_path))

    assert resultado["ok"] is False
    assert "no tiene pruebas guardadas" in resultado["motivo"]
