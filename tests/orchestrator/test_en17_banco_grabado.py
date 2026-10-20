"""Corrida del banco con salidas de pytest grabadas: el informe detallado de punta a punta.

No usa Docker ni red: la IA es la simulada y el ejecutor repite lo que pytest dijo al
correr los mismos tests (`scripts/grabar_ejecuciones.py`). Si cambia la IA simulada o el
banco, esta prueba pide volver a grabar.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from qagent import contracts
from qagent.almacenamiento import AlmacenProyecto
from qagent.config import cargar_configuracion
from qagent.config.carga import RUTA_CONFIG
from qagent.orchestrator.corrida import ejecutar_corrida
from qagent.storage.exportar_informe import exportar_informe
from tests.orchestrator.ejecutor_grabado import EjecutorGrabado

BANCO = Path(__file__).resolve().parents[2] / "bench"
IMAGEN = "grabacion-local (sin Docker)"


@pytest.fixture(scope="module")
def corrida(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("banco") / "banco"
    shutil.copytree(
        BANCO, carpeta, ignore=shutil.ignore_patterns("*.md", "*.json", ".qagent")
    )
    almacen = AlmacenProyecto(carpeta)
    almacen.inicializar()
    config = cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config
    ejecutor = EjecutorGrabado()
    run_id = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
    resumen = ejecutar_corrida(
        carpeta,
        "deep",
        config,
        None,
        simulado=True,
        run_id=run_id,
        preparar_imagen=lambda ruta: IMAGEN,
        ejecutor=ejecutor,
    )
    detalle = json.loads(
        (almacen.carpeta_run(run_id) / "detalle.json").read_text(encoding="utf-8")
    )
    return {
        "carpeta": carpeta,
        "resumen": resumen,
        "detalle": detalle,
        "ejecutor": ejecutor,
        "run_id": run_id,
    }


def _funcion(corrida, nombre: str) -> dict:
    return next(f for f in corrida["detalle"]["funciones"] if f["funcion"] == nombre)


def test_la_corrida_repite_el_resultado_grabado(corrida) -> None:
    resumen = corrida["resumen"]

    assert resumen.estado == "fin", resumen.motivo
    assert (resumen.aceptadas, resumen.bugs_detectados) == (3, 3)
    assert corrida["ejecutor"].sin_usar == set(), "grabaciones sobrantes: regrabar"


def test_detalle_cumple_su_contrato_y_trae_el_entorno(corrida) -> None:
    detalle = corrida["detalle"]

    assert contracts.es_valido(contracts.DETALLE, detalle)
    entorno = detalle["entorno"]
    assert entorno["imagen"] == IMAGEN
    assert entorno["pytest"].startswith("9.")
    assert entorno["python"]
    assert detalle["totales_casos"]["total"] >= 6
    assert detalle["totales_casos"]["fallaron"] >= 3


def test_el_bug_de_calcular_descuento_dice_donde_y_que(corrida) -> None:
    ultimo = _funcion(corrida, "calcular_descuento")["intentos"][-1]
    caso = next(
        c
        for c in ultimo["ejecucion"]["casos"]
        if c["nombre"] == "test_descuento_normal"
    )

    assert ultimo["decision"] == "bug_detectado"
    assert ultimo["tipo_fallo"] == "bug_codigo"
    assert caso["resultado"] == "fallo"
    assert caso["tipo_error"] == "AssertionError"
    assert (caso["archivo"], caso["linea"]) == ("tests/test_generado.py", 7)
    assert "calcular_descuento(precio=100.0, porcentaje=20.0)" in caso["codigo"]
    assert caso["obtenido"] == "20.0"
    assert caso["esperado"].startswith("80.0")


def test_los_casos_que_pasan_quedan_registrados_junto_a_los_que_fallan(corrida) -> None:
    ultimo = _funcion(corrida, "calcular_descuento")["intentos"][-1]
    resultados = {c["nombre"]: c["resultado"] for c in ultimo["ejecucion"]["casos"]}

    assert resultados["test_descuento_normal"] == "fallo"
    assert resultados["test_precio_negativo"] == "paso"
    assert ultimo["ejecucion"]["totales"]["pasaron"] == 2


def test_una_funcion_correcta_trae_todos_sus_casos_en_verde(corrida) -> None:
    ultimo = _funcion(corrida, "es_palindromo")["intentos"][-1]

    assert ultimo["decision"] == "accept"
    assert ultimo["ejecucion"]["totales"]["fallaron"] == 0
    assert all(c["resultado"] == "paso" for c in ultimo["ejecucion"]["casos"])


def test_las_lineas_sin_cubrir_salen_de_la_cobertura(corrida) -> None:
    ejecucion = _funcion(corrida, "calcular_descuento")["intentos"][-1]["ejecucion"]

    assert isinstance(ejecucion["lineas_sin_cubrir"], list)


def test_lo_grabado_no_trae_datos_de_la_maquina_donde_se_grabo(corrida) -> None:
    texto = json.dumps(corrida["detalle"])
    grabacion = (
        Path(__file__).parent / "grabaciones" / "bench_ejecuciones.json"
    ).read_text(encoding="utf-8")

    for contenido in (texto, grabacion):
        assert "C:\\" not in contenido and "C:/" not in contenido
        assert "Users" not in contenido and "AppData" not in contenido


@pytest.mark.parametrize("formato", ["md", "html", "json", "pdf"])
def test_cada_formato_exporta_el_detalle_del_banco(
    corrida, formato: str, tmp_path
) -> None:
    r = exportar_informe(
        corrida["carpeta"],
        run_id=corrida["run_id"],
        formato=formato,
        carpeta_destino=tmp_path,
    )
    ruta = Path(r["ruta"])

    assert ruta.is_file() and ruta.stat().st_size > 0
    if formato in ("md", "html"):
        texto = ruta.read_text(encoding="utf-8")
        assert "test_descuento_normal" in texto
        assert "tests/test_generado.py:7" in texto
    if formato == "json":
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        assert datos["ejecucion"]["totales_casos"]["fallaron"] >= 3
