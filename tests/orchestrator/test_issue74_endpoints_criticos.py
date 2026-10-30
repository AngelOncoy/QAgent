"""#74: endpoints prioritarios en la corrida Profundo, con IA simulada y sin Docker.

El mutador se reemplaza por uno que registra lo que se le pide y devuelve resultados
conocidos; el ejecutor de pruebas siempre aprueba.
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
from qagent.sandbox import MutacionFuncion, ResultadoMutacion, Sobreviviente
from tests.orchestrator.test_en09_mutacion_corrida import (
    MutadorGrabado,
    ejecutor_exitoso,
)

BANCO = Path(__file__).resolve().parents[2] / "bench_api" / "api_mvp.py"
ENDPOINTS = [
    "GET /salud",
    "POST /items",
    "GET /items",
    "GET /items/{item_id}",
    "DELETE /items/{item_id}",
    "GET /descuento",
]


class MutadorDeManejadores(MutadorGrabado):
    """Además de lo de EN-09, registra los manejadores pedidos."""

    def __call__(self, imagen, proyecto, tests, modulo, funciones, limites, **extra):
        resultado = super().__call__(
            imagen, proyecto, tests, modulo, funciones, limites, **extra
        )
        self.llamadas[-1]["manejadores"] = list(extra.get("manejadores") or [])
        for manejador in extra.get("manejadores") or []:
            if manejador in self.por_funcion:
                resultado.funciones[manejador] = self.por_funcion[manejador]
        return ResultadoMutacion(modulo, resultado.funciones)


@pytest.fixture
def config():
    return cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config


@pytest.fixture
def almacen(tmp_path: Path) -> AlmacenProyecto:
    shutil.copy(BANCO, tmp_path / "api_mvp.py")
    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()
    return almacen


def correr(almacen, config, mutador, criticas=(), perfil="deep"):
    run_id = almacen.crear_run(tipos_prueba=["endpoint"])["run_id"]
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
                "ruta": "api_mvp.py",
                "funciones": [],
                "endpoints": ENDPOINTS,
                "criticas": list(criticas),
            }
        ],
        mutador=mutador,
    )
    ruta = almacen.carpeta_run(run_id) / "results.json"
    return resumen, json.loads(ruta.read_text(encoding="utf-8"))


def por_objetivo(results: dict) -> dict[str, dict]:
    return {o["funcion"]: o for o in results["objetivos"]}


def contratos_guardados(almacen: AlmacenProyecto) -> dict[str, dict]:
    [plan] = almacen.listar_planes_modulo()
    return {c["objetivo"]: c for c in plan["contratos"]}


def test_los_endpoints_marcados_llegan_criticos_al_contrato_y_se_mutan(
    almacen, config
) -> None:
    mutador = MutadorDeManejadores(
        {
            "borrar_item": MutacionFuncion(
                "borrar_item",
                "ok",
                75.0,
                3,
                [Sobreviviente("api_mvp.x__m_1", 103, "if not → if")],
            )
        }
    )

    _, results = correr(
        almacen, config, mutador, criticas=["DELETE /items/{item_id}", "GET /salud"]
    )

    contratos = contratos_guardados(almacen)
    for contrato in contratos.values():
        contracts.validar(contracts.PLANNER_V3, contrato)
    assert {o for o, c in contratos.items() if c["critical"]} == {
        "DELETE /items/{item_id}",
        "GET /salud",
    }
    objetivos = por_objetivo(results)
    assert {o for o, d in objetivos.items() if d["critical"]} == {
        "DELETE /items/{item_id}",
        "GET /salud",
    }
    # Solo el código de los manejadores marcados, nunca funciones ni el módulo entero.
    [llamada] = mutador.llamadas
    assert llamada["funciones"] == []
    assert llamada["manejadores"] == ["salud", "borrar_item"]
    assert llamada["inicios"]["borrar_item"] == 101
    # Las pruebas de endpoint aprobadas se usan contra los mutantes.
    assert len(llamada["pruebas"]) == len(ENDPOINTS)
    borrar = objetivos["DELETE /items/{item_id}"]
    assert borrar["tipo"] == "endpoint"
    assert borrar["metricas"]["mutation_score"] == 75.0
    assert borrar["mutacion"]["sobrevivientes"][0]["linea"] == 103
    # Sin resultado para un manejador, queda el motivo y no una puntuación inventada.
    assert objetivos["GET /salud"]["metricas"]["mutation_score"] is None
    assert objetivos["GET /salud"]["mutacion"]["estado"] == "error"
    assert objetivos["GET /items"].get("mutacion") is None


def test_sin_criticas_ningun_endpoint_es_critico_ni_se_muta(almacen, config) -> None:
    mutador = MutadorDeManejadores()

    _, results = correr(almacen, config, mutador)

    assert not any(o["critical"] for o in results["objetivos"])
    assert not any(c["critical"] for c in contratos_guardados(almacen).values())
    assert mutador.llamadas == []


def test_sin_profundizar_no_se_muta_aunque_haya_endpoints_marcados(
    almacen, config
) -> None:
    mutador = MutadorDeManejadores()

    _, results = correr(almacen, config, mutador, criticas=["GET /salud"], perfil="std")

    assert por_objetivo(results)["GET /salud"]["critical"] is True
    assert mutador.llamadas == []


def test_la_spec_reutilizada_toma_la_marca_actual_del_endpoint(almacen, config) -> None:
    correr(almacen, config, MutadorDeManejadores(), criticas=["GET /salud"])
    mutador = MutadorDeManejadores()

    resumen, results = correr(almacen, config, mutador, criticas=["GET /descuento"])

    run = almacen.leer_run(resumen.run_id)
    assert {s["modulo"]: s["estado"] for s in run["specs"]} == {
        "api_mvp.py": "reutilizado"
    }
    log = json.loads(
        (almacen.carpeta_run(resumen.run_id) / "log.json").read_text(encoding="utf-8")
    )
    assert [c for c in log["llamadas"] if c["agente"] == "planner"] == []
    criticos = {o: d["critical"] for o, d in por_objetivo(results).items()}
    assert criticos["GET /salud"] is False
    assert criticos["GET /descuento"] is True
    assert contratos_guardados(almacen)["GET /salud"]["critical"] is False
    assert contratos_guardados(almacen)["GET /descuento"]["critical"] is True
    assert mutador.llamadas[0]["manejadores"] == ["descuento"]
