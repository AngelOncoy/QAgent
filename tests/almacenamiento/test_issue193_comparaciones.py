"""#193: persistencia atómica y trazable de comparaciones entre corridas."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from qagent import contracts
from qagent.almacenamiento import AlmacenProyecto, DatoNoEncontrado, ErrorAlmacen

ORIGEN = "20261029-120000-abcd"
VERIFICACION = "20261029-130000-ef01"


def ejemplo() -> dict:
    ruta = contracts.DIR_CONTRATOS / "ejemplos" / "run_comparison.v1.json"
    return json.loads(ruta.read_text(encoding="utf-8"))


def crear_run(almacen: AlmacenProyecto, run_id: str, resultados: bool = True) -> None:
    almacen.guardar_run(
        {
            "run_id": run_id,
            "inicio": "2026-10-29T12:00:00+00:00",
            "fin": "2026-10-29T12:01:00+00:00",
            "tipos_prueba": ["funcion"],
            "imagen_docker": "qagent-sandbox:base",
            "estado": "fin",
            "resumen": {"pasaron": 1, "fallaron": 0},
        }
    )
    if resultados:
        (almacen.carpeta_run(run_id) / "results.json").write_text(
            '{"original": true}', encoding="utf-8"
        )


@pytest.fixture
def almacen(tmp_path: Path) -> AlmacenProyecto:
    resultado = AlmacenProyecto(tmp_path)
    crear_run(resultado, ORIGEN)
    crear_run(resultado, VERIFICACION)
    return resultado


def test_guarda_recupera_y_lista_comparacion(almacen) -> None:
    dato = ejemplo()

    guardado = almacen.guardar_comparacion(dato)

    assert guardado == dato
    ruta = almacen.carpeta_comparaciones / VERIFICACION / f"{ORIGEN}.json"
    assert ruta.is_file() and ruta.is_relative_to(almacen.carpeta)
    assert almacen.leer_comparacion(ORIGEN, VERIFICACION) == dato
    assert almacen.listar_comparaciones() == [dato]
    assert almacen.listar_comparaciones(ORIGEN) == [dato]
    assert almacen.listar_comparaciones(VERIFICACION) == [dato]


def test_guardado_es_idempotente_e_inmutable(almacen) -> None:
    dato = ejemplo()
    almacen.guardar_comparacion(dato)
    assert almacen.guardar_comparacion(copy.deepcopy(dato)) == dato

    alterado = copy.deepcopy(dato)
    alterado["comparaciones"][0]["estado_posterior"]["observado"] = "otro"
    with pytest.raises(ErrorAlmacen, match="no coincide"):
        almacen.guardar_comparacion(alterado)


def test_no_modifica_resultados_originales(almacen) -> None:
    antes = {
        run_id: (almacen.carpeta_run(run_id) / "results.json").read_bytes()
        for run_id in (ORIGEN, VERIFICACION)
    }

    almacen.guardar_comparacion(ejemplo())

    despues = {
        run_id: (almacen.carpeta_run(run_id) / "results.json").read_bytes()
        for run_id in (ORIGEN, VERIFICACION)
    }
    assert despues == antes


def test_rechaza_corrida_inexistente_o_sin_resultados(tmp_path: Path) -> None:
    almacen = AlmacenProyecto(tmp_path)
    crear_run(almacen, ORIGEN)

    with pytest.raises(DatoNoEncontrado):
        almacen.guardar_comparacion(ejemplo())

    crear_run(almacen, VERIFICACION, resultados=False)
    with pytest.raises(DatoNoEncontrado, match="results.json"):
        almacen.guardar_comparacion(ejemplo())


def test_valida_antes_de_escribir(almacen) -> None:
    dato = ejemplo()
    dato["comparaciones"][0]["resultado"] = "inventado"

    with pytest.raises(contracts.ContratoInvalido):
        almacen.guardar_comparacion(dato)

    assert almacen.listar_comparaciones() == []


def test_error_de_disco_no_deja_archivo_parcial(almacen, monkeypatch) -> None:
    def falla(*_args, **_kwargs):
        raise OSError("disco lleno")

    monkeypatch.setattr("qagent.almacenamiento.proyecto.escribir_json_atomico", falla)

    with pytest.raises(OSError, match="disco lleno"):
        almacen.guardar_comparacion(ejemplo())

    assert almacen.listar_comparaciones() == []
