"""HU-24: reutilización del plan cuando código y docstrings no cambiaron."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from qagent.almacenamiento import AlmacenProyecto
from qagent.almacenamiento.historial import construir_historial
from qagent.config import cargar_configuracion
from qagent.config.carga import RUTA_CONFIG
from qagent.orchestrator.corrida import ejecutar_corrida
from qagent.sandbox import ResultadoSandbox

BANCO = Path(__file__).resolve().parents[2] / "bench" / "banco_mvp.py"
COBERTURA = {
    "totals": {"percent_covered": 100.0, "num_branches": 0, "covered_branches": 0}
}


def ejecutor_exitoso(_imagen, _proyecto, _tests, _modulo) -> ResultadoSandbox:
    return ResultadoSandbox(
        exit_code=0,
        stdout="1 passed",
        stderr="",
        coverage=COBERTURA,
        duracion_s=0.01,
    )


def ejecutor_con_error(_imagen, _proyecto, _tests, _modulo) -> ResultadoSandbox:
    raise RuntimeError("sandbox no disponible")


@pytest.fixture
def config():
    return cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config


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
    )


def llamadas_planner(almacen: AlmacenProyecto, run_id: str) -> list[dict]:
    ruta = almacen.carpeta_run(run_id) / "log.json"
    log = json.loads(ruta.read_text(encoding="utf-8"))
    return [llamada for llamada in log["llamadas"] if llamada["agente"] == "planner"]


def estados_specs(almacen: AlmacenProyecto, run_id: str) -> dict[str, str]:
    run = almacen.leer_run(run_id)
    return {spec["modulo"]: spec["estado"] for spec in run["specs"]}


def test_primera_corrida_genera_y_segunda_reutiliza_sin_planner(
    tmp_path: Path, config
) -> None:
    shutil.copy(BANCO, tmp_path / "banco_mvp.py")
    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()

    primera = correr(almacen, config)
    segunda = correr(almacen, config)

    assert estados_specs(almacen, primera.run_id) == {"banco_mvp.py": "generado"}
    assert len(llamadas_planner(almacen, primera.run_id)) == 1
    assert estados_specs(almacen, segunda.run_id) == {"banco_mvp.py": "reutilizado"}
    assert llamadas_planner(almacen, segunda.run_id) == []
    segundo_log = json.loads(
        (almacen.carpeta_run(segunda.run_id) / "log.json").read_text(encoding="utf-8")
    )
    assert segundo_log["totales_por_agente"].get("planner") is None
    historial = {
        corrida["run_id"]: corrida
        for corrida in construir_historial(tmp_path)["corridas"]
    }
    segunda_en_historial = historial[segunda.run_id]
    primera_en_historial = historial[primera.run_id]
    assert segunda_en_historial["run_id"] == segunda.run_id
    assert segunda_en_historial["tokens_planner"] == 0
    assert segunda_en_historial["resumen_specs"]["reutilizado"] == 1
    assert primera_en_historial["run_id"] == primera.run_id
    assert primera_en_historial["resumen_specs"]["generado"] == 1
    [spec] = almacen.listar_planes_modulo()
    assert spec["run_origen"] == primera.run_id
    assert spec["ultima_corrida"] == segunda.run_id


def test_cambiar_codigo_y_luego_docstring_regenera_la_spec(
    tmp_path: Path, config
) -> None:
    modulo = tmp_path / "banco_mvp.py"
    shutil.copy(BANCO, modulo)
    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()
    primera = correr(almacen, config)
    huella_inicial = almacen.listar_planes_modulo()[0]["huella"]

    modulo.write_text(
        modulo.read_text(encoding="utf-8").replace(
            "return monto_descuento", "return precio - monto_descuento"
        ),
        encoding="utf-8",
    )
    por_codigo = correr(almacen, config)
    huella_codigo = almacen.listar_planes_modulo()[0]["huella"]

    modulo.write_text(
        modulo.read_text(encoding="utf-8").replace(
            "Calcula el precio final", "Obtiene el precio final"
        ),
        encoding="utf-8",
    )
    por_docstring = correr(almacen, config)
    huella_docstring = almacen.listar_planes_modulo()[0]["huella"]

    assert estados_specs(almacen, por_codigo.run_id)["banco_mvp.py"] == "regenerado"
    assert estados_specs(almacen, por_docstring.run_id)["banco_mvp.py"] == "regenerado"
    assert len(llamadas_planner(almacen, por_codigo.run_id)) == 1
    assert len(llamadas_planner(almacen, por_docstring.run_id)) == 1
    assert len({huella_inicial, huella_codigo, huella_docstring}) == 3
    assert primera.run_id != almacen.listar_planes_modulo()[0]["run_origen"]


def test_varios_modulos_solo_regeneran_el_que_cambio(tmp_path: Path, config) -> None:
    uno = tmp_path / "uno"
    dos = tmp_path / "dos"
    uno.mkdir()
    dos.mkdir()
    fuente = BANCO.read_text(encoding="utf-8")
    (uno / "banco_mvp.py").write_text(fuente, encoding="utf-8")
    (dos / "banco_mvp.py").write_text(fuente, encoding="utf-8")
    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()
    correr(almacen, config)

    cambiado = dos / "banco_mvp.py"
    cambiado.write_text(
        fuente.replace("return monto_descuento", "return precio"), encoding="utf-8"
    )
    segunda = correr(almacen, config)

    assert estados_specs(almacen, segunda.run_id) == {
        "uno/banco_mvp.py": "reutilizado",
        "dos/banco_mvp.py": "regenerado",
    }
    assert len(llamadas_planner(almacen, segunda.run_id)) == 1


def test_un_fallo_del_reviewer_no_guarda_un_plan_parcial(
    tmp_path: Path, config
) -> None:
    shutil.copy(BANCO, tmp_path / "banco_mvp.py")
    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()
    run_id = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]

    ejecutar_corrida(
        almacen.raiz,
        "deep",
        config,
        None,
        simulado=True,
        run_id=run_id,
        preparar_imagen=lambda _ruta: "imagen-prueba",
        ejecutor=ejecutor_con_error,
    )

    [plan] = almacen.listar_planes_modulo()
    assert len(plan["contratos"]) == 6
    assert {contrato["objetivo"] for contrato in plan["contratos"]} == {
        "calcular_descuento",
        "clasificar_edad",
        "buscar_elemento_mayor",
        "es_palindromo",
        "invertir_palabras",
        "formatear_moneda",
    }
