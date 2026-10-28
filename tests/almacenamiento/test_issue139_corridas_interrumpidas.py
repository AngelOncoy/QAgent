"""#139: una corrida que quedó «en curso» porque la app se cerró se marca interrumpida.

Evidencia: APP-RF tenía dos run.json en `en_curso` para siempre; al reabrir el proyecto
la app mostraba datos de demostración como si fueran suyos.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from qagent.almacenamiento import AlmacenProyecto, BloqueoCorrida, corrida_activa
from qagent.almacenamiento.bloqueo import ARCHIVO_BLOQUEO
from qagent.almacenamiento.historial import construir_historial
from qagent.almacenamiento.proyecto import MOTIVO_INTERRUMPIDA


@pytest.fixture
def almacen(tmp_path: Path) -> AlmacenProyecto:
    proyecto = AlmacenProyecto(tmp_path / "proyecto")
    proyecto.inicializar()
    return proyecto


def _con_resultados(almacen: AlmacenProyecto, run_id: str) -> None:
    almacen.finalizar_run(run_id, "fin", 1, 0)
    (almacen.carpeta_run(run_id) / "results.json").write_text("{}", encoding="utf-8")


# --- Bloqueo ----------------------------------------------------------------------


def test_sin_archivo_de_bloqueo_nadie_ejecuta_la_corrida(tmp_path: Path) -> None:
    assert corrida_activa(tmp_path) is False


def test_el_bloqueo_se_ve_mientras_dura_y_se_borra_al_liberarlo(tmp_path: Path) -> None:
    bloqueo = BloqueoCorrida.tomar(tmp_path)
    try:
        assert corrida_activa(tmp_path) is True
        with pytest.raises(OSError):
            BloqueoCorrida.tomar(tmp_path)  # nadie más puede tomarlo
    finally:
        bloqueo.liberar()

    assert corrida_activa(tmp_path) is False
    assert not (tmp_path / ARCHIVO_BLOQUEO).exists()


def test_liberar_dos_veces_no_falla(tmp_path: Path) -> None:
    bloqueo = BloqueoCorrida.tomar(tmp_path)
    bloqueo.liberar()
    bloqueo.liberar()


def _python(codigo: str, *args: str, **opciones) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-c", textwrap.dedent(codigo), *args],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        **opciones,
    )


def test_otro_proceso_vivo_mantiene_la_corrida_activa(tmp_path: Path) -> None:
    proceso = _python(
        """
        import sys
        from qagent.almacenamiento import BloqueoCorrida
        bloqueo = BloqueoCorrida.tomar(sys.argv[1])
        print("listo", flush=True)
        sys.stdin.readline()
        """,
        str(tmp_path),
    )
    try:
        assert proceso.stdout.readline().strip() == "listo"
        assert corrida_activa(tmp_path) is True
    finally:
        proceso.communicate("fin\n", timeout=30)


def test_si_el_proceso_se_cae_el_bloqueo_queda_libre(tmp_path: Path) -> None:
    """La app se cerró de golpe: el archivo queda, pero el sistema soltó el bloqueo."""
    proceso = _python(
        """
        import os, sys
        from qagent.almacenamiento import BloqueoCorrida
        BloqueoCorrida.tomar(sys.argv[1])
        os._exit(1)
        """,
        str(tmp_path),
    )
    proceso.communicate(timeout=30)

    assert (tmp_path / ARCHIVO_BLOQUEO).exists()
    assert corrida_activa(tmp_path) is False


# --- Almacén ----------------------------------------------------------------------


def test_una_corrida_en_curso_sin_proceso_se_marca_interrumpida(almacen) -> None:
    huerfana = almacen.crear_run(["funcion"])["run_id"]
    terminada = almacen.crear_run(["funcion"])["run_id"]
    _con_resultados(almacen, terminada)

    marcadas = almacen.cerrar_interrumpidas()

    assert marcadas == [huerfana]
    run = almacen.leer_run(huerfana)  # sigue cumpliendo su validación
    assert run["estado"] == "interrumpida"
    assert run["tipo_terminacion"] == "interrumpida"
    assert run["motivo"] == MOTIVO_INTERRUMPIDA
    assert run["fin"] is not None
    assert almacen.leer_run(terminada)["estado"] == "fin"
    assert almacen.carpeta_run(huerfana).is_dir()  # no se borra nada


def test_una_corrida_bloqueada_no_se_toca(almacen) -> None:
    run_id = almacen.crear_run(["funcion"])["run_id"]

    bloqueo = BloqueoCorrida.tomar(almacen.carpeta_run(run_id))
    try:
        assert almacen.cerrar_interrumpidas() == []
        assert almacen.leer_run(run_id)["estado"] == "en_curso"
    finally:
        bloqueo.liberar()

    assert almacen.cerrar_interrumpidas() == [run_id]


def test_cerrar_interrumpidas_es_idempotente(almacen) -> None:
    almacen.crear_run(["funcion"])

    assert len(almacen.cerrar_interrumpidas()) == 1
    assert almacen.cerrar_interrumpidas() == []


def test_solo_cuentan_las_corridas_con_resultados(almacen) -> None:
    assert almacen.tiene_corridas_con_resultados() is False
    almacen.crear_run(["funcion"])
    almacen.cerrar_interrumpidas()
    assert almacen.tiene_corridas_con_resultados() is False

    _con_resultados(almacen, almacen.crear_run(["funcion"])["run_id"])

    assert almacen.tiene_corridas_con_resultados() is True


def test_el_historial_muestra_la_corrida_como_interrumpida(almacen) -> None:
    almacen.crear_run(["funcion"])
    almacen.cerrar_interrumpidas()

    [fila] = construir_historial(almacen.raiz)["corridas"]

    assert fila["tipo_terminacion"] == "interrumpida"
    assert fila["terminacion_nombre"] == "Interrumpida"
    assert fila["pasaron"] is None
