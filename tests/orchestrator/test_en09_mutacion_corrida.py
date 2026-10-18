"""EN-09: la corrida Profundo aplica mutmut solo a las funciones críticas aprobadas.

Sin Docker: el mutador se reemplaza por uno que devuelve resultados conocidos.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from qagent import contracts
from qagent.almacenamiento import AlmacenProyecto
from qagent.config import Mutacion, cargar_configuracion
from qagent.config.carga import RUTA_CONFIG
from qagent.orchestrator.corrida import ejecutar_corrida
from qagent.sandbox import (
    LimitesSandbox,
    MutacionFuncion,
    ResultadoMutacion,
    ResultadoSandbox,
    Sobreviviente,
)

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


class MutadorGrabado:
    """Registra cada llamada y devuelve un resultado fijo por función."""

    def __init__(self, por_funcion: dict[str, MutacionFuncion] | None = None) -> None:
        self.llamadas: list[dict] = []
        self.por_funcion = por_funcion or {}

    def __call__(self, imagen, proyecto, tests, modulo, funciones, limites, **extra):
        self.llamadas.append(
            {
                "imagen": imagen,
                "modulo": modulo,
                "funciones": list(funciones),
                "timeout_s": limites.timeout_s,
                "cpus": limites.cpus,
                "memoria": limites.memoria,
                "pruebas": sorted(p.name for p in Path(tests).iterdir()),
                "inicios": extra.get("inicios"),
            }
        )
        return ResultadoMutacion(
            modulo, {n: self.por_funcion[n] for n in funciones if n in self.por_funcion}
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


def correr(almacen, config, mutador, perfil="deep", criticas=(), al_evento=None):
    run_id = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
    resumen = ejecutar_corrida(
        almacen.raiz,
        perfil,
        config,
        None,
        simulado=True,
        run_id=run_id,
        preparar_imagen=lambda _ruta: "imagen-prueba",
        ejecutor=ejecutor_exitoso,
        seleccion=[
            {
                "ruta": "banco_mvp.py",
                "funciones": TODAS,
                "endpoints": [],
                "criticas": list(criticas),
            }
        ],
        mutador=mutador,
        al_evento=al_evento,
    )
    ruta = almacen.carpeta_run(run_id) / "results.json"
    return resumen, json.loads(ruta.read_text(encoding="utf-8"))


def por_funcion(results: dict) -> dict[str, dict]:
    return {o["funcion"]: o for o in results["objetivos"]}


def test_profundo_muta_solo_las_criticas_aprobadas(almacen, config) -> None:
    mutador = MutadorGrabado(
        {
            "calcular_descuento": MutacionFuncion(
                "calcular_descuento",
                "ok",
                75.0,
                3,
                [Sobreviviente("banco_mvp.x_calcular_descuento__mutmut_2", 9, "a → b")],
            ),
            "clasificar_edad": MutacionFuncion("clasificar_edad", "ok", 40.0, 2),
        }
    )

    _, results = correr(
        almacen, config, mutador, criticas=["calcular_descuento", "clasificar_edad"]
    )

    [llamada] = mutador.llamadas
    assert llamada["modulo"] == "banco_mvp.py"
    assert llamada["imagen"] == "imagen-prueba"
    assert llamada["funciones"] == ["calcular_descuento", "clasificar_edad"]
    assert llamada["timeout_s"] == 120 * 2
    assert len(llamada["pruebas"]) == len(TODAS)  # todas las aprobadas del módulo
    assert set(llamada["inicios"]) == set(TODAS)

    objetivos = por_funcion(results)
    descuento = objetivos["calcular_descuento"]
    assert descuento["metricas"]["mutation_score"] == 75.0
    assert descuento["controles"]["mutation"] is True
    assert descuento["mutacion"]["sobrevivientes"] == [
        {
            "mutante": "banco_mvp.x_calcular_descuento__mutmut_2",
            "linea": 9,
            "cambio": "a → b",
        }
    ]
    edad = objetivos["clasificar_edad"]
    assert edad["metricas"]["mutation_score"] == 40.0
    assert edad["controles"]["mutation"] is False  # bajo la meta de 60 %
    otra = objetivos["es_palindromo"]
    assert otra["metricas"]["mutation_score"] is None
    assert otra["controles"]["mutation"] is None
    assert "mutacion" not in otra
    contracts.validar(contracts.RUN_LOG, results)


@pytest.mark.parametrize(
    "perfil, criticas",
    [("std", ["calcular_descuento"]), ("humo", ["calcular_descuento"]), ("deep", [])],
)
def test_sin_profundo_o_sin_criticas_no_hay_mutacion(
    almacen, config, perfil, criticas
) -> None:
    mutador = MutadorGrabado()

    _, results = correr(almacen, config, mutador, perfil=perfil, criticas=criticas)

    assert mutador.llamadas == []
    assert all(o["metricas"]["mutation_score"] is None for o in results["objetivos"])


def test_un_fallo_de_mutmut_no_detiene_la_corrida(almacen, config) -> None:
    def mutador_roto(*_args, **_kwargs):
        raise RuntimeError("Docker se cayó")

    resumen, results = correr(
        almacen, config, mutador_roto, criticas=["calcular_descuento"]
    )

    assert resumen.estado == "fin"
    descuento = por_funcion(results)["calcular_descuento"]
    assert descuento["decision"] == "accept"
    assert descuento["mutacion"]["estado"] == "error"
    assert "Docker se cayó" in descuento["mutacion"]["mensaje"]
    assert descuento["metricas"]["mutation_score"] is None
    assert descuento["controles"]["mutation"] is None
    contracts.validar(contracts.RUN_LOG, results)


def test_tiempo_agotado_queda_registrado_sin_puntuacion(almacen, config) -> None:
    mutador = MutadorGrabado(
        {
            "calcular_descuento": MutacionFuncion(
                "calcular_descuento", "tiempo_agotado", mensaje="Se agotó el tiempo."
            )
        }
    )

    _, results = correr(almacen, config, mutador, criticas=["calcular_descuento"])

    descuento = por_funcion(results)["calcular_descuento"]
    assert descuento["mutacion"]["estado"] == "tiempo_agotado"
    assert descuento["metricas"]["mutation_score"] is None


def test_el_tiempo_maximo_sale_de_config(almacen, config) -> None:
    mutador = MutadorGrabado()
    corta = replace(config, mutacion=Mutacion(tiempo_maximo_por_funcion_s=30))

    correr(almacen, corta, mutador, criticas=["calcular_descuento", "clasificar_edad"])

    assert mutador.llamadas[0]["timeout_s"] == 60


def test_cpu_y_memoria_de_la_mutacion_salen_de_sandbox(almacen, config) -> None:
    mutador = MutadorGrabado()
    otra = replace(config, sandbox=LimitesSandbox(cpus=2.0, memoria="1g", timeout_s=45))

    correr(almacen, otra, mutador, criticas=["calcular_descuento"])

    [llamada] = mutador.llamadas
    assert (llamada["cpus"], llamada["memoria"]) == (2.0, "1g")
    # El tiempo máximo sigue siendo el de [mutacion], no el de [sandbox].
    assert llamada["timeout_s"] == 120


def test_el_monitor_muestra_el_resultado_de_la_mutacion(almacen, config) -> None:
    eventos: list[dict] = []
    mutador = MutadorGrabado(
        {"calcular_descuento": MutacionFuncion("calcular_descuento", "ok", 75.0, 3)}
    )

    correr(
        almacen,
        config,
        mutador,
        criticas=["calcular_descuento"],
        al_evento=eventos.append,
    )

    mensajes = [e["mensaje"] for e in eventos]
    assert any("Mutation testing (mutmut) sobre 1 función(es)" in m for m in mensajes)
    assert any(
        "calcular_descuento: Mutation Score 75 % (3 de 3 mutantes detectados)" in m
        for m in mensajes
    )
