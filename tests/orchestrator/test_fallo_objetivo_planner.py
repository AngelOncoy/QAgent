"""Pruebas de regresión e integración: fallos de contrato del Planner por objetivo.

Escenario: Proyecto APP-RF, error observado en get_siamese_model (app/utils/siamese_loader.py).
Un error de contrato en un objetivo no debe interrumpir el procesamiento del resto
del proyecto. Los errores recuperables se registran por objetivo sin detener la corrida,
mientras que los errores globales siguen deteniéndola.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from qagent.almacenamiento import AlmacenProyecto
from qagent.almacenamiento.historial import construir_historial
from qagent.app.monitor_eventos import a_fila_monitor
from qagent.config import cargar_configuracion
from qagent.config.carga import RUTA_CONFIG
from qagent.llm import TokenTracker
from qagent.orchestrator import BusEventos, Estado, Orquestador
from qagent.orchestrator.corrida import ejecutar_corrida
from qagent.orchestrator.eventos import Evento
from qagent.orchestrator.orquestador import ERROR_CONTRATO_PLANNER
from qagent.sandbox import ResultadoSandbox
from tests.orchestrator.fakes import (
    GeneratorSimulado,
    PlannerSimulado,
    ReviewerGuionado,
)
from tests.orchestrator.test_orquestador import plan_grabado

E = Estado


def modulo_siamese_loader() -> dict[str, Any]:
    """Simula el módulo app/utils/siamese_loader.py con múltiples funciones."""
    return {
        "ruta": "app/utils/siamese_loader.py",
        "huella": "a" * 64,
        "funciones": [
            {"nombre": "get_siamese_model", "firma": "(device=None)"},
            {"nombre": "limpiar_cache", "firma": "() -> None"},
        ],
    }


def contratos_escenario_app_rf() -> list[dict[str, Any]]:
    """Plan con get_siamese_model inválido y limpiar_cache válido."""
    base = plan_grabado()[0]

    # get_siamese_model produce una respuesta que no cumple planner_contract.v2
    # Por ejemplo: origen es "ejecucion" (prohibido)
    siamese = copy.deepcopy(base)
    siamese["modulo"] = "app/utils/siamese_loader.py"
    siamese["objetivo"] = "get_siamese_model"
    siamese["casos"] = [
        {
            "id": "caso_invalido",
            "entrada": {"device": "cpu"},
            "origen": "ejecucion",  # Origen prohibido en planner_contract.v2
            "valor_esperado": "modelo",
            "categoria": "normal",
        }
    ]

    # limpiar_cache es un contrato perfectamente válido
    cache = copy.deepcopy(base)
    cache["modulo"] = "app/utils/siamese_loader.py"
    cache["objetivo"] = "limpiar_cache"
    cache["casos"] = [
        {
            "id": "limpieza_normal",
            "entrada": {},
            "origen": "tipo",
            "valor_esperado": None,
            "categoria": "normal",
        }
    ]

    return [siamese, cache]


class GeneratorEspia(GeneratorSimulado):
    def __init__(self, tracker: TokenTracker) -> None:
        super().__init__(tracker)
        self.objetivos_generados: list[str] = []

    def generar(self, contrato: dict, intento: int, feedback: str | None) -> dict:
        self.objetivos_generados.append(contrato["objetivo"])
        return super().generar(contrato, intento, feedback)


def test_escenario_app_rf_get_siamese_model_no_detiene_limpiar_cache() -> None:
    """Criterios: error de Planner por objetivo, continuidad de independientes,

    sin pruebas inválidas para ocultar el error, contadores y Monitor.
    """
    tracker = TokenTracker()
    eventos: list[Evento] = []
    bus = BusEventos()
    bus.suscribir(eventos.append)

    plan = contratos_escenario_app_rf()
    generator = GeneratorEspia(tracker)
    reviewer = ReviewerGuionado(tracker, ["accept"])

    orquestador = Orquestador(
        planner=PlannerSimulado(tracker, plan),
        generator=generator,
        reviewer=reviewer,
        bus=bus,
        tracker=tracker,
    )

    resultado = orquestador.ejecutar(modulo_siamese_loader())

    # 1. El estado final es FIN (no FALLO_CONTROLADO)
    assert resultado.estado_final is E.FIN
    assert resultado.motivo_fallo is None

    # 2. Ambos objetivos están presentes en resultado.objetivos
    assert [o.objetivo for o in resultado.objetivos] == [
        "get_siamese_model",
        "limpiar_cache",
    ]

    # 3. get_siamese_model quedó sin veredicto por error de contrato del planner
    siamese = resultado.objetivos[0]
    assert siamese.decision is None
    assert siamese.motivo_sin_veredicto == ERROR_CONTRATO_PLANNER
    assert siamese.codigo is None
    assert siamese.intentos == 0

    # 4. No se generaron pruebas para get_siamese_model
    assert "get_siamese_model" not in generator.objetivos_generados
    assert generator.objetivos_generados == ["limpiar_cache"]

    # 5. limpiar_cache se procesó correctamente y fue aceptada
    cache = resultado.objetivos[1]
    assert cache.decision == "accept"
    assert cache.codigo is not None
    assert cache.intentos == 1

    # 6. El Monitor muestra el objetivo y motivo del error
    eventos_siamese = [
        e for e in eventos if e.funcion == "get_siamese_model" and e.tipo == "veredicto"
    ]
    assert len(eventos_siamese) == 1
    ev = eventos_siamese[0]
    assert ev.datos["motivo"] == ERROR_CONTRATO_PLANNER
    assert ev.datos["decision"] is None
    assert "get_siamese_model" in ev.mensaje

    fila = a_fila_monitor(ev.a_dict())
    assert fila["a"] == "watch"
    assert fila["guard"] == ["Error en contrato del Planner", "SIN VEREDICTO"]
    assert fila["fn"] == "get_siamese_model"


def test_escenario_completo_con_storage_y_corrida(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Prueba de integración de punta a punta con AlmacenProyecto, results.json

    y resumen de la corrida.
    """
    archivo_loader = tmp_path / "app" / "utils" / "siamese_loader.py"
    archivo_loader.parent.mkdir(parents=True, exist_ok=True)
    archivo_loader.write_text(
        "def get_siamese_model(device=None):\n    return 'modelo'\n\n"
        "def limpiar_cache() -> None:\n    return None\n",
        encoding="utf-8",
    )

    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()
    run_id = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
    config = cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config

    def planificar_falso(self, modulo: dict) -> list[dict]:
        plan = contratos_escenario_app_rf()
        for c in plan:
            c["modulo"] = modulo["ruta"]
            c["huella"] = modulo["huella"]
        return plan

    monkeypatch.setattr(
        "qagent.orchestrator.corrida.PlannerAgent.planificar",
        planificar_falso,
    )

    def preparar_imagen_falsa(_ruta: Path, _avanzar=None) -> str:
        return "imagen-falsa"

    def ejecutor_simulado(_imagen, _proyecto, _tests, _modulo) -> ResultadoSandbox:
        return ResultadoSandbox(
            exit_code=0,
            stdout="=== 1 passed ===",
            stderr="",
            duracion_s=0.5,
        )

    resumen = ejecutar_corrida(
        tmp_path,
        "deep",
        config,
        None,
        simulado=True,
        run_id=run_id,
        preparar_imagen=preparar_imagen_falsa,
        ejecutor=ejecutor_simulado,
    )

    # La corrida completa termina en FIN pero con aviso de completada con errores
    assert resumen.estado == "fin"
    assert "completada con errores" in (resumen.motivo or "").lower()

    # Contadores reflejan los objetivos procesados
    assert resumen.total_funciones == 2
    assert resumen.aceptadas == 1
    assert resumen.sin_veredicto == 1
    assert resumen.bugs_detectados == 0
    assert resumen.estancadas == 0

    # Historial conserva los resultados parciales
    historial = construir_historial(tmp_path)
    assert len(historial["corridas"]) == 1
    corrida_historial = historial["corridas"][0]
    assert corrida_historial["total_objetivos"] == 2
    assert corrida_historial["pasaron"] == 1

    # Spec guardada solo contiene el contrato válido (limpiar_cache)
    specs = almacen.listar_specs()
    assert len(specs) == 1
    assert specs[0]["contrato"]["objetivo"] == "limpiar_cache"


def test_diferenciacion_corrida_cancelada(tmp_path: Path) -> None:
    """Verifica que la cancelación por el usuario se diferencie correctamente."""
    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()
    config = cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config

    resumen = ejecutar_corrida(
        tmp_path,
        "deep",
        config,
        None,
        simulado=True,
        cancelado=lambda: True,  # cancelada desde el inicio
    )

    assert resumen.estado == "fallo_controlado"
    assert resumen.cancelada is True
    assert "cancelada por el usuario" in (resumen.motivo or "").lower()


def test_error_global_detiene_la_corrida_cuando_corresponde(tmp_path: Path) -> None:
    """Un error estructural que impide procesar el proyecto sigue deteniendo la corrida."""
    config = cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config

    # Proyecto con carpeta inexistente
    resumen = ejecutar_corrida(
        tmp_path / "carpeta_que_no_existe",
        "deep",
        config,
        None,
        simulado=True,
    )

    assert resumen.estado == "fallo_controlado"
    assert not resumen.cancelada
    assert "no existe" in (resumen.motivo or "").lower()
