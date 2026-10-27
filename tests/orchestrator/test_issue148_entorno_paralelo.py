"""Planificar mientras se construye el entorno aislado (#148).

La imagen del sandbox se simula con una función que espera una señal: así se ve que
el Planner trabaja antes de que la imagen esté lista y que el Generator y el Reviewer
esperan. IA simulada, sin Docker.
"""

from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path

import pytest

from qagent.almacenamiento import AlmacenProyecto
from qagent.config import cargar_configuracion
from qagent.config.carga import RUTA_CONFIG
from qagent.orchestrator.corrida import EntornoEnPreparacion, ejecutar_corrida
from tests.orchestrator.test_corrida import BANCO, ejecutor_simulado

ESPERA_MAXIMA_S = 10


@pytest.fixture
def proyecto(tmp_path: Path) -> AlmacenProyecto:
    carpeta = tmp_path / "banco"
    shutil.copytree(
        BANCO, carpeta, ignore=shutil.ignore_patterns("*.md", "*.json", ".qagent")
    )
    almacen = AlmacenProyecto(carpeta)
    almacen.inicializar()
    return almacen


@pytest.fixture
def config():
    return cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config


def correr(almacen, config, preparar_imagen, **opciones):
    eventos: list[dict] = []
    orden: list[str] = []
    al_evento = opciones.pop("al_evento", None)

    def registrar(evento: dict) -> None:
        eventos.append(evento)
        if evento["agente"] in ("planner", "generator", "reviewer"):
            orden.append(evento["agente"])
        if al_evento is not None:
            al_evento(evento)

    run_id = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
    resumen = ejecutar_corrida(
        almacen.raiz,
        "deep",
        config,
        None,
        simulado=True,
        al_evento=registrar,
        run_id=run_id,
        preparar_imagen=preparar_imagen,
        ejecutor=ejecutor_simulado,
        **opciones,
    )
    return resumen, eventos, orden


def test_planifica_antes_de_que_la_imagen_este_lista(proyecto, config) -> None:
    # La imagen solo queda lista cuando el Planner terminó un plan.
    planificado = threading.Event()

    def imagen_lenta(_ruta):
        planificado.wait(ESPERA_MAXIMA_S)
        return "imagen-prueba"

    def al_evento(evento: dict) -> None:
        if str(evento["mensaje"]).startswith("Plan con"):
            planificado.set()

    inicio = time.monotonic()
    resumen, _, orden = correr(proyecto, config, imagen_lenta, al_evento=al_evento)

    assert time.monotonic() - inicio < ESPERA_MAXIMA_S / 2
    assert resumen.estado == "fin", resumen.motivo
    assert planificado.is_set(), "el Planner no trabajó mientras se preparaba la imagen"
    assert orden[: orden.index("generator")].count("planner") >= 1
    assert resumen.aceptadas > 0


def test_el_generator_espera_a_la_imagen(proyecto, config) -> None:
    lista = threading.Event()
    marca: dict[str, float] = {}

    def imagen_lenta(_ruta):
        time.sleep(0.5)
        marca["imagen"] = time.monotonic()
        lista.set()
        return "imagen-prueba"

    primeros: dict[str, float] = {}

    def al_evento(evento: dict) -> None:
        if evento["agente"] in ("generator", "reviewer"):
            primeros.setdefault(evento["agente"], time.monotonic())

    resumen, *_ = correr(proyecto, config, imagen_lenta, al_evento=al_evento)

    assert resumen.estado == "fin", resumen.motivo
    assert primeros["generator"] >= marca["imagen"]
    assert primeros["reviewer"] >= marca["imagen"]


def test_mismo_resultado_que_con_la_imagen_lista(proyecto, config) -> None:
    rapido, *_ = correr(proyecto, config, lambda _ruta: "imagen-prueba")

    def imagen_lenta(_ruta):
        time.sleep(0.3)
        return "imagen-prueba"

    lento, *_ = correr(proyecto, config, imagen_lenta)

    for campo in ("estado", "aceptadas", "bugs_detectados", "total_procesados"):
        assert getattr(lento, campo) == getattr(rapido, campo), campo


def test_mide_el_entorno_y_la_espera(proyecto, config) -> None:
    def imagen_lenta(_ruta):
        time.sleep(0.3)
        return "imagen-prueba"

    resumen, *_ = correr(proyecto, config, imagen_lenta)

    etapas = resumen.duracion_etapas
    assert etapas["entorno"] >= 0.25  # sleep en Windows puede quedarse corto
    assert 0 <= etapas["espera_entorno"] <= etapas["entorno"]


def test_el_error_de_la_imagen_termina_la_corrida_con_su_motivo(
    proyecto, config
) -> None:
    def imagen_rota(_ruta):
        time.sleep(0.1)
        raise RuntimeError("Docker no responde")

    resumen, *_ = correr(proyecto, config, imagen_rota)

    assert resumen.estado == "fallo_controlado"
    assert "Docker no responde" in resumen.motivo


def test_cancelar_mientras_se_espera_la_imagen(proyecto, config) -> None:
    nunca = threading.Event()
    cancelar = threading.Event()

    def imagen_colgada(_ruta):
        nunca.wait(ESPERA_MAXIMA_S)
        return "imagen-prueba"

    def al_evento(evento: dict) -> None:
        if str(evento["mensaje"]).startswith("Plan con"):
            cancelar.set()

    inicio = time.monotonic()
    try:
        resumen, _, orden = correr(
            proyecto,
            config,
            imagen_colgada,
            al_evento=al_evento,
            cancelado=cancelar.is_set,
        )
    finally:
        nunca.set()

    assert time.monotonic() - inicio < ESPERA_MAXIMA_S / 2
    assert resumen.cancelada is True
    assert resumen.tipo_terminacion == "cancelada"
    assert "generator" not in orden


def test_entorno_en_preparacion_relanza_el_error() -> None:
    def falla() -> str:
        raise ValueError("sin red")

    entorno = EntornoEnPreparacion(falla)

    try:
        entorno.esperar()
    except ValueError as error:
        assert "sin red" in str(error)
    else:
        raise AssertionError("se esperaba el error de la preparación")
    assert entorno.listo()
