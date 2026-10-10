"""Corrida completa sobre el banco: análisis → agentes → registro en .pyagent/ (EN-04).

Usa la IA simulada y un ejecutor que reemplaza a Docker: no ejecuta ningún código, solo
responde como lo haría pytest según la función que prueba el test generado.
"""

from __future__ import annotations

import dataclasses
import json
import shutil
from pathlib import Path

import pytest

from pyagent.almacenamiento import AlmacenProyecto
from pyagent.config import cargar_configuracion
from pyagent.config.carga import RUTA_CONFIG
from pyagent.orchestrator.corrida import ejecutar_corrida
from pyagent.sandbox import ResultadoSandbox

BANCO = Path(__file__).resolve().parents[2] / "bench"
CON_BUG = ("calcular_descuento", "clasificar_edad", "buscar_elemento_mayor")
COBERTURA = {
    "totals": {"percent_covered": 50.0, "num_branches": 4, "covered_branches": 2}
}


def ejecutor_simulado(
    imagen, ruta_proyecto, ruta_tests, modulo_cov
) -> ResultadoSandbox:
    codigo = (ruta_tests / "test_generado.py").read_text(encoding="utf-8")
    if any(f"import {nombre}" in codigo for nombre in CON_BUG):
        salida = "E       assert 20.0 == 80.0\nFAILED test_generado.py::test_x - assert 20.0 == 80.0"
        return ResultadoSandbox(
            exit_code=1, stdout=salida, stderr="", coverage=COBERTURA, duracion_s=0.1
        )
    return ResultadoSandbox(
        exit_code=0, stdout="1 passed", stderr="", coverage=COBERTURA, duracion_s=0.1
    )


@pytest.fixture
def proyecto(tmp_path: Path) -> AlmacenProyecto:
    carpeta = tmp_path / "banco"
    shutil.copytree(BANCO, carpeta, ignore=shutil.ignore_patterns("*.md", "*.json"))
    almacen = AlmacenProyecto(carpeta)
    almacen.inicializar()
    return almacen


@pytest.fixture
def config():
    return cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config


def correr(almacen, config, **opciones):
    eventos: list[dict] = []
    run_id = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
    resumen = ejecutar_corrida(
        almacen.raiz,
        "deep",
        config,
        None,
        simulado=True,
        al_evento=eventos.append,
        run_id=run_id,
        preparar_imagen=lambda ruta: "imagen-prueba",
        ejecutor=ejecutor_simulado,
        **opciones,
    )
    return resumen, eventos


def test_corrida_completa_del_banco(proyecto, config) -> None:
    resumen, eventos = correr(proyecto, config)

    assert resumen.estado == "fin", resumen.motivo
    assert resumen.total_funciones == 6
    assert (resumen.aceptadas, resumen.bugs_detectados, resumen.estancadas) == (3, 3, 0)
    assert resumen.tokens == 0
    # El Monitor recibe el progreso de cada veredicto.
    veredictos = [e for e in eventos if e["tipo"] == "veredicto"]
    assert [e["progreso"]["hechos"] for e in veredictos] == [1, 2, 3, 4, 5, 6]
    assert all(e["progreso"]["total"] == 6 for e in eventos)
    assert eventos[-1]["tipo"] == "fin"


def test_deja_el_registro_completo_en_pyagent(proyecto, config) -> None:
    resumen, _ = correr(proyecto, config)

    carpeta = proyecto.carpeta_run(resumen.run_id)
    assert resumen.carpeta == str(carpeta)
    results = json.loads((carpeta / "results.json").read_text(encoding="utf-8"))
    assert results["resumen"]["aceptadas"] == 3
    assert results["resumen"]["bugs_detectados"] == 3
    assert (carpeta / "log.json").is_file()

    run = proyecto.leer_run(resumen.run_id)
    assert run["estado"] == "fin"
    assert run["resumen"] == {"pasaron": 3, "fallaron": 3}

    assert len(proyecto.listar_specs()) == 6
    aprobadas = sorted(p.name for p in proyecto.listar_pruebas_aprobadas())
    assert aprobadas == [
        "test_banco_mvp_py__es_palindromo.py",
        "test_banco_mvp_py__formatear_moneda.py",
        "test_banco_mvp_py__invertir_palabras.py",
    ]


def test_corta_al_alcanzar_el_tope_de_gasto(proyecto, config) -> None:
    sin_presupuesto = dataclasses.replace(
        config,
        presupuesto=dataclasses.replace(config.presupuesto, tope_por_corrida_usd=0.0),
    )

    resumen, eventos = correr(proyecto, sin_presupuesto)

    assert resumen.estado == "fallo_controlado"
    assert "tope de gasto" in resumen.motivo
    assert resumen.aceptadas == 0
    assert proyecto.leer_run(resumen.run_id)["estado"] == "fallo_controlado"
    assert any(e["tipo"] == "fallo" for e in eventos)


def test_carpeta_inexistente_termina_sin_lanzar(tmp_path, config) -> None:
    resumen = ejecutar_corrida(
        tmp_path / "no-existe", "deep", config, None, simulado=True
    )

    assert resumen.estado == "fallo_controlado"
    assert "no existe" in resumen.motivo


def test_proyecto_sin_funciones(tmp_path, config) -> None:
    (tmp_path / "vacio.py").write_text("X = 1\n", encoding="utf-8")

    resumen = ejecutar_corrida(tmp_path, "deep", config, None, simulado=True)

    assert resumen.estado == "fallo_controlado"
    assert "funciones públicas" in resumen.motivo


def test_un_error_al_preparar_docker_no_tumba_la_app(proyecto, config) -> None:
    def sin_imagen(ruta):
        raise RuntimeError("Docker no responde")

    run_id = proyecto.crear_run()["run_id"]
    resumen = ejecutar_corrida(
        proyecto.raiz,
        "deep",
        config,
        None,
        simulado=True,
        run_id=run_id,
        preparar_imagen=sin_imagen,
    )

    assert resumen.estado == "fallo_controlado"
    assert "Docker no responde" in resumen.motivo
    assert proyecto.leer_run(run_id)["estado"] == "fallo_controlado"
