"""#168: la corrida produce planner_contract.v3 y generated_test.v2, y sigue usando
las specs v2 guardadas antes (HU-24) sin migrarlas ni borrarlas."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from qagent import contracts
from qagent.almacenamiento import AlmacenProyecto
from qagent.config import cargar_configuracion
from qagent.config.carga import RUTA_CONFIG
from qagent.orchestrator.corrida import ejecutar_corrida
from qagent.sandbox import ResultadoMutacion, ResultadoSandbox

BANCO = Path(__file__).resolve().parents[2] / "bench" / "banco_mvp.py"
COBERTURA = {
    "totals": {"percent_covered": 100.0, "num_branches": 0, "covered_branches": 0}
}


def ejecutor_exitoso(_imagen, _proyecto, _tests, _modulo) -> ResultadoSandbox:
    return ResultadoSandbox(0, "1 passed", "", coverage=COBERTURA, duracion_s=0.01)


def mutador_vacio(_imagen, _proyecto, _tests, modulo, funciones, _limites, **_):
    return ResultadoMutacion(modulo, {})


@pytest.fixture
def config():
    return cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config


@pytest.fixture
def almacen(tmp_path: Path) -> AlmacenProyecto:
    shutil.copy(BANCO, tmp_path / "banco_mvp.py")
    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()
    return almacen


def correr(almacen: AlmacenProyecto, config):
    run_id = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
    return ejecutar_corrida(
        almacen.raiz,
        "deep",
        config,
        None,
        simulado=True,
        run_id=run_id,
        preparar_imagen=lambda _ruta: "imagen-prueba",
        ejecutor=ejecutor_exitoso,
        mutador=mutador_vacio,
    )


def _a_v2(dato: Any) -> Any:
    """Convierte a v2 todos los planner_contract.v3 de Python de un JSON guardado."""
    if isinstance(dato, list):
        return [_a_v2(x) for x in dato]
    if not isinstance(dato, dict):
        return dato
    nuevo = {k: _a_v2(v) for k, v in dato.items()}
    if nuevo.get("version") == "3" and nuevo.get("lenguaje") == "python":
        for clave in ("lenguaje", "framework_pruebas", "framework_app"):
            nuevo.pop(clave, None)
        nuevo["version"] = "2"
    return nuevo


def _resultados(almacen: AlmacenProyecto, run_id: str) -> dict[str, Any]:
    ruta = almacen.carpeta_run(run_id) / "results.json"
    return json.loads(ruta.read_text(encoding="utf-8"))


def test_las_specs_nuevas_se_guardan_como_v3(almacen, config) -> None:
    correr(almacen, config)

    specs = almacen.listar_specs()
    assert specs
    for spec in specs:
        contrato = spec["contrato"]
        assert contrato["version"] == "3"
        assert contrato["lenguaje"] == "python"
        assert contrato["framework_pruebas"] == "pytest"
        contracts.validar(contracts.PLANNER_V3, contrato)


def test_results_registra_el_lenguaje_de_cada_objetivo(almacen, config) -> None:
    resultado = correr(almacen, config)

    objetivos = _resultados(almacen, resultado.run_id)["objetivos"]
    assert objetivos
    assert {o["lenguaje"] for o in objetivos} == {"python"}


def test_las_specs_v2_guardadas_se_reutilizan_sin_migrarlas(almacen, config) -> None:
    correr(almacen, config)
    carpeta = almacen.raiz / ".qagent" / "specs"
    guardados = sorted(carpeta.rglob("*.json"))
    for ruta in guardados:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        ruta.write_text(json.dumps(_a_v2(datos), ensure_ascii=False), encoding="utf-8")
    antes = {s["id"]: s["contrato"] for s in almacen.listar_specs()}
    assert {c["version"] for c in antes.values()} == {"2"}

    segunda = correr(almacen, config)

    run = almacen.leer_run(segunda.run_id)
    assert {spec["estado"] for spec in run["specs"]} == {"reutilizado"}
    # Las specs v2 no se migran ni se borran: mismas specs, mismo contrato v2.
    assert {s["id"]: s["contrato"] for s in almacen.listar_specs()} == antes
    assert all(ruta.is_file() for ruta in guardados)
    # Su lenguaje sale del contrato v2: Python.
    objetivos = _resultados(almacen, segunda.run_id)["objetivos"]
    assert {o["lenguaje"] for o in objetivos} == {"python"}
    assert all(o["decision"] == "accept" for o in objetivos)


def test_generated_test_para_usa_el_lenguaje_del_contrato() -> None:
    contrato_v2 = json.loads(
        (
            Path(contracts.__file__).parent / "ejemplos" / "planner_contract.v2.json"
        ).read_text(encoding="utf-8")
    )

    generado = contracts.generated_test_para(
        contrato_v2, 1, "def test_x():\n    pass\n"
    )

    assert generado["version"] == "2"
    assert generado["lenguaje"] == "python"
    assert generado["framework_pruebas"] == "pytest"
    assert generado["casos_cubiertos"] == [c["id"] for c in contrato_v2["casos"]]
    contracts.validar_versionado(contracts.FAMILIA_GENERATED_TEST, generado)


def test_lenguaje_de_contrato_v2_es_python() -> None:
    assert contracts.lenguaje_de_contrato({"version": "2"}) == "python"
    assert (
        contracts.lenguaje_de_contrato({"version": "3", "lenguaje": "java"}) == "java"
    )
