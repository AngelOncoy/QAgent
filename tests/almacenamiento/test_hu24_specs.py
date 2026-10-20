"""Persistencia y descarga de specs modulares de HU-24."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from io import BytesIO
from zipfile import ZipFile

from qagent import contracts
from qagent.almacenamiento import (
    AlmacenProyecto,
    id_de_modulo,
    nombre_spec_modulo,
)

RUN_1 = "20261011-090000-abcd"
RUN_2 = "20261011-100000-ef01"
HUELLA = "a" * 64
MOMENTO = datetime(2026, 10, 11, 9, 0, tzinfo=timezone.utc)


def contrato() -> dict:
    dato = json.loads(
        (contracts.DIR_CONTRATOS / "ejemplos" / "planner_contract.v2.json").read_text(
            encoding="utf-8"
        )
    )
    dato["huella"] = HUELLA
    return dato


def test_guarda_un_plan_por_modulo_con_huella_y_corrida(tmp_path) -> None:
    almacen = AlmacenProyecto(tmp_path)

    plan = almacen.guardar_plan_modulo(
        "tienda/precios.py", HUELLA, [contrato()], RUN_1, "generado", MOMENTO
    )

    identificador = id_de_modulo("tienda/precios.py")
    assert identificador.startswith("tienda__precios--")
    assert nombre_spec_modulo("tienda/precios.py") == f"{identificador}.spec.json"
    assert (almacen.carpeta_specs / f"{identificador}.spec.json").is_file()
    assert plan["huella"] == HUELLA
    assert plan["run_origen"] == RUN_1
    assert plan["ultima_accion"] == "generado"


def test_modulos_distintos_no_colisionan_en_el_nombre_de_su_spec() -> None:
    assert nombre_spec_modulo("a/b.py") != nombre_spec_modulo("a__b.py")


def test_reutilizar_conserva_la_corrida_de_origen(tmp_path) -> None:
    almacen = AlmacenProyecto(tmp_path)
    almacen.guardar_plan_modulo(
        "tienda/precios.py", HUELLA, [contrato()], RUN_1, "generado", MOMENTO
    )

    reutilizado = almacen.guardar_plan_modulo(
        "tienda/precios.py", HUELLA, [contrato()], RUN_2, "reutilizado"
    )

    assert reutilizado["run_origen"] == RUN_1
    assert reutilizado["ultima_corrida"] == RUN_2
    assert reutilizado["ultima_accion"] == "reutilizado"
    assert almacen.buscar_plan_vigente("tienda/precios.py", HUELLA) == reutilizado
    assert almacen.buscar_plan_vigente("tienda/precios.py", "b" * 64) is None


def test_historial_de_run_registra_el_estado_de_la_spec(tmp_path) -> None:
    almacen = AlmacenProyecto(tmp_path)
    run = almacen.crear_run(ahora=MOMENTO)
    registro = {
        "modulo": "tienda/precios.py",
        "huella": HUELLA,
        "run_origen": run["run_id"],
        "estado": "generado",
    }

    actualizado = almacen.registrar_specs_run(run["run_id"], [registro])

    assert actualizado["specs"] == [registro]
    assert almacen.leer_run(run["run_id"])["specs"] == [registro]


def test_descarga_individual_en_zip(tmp_path) -> None:
    almacen = AlmacenProyecto(tmp_path)
    almacen.guardar_plan_modulo(
        "tienda/precios.py", HUELLA, [contrato()], RUN_1, "generado"
    )

    nombre, contenido = almacen.crear_zip_specs("tienda/precios.py")

    assert nombre == f"{id_de_modulo('tienda/precios.py')}.spec.zip"
    with ZipFile(BytesIO(contenido)) as archivo:
        assert archivo.namelist() == [nombre_spec_modulo("tienda/precios.py")]
        dato = json.loads(archivo.read(archivo.namelist()[0]))
    assert dato["huella"] == HUELLA
    assert dato["run_origen"] == RUN_1
