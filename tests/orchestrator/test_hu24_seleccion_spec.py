"""HU-24: una spec reutilizada respeta los objetivos elegidos en la Vista previa."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from qagent.almacenamiento import AlmacenProyecto
from qagent.config import cargar_configuracion
from qagent.config.carga import RUTA_CONFIG
from qagent.orchestrator.corrida import ejecutar_corrida
from qagent.sandbox import ResultadoSandbox

BANCO = Path(__file__).resolve().parents[2] / "bench" / "banco_mvp.py"
TODAS = [
    "calcular_descuento",
    "clasificar_edad",
    "buscar_elemento_mayor",
    "es_palindromo",
    "invertir_palabras",
    "formatear_moneda",
]


def ejecutor_exitoso(_imagen, _proyecto, _tests, _modulo) -> ResultadoSandbox:
    return ResultadoSandbox(
        exit_code=0,
        stdout="1 passed",
        stderr="",
        coverage={
            "totals": {
                "percent_covered": 100.0,
                "num_branches": 0,
                "covered_branches": 0,
            }
        },
        duracion_s=0.01,
    )


@pytest.fixture
def config():
    return cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config


@pytest.fixture
def almacen(tmp_path: Path) -> AlmacenProyecto:
    shutil.copy(BANCO, tmp_path / "banco_mvp.py")
    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()
    return almacen


def correr(almacen: AlmacenProyecto, config, funciones: list[str]):
    run_id = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
    return ejecutar_corrida(
        almacen.raiz,
        "std",
        config,
        None,
        simulado=True,
        run_id=run_id,
        preparar_imagen=lambda _ruta: "imagen-prueba",
        ejecutor=ejecutor_exitoso,
        seleccion=[{"ruta": "banco_mvp.py", "funciones": funciones, "endpoints": []}],
    )


def probadas(almacen: AlmacenProyecto, run_id: str) -> list[str]:
    ruta = almacen.carpeta_run(run_id) / "results.json"
    results = json.loads(ruta.read_text(encoding="utf-8"))
    return [objetivo["funcion"] for objetivo in results["objetivos"]]


def llamadas_planner(almacen: AlmacenProyecto, run_id: str) -> int:
    ruta = almacen.carpeta_run(run_id) / "log.json"
    log = json.loads(ruta.read_text(encoding="utf-8"))
    return sum(1 for llamada in log["llamadas"] if llamada["agente"] == "planner")


def estado_spec(almacen: AlmacenProyecto, run_id: str) -> str:
    [spec] = almacen.leer_run(run_id)["specs"]
    return spec["estado"]


def objetivos_guardados(almacen: AlmacenProyecto) -> set[str]:
    [plan] = almacen.listar_planes_modulo()
    return {contrato["objetivo"] for contrato in plan["contratos"]}


def test_reutilizar_solo_prueba_los_objetivos_elegidos(almacen, config) -> None:
    correr(almacen, config, TODAS)

    segunda = correr(almacen, config, ["es_palindromo"])

    assert estado_spec(almacen, segunda.run_id) == "reutilizado"
    assert llamadas_planner(almacen, segunda.run_id) == 0
    assert probadas(almacen, segunda.run_id) == ["es_palindromo"]


def test_la_spec_guardada_conserva_los_objetivos_no_elegidos(almacen, config) -> None:
    correr(almacen, config, TODAS)
    correr(almacen, config, ["es_palindromo"])

    tercera = correr(almacen, config, TODAS)

    assert objetivos_guardados(almacen) == set(TODAS)
    assert estado_spec(almacen, tercera.run_id) == "reutilizado"
    assert llamadas_planner(almacen, tercera.run_id) == 0
    assert sorted(probadas(almacen, tercera.run_id)) == sorted(TODAS)


def test_si_la_spec_no_tiene_un_objetivo_elegido_se_vuelve_a_planificar(
    almacen, config
) -> None:
    correr(almacen, config, ["es_palindromo"])
    assert objetivos_guardados(almacen) == {"es_palindromo"}

    segunda = correr(almacen, config, ["es_palindromo", "clasificar_edad"])

    assert estado_spec(almacen, segunda.run_id) == "regenerado"
    assert llamadas_planner(almacen, segunda.run_id) == 1
    assert sorted(probadas(almacen, segunda.run_id)) == [
        "clasificar_edad",
        "es_palindromo",
    ]
    assert objetivos_guardados(almacen) == {"es_palindromo", "clasificar_edad"}


def test_al_volver_a_planificar_se_conservan_los_objetivos_no_elegidos(
    almacen, config
) -> None:
    correr(almacen, config, ["es_palindromo", "formatear_moneda"])

    correr(almacen, config, ["es_palindromo", "clasificar_edad"])

    assert objetivos_guardados(almacen) == {
        "es_palindromo",
        "formatear_moneda",
        "clasificar_edad",
    }
