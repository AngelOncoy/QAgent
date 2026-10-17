"""#70: caché del Mutation Score por función en `.qagent/mutacion/`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qagent.almacenamiento import AlmacenProyecto, ErrorAlmacen, huella_de_prueba

SPEC = "banco_mvp_py__es_palindromo"
RUN = "20261017-101500-abcd"
HUELLA = "a" * 64
MUTACION = {
    "estado": "ok",
    "puntuacion": 71.4,
    "detectados": 5,
    "sobrevivientes": [{"mutante": "m", "linea": 93, "cambio": "a → b"}],
    "mensaje": None,
}


@pytest.fixture
def almacen(tmp_path: Path) -> AlmacenProyecto:
    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()
    return almacen


def test_huella_de_prueba_ignora_saltos_de_linea_de_windows() -> None:
    assert huella_de_prueba("a\r\nb\n") == huella_de_prueba("a\nb\n")
    assert huella_de_prueba("a") != huella_de_prueba("b")


def test_guarda_y_reutiliza_si_funcion_y_prueba_no_cambiaron(almacen) -> None:
    prueba = huella_de_prueba("def test_x(): pass\n")

    almacen.guardar_mutacion(SPEC, HUELLA, prueba, MUTACION, RUN)

    guardado = almacen.mutacion_vigente(SPEC, HUELLA, prueba)
    assert guardado["mutacion"] == MUTACION
    assert guardado["run_id"] == RUN
    archivo = almacen.carpeta_mutacion / f"{SPEC}.json"
    assert json.loads(archivo.read_text(encoding="utf-8"))["huella_prueba"] == prueba


@pytest.mark.parametrize(
    "huella_objetivo, codigo",
    [("b" * 64, "def test_x(): pass\n"), ("a" * 64, "def test_y(): pass\n")],
)
def test_si_cambia_la_funcion_o_la_prueba_no_se_reutiliza(
    almacen, huella_objetivo, codigo
) -> None:
    almacen.guardar_mutacion(
        SPEC, HUELLA, huella_de_prueba("def test_x(): pass\n"), MUTACION, RUN
    )

    assert (
        almacen.mutacion_vigente(SPEC, huella_objetivo, huella_de_prueba(codigo))
        is None
    )


def test_sin_registro_o_sin_huellas_no_hay_mutacion_vigente(almacen) -> None:
    assert almacen.mutacion_vigente(SPEC, HUELLA, "c" * 64) is None
    assert almacen.mutacion_vigente(SPEC, None, "c" * 64) is None
    assert almacen.mutacion_vigente(SPEC, HUELLA, None) is None


def test_un_registro_danado_se_ignora(almacen) -> None:
    almacen.carpeta_mutacion.mkdir(parents=True)
    (almacen.carpeta_mutacion / f"{SPEC}.json").write_text("{roto", encoding="utf-8")

    assert almacen.mutacion_vigente(SPEC, HUELLA, "c" * 64) is None


@pytest.mark.parametrize(
    "mutacion",
    [
        {**MUTACION, "estado": "tiempo_agotado", "puntuacion": None},
        {**MUTACION, "estado": "error"},
        {**MUTACION, "puntuacion": None},
    ],
)
def test_solo_se_guardan_mutaciones_con_puntuacion(almacen, mutacion) -> None:
    with pytest.raises(ErrorAlmacen):
        almacen.guardar_mutacion(SPEC, HUELLA, "c" * 64, mutacion, RUN)
    assert not (almacen.carpeta_mutacion / f"{SPEC}.json").exists()


@pytest.mark.parametrize(
    "spec, huella, prueba, run",
    [
        ("../fuera", HUELLA, "c" * 64, RUN),
        (SPEC, "corta", "c" * 64, RUN),
        (SPEC, HUELLA, "C" * 64, RUN),
        (SPEC, HUELLA, "c" * 64, "ayer"),
    ],
)
def test_rechaza_campos_invalidos(almacen, spec, huella, prueba, run) -> None:
    with pytest.raises(ErrorAlmacen):
        almacen.guardar_mutacion(spec, huella, prueba, MUTACION, run)
