from __future__ import annotations

from pathlib import Path

import pytest

from qagent.almacenamiento.disco import DatoCorrupto
from qagent.almacenamiento.proyecto import AlmacenProyecto, ErrorAlmacen


def _documento() -> dict:
    return {
        "version": "1",
        "reglas": [
            {
                "id": "capas-001",
                "tipo": "dependencia_prohibida",
                "nombre": "Dominio no importa interfaz",
                "origen": "usuario",
                "confirmada": True,
                "desde": "dominio",
                "hacia": "interfaz",
            }
        ],
    }


def test_proyecto_antiguo_inyecta_universal_sin_escribir(tmp_path: Path) -> None:
    almacen = AlmacenProyecto(tmp_path)
    dato = almacen.leer_reglas_arquitectura()
    assert [r["id"] for r in dato["reglas"]] == ["universal-sin-ciclos"]
    assert not (tmp_path / ".qagent").exists()


def test_guarda_y_lee_atomicamente_sin_tocar_fuentes(tmp_path: Path) -> None:
    fuente = tmp_path / "app.py"
    fuente.write_text("print('original')\n", encoding="utf-8")
    almacen = AlmacenProyecto(tmp_path)
    almacen.guardar_reglas_arquitectura(_documento())
    leido = almacen.leer_reglas_arquitectura()
    assert [r["id"] for r in leido["reglas"]] == [
        "universal-sin-ciclos",
        "capas-001",
    ]
    assert fuente.read_text(encoding="utf-8") == "print('original')\n"
    assert not list((tmp_path / ".qagent").glob("*.tmp"))


def test_reemplazo_conserva_documento_previo_si_falla(
    monkeypatch, tmp_path: Path
) -> None:
    almacen = AlmacenProyecto(tmp_path)
    almacen.guardar_reglas_arquitectura(_documento())
    anterior = almacen.archivo_reglas_arquitectura.read_bytes()

    def falla(*_args, **_kwargs):
        raise OSError("disco lleno")

    monkeypatch.setattr("qagent.almacenamiento.proyecto.escribir_json_atomico", falla)
    nuevo = _documento()
    nuevo["reglas"][0]["nombre"] = "otra"
    with pytest.raises(OSError, match="disco lleno"):
        almacen.guardar_reglas_arquitectura(nuevo)
    assert almacen.archivo_reglas_arquitectura.read_bytes() == anterior


def test_json_corrupto_y_regla_universal_persistida_se_rechazan(tmp_path: Path) -> None:
    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()
    almacen.archivo_reglas_arquitectura.write_text("{", encoding="utf-8")
    with pytest.raises(DatoCorrupto):
        almacen.leer_reglas_arquitectura()
    with pytest.raises(ErrorAlmacen, match="universales"):
        almacen.guardar_reglas_arquitectura(
            {
                "version": "1",
                "reglas": [
                    {
                        "id": "universal-sin-ciclos",
                        "tipo": "ciclos_importacion",
                        "nombre": "sin ciclos",
                        "origen": "universal",
                        "confirmada": True,
                    }
                ],
            }
        )


def test_ruta_es_fija_y_no_admite_path_traversal(tmp_path: Path) -> None:
    almacen = AlmacenProyecto(tmp_path)
    assert (
        almacen.archivo_reglas_arquitectura
        == tmp_path / ".qagent" / "reglas_arquitectura.json"
    )
    assert almacen.archivo_reglas_arquitectura.resolve().is_relative_to(
        tmp_path.resolve()
    )
