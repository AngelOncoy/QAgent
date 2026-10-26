"""Lo seleccionado que no se probó se registra como omitido, no como pendiente.

Caso real (APP-RF): se eligieron 4 objetivos; el Planner omitió una función sin
docstring y un endpoint con la ruta sin resolver. Resultados mostró 2 y dijo «Todo
pasó», mientras results.json quedaba como `detenida_error` con 2 «pendientes».
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from qagent.contracts import RUN_LOG, ContratoInvalido, validar
from qagent.llm import FakeLLMClient, TokenTracker, cargar_precios
from qagent.orchestrator import BusEventos, Estado, Orquestador
from qagent.orchestrator.corrida import ResumenCorrida, _contar, tipo_terminacion
from qagent.orchestrator.orquestador import (
    MOTIVO_RUTA_SIN_RESOLVER,
    MOTIVO_SIN_CONTRATO,
)
from qagent.storage import escribir_corrida
from qagent.storage.vista_ejecucion import (
    corrida_incompleta,
    respuesta_principal,
    vista_ejecucion,
)
from tests.orchestrator.fakes import (
    GeneratorSimulado,
    PlannerSimulado,
    ReviewerGuionado,
)

RAIZ = Path(__file__).resolve().parents[2]
FRONTEND = RAIZ / "src" / "qagent" / "frontend"

MODULO = {
    "ruta": "modulo_simulado.py",
    "huella": "0" * 64,
    "funciones": [
        {"nombre": "duplicar", "firma": "(x: int) -> int"},
        {"nombre": "sin_docstring", "firma": "(a, b)"},
    ],
    "endpoints": [
        {"objetivo": "GET /health", "manejador": "health", "resuelta": False},
    ],
}

MOTIVO_PLANNER = (
    "la función no tiene docstring y no se pudo deducir un resultado esperado "
    "verificable a partir de la firma, los tipos ni el docstring"
)


def plan_grabado() -> list[dict]:
    return json.loads(FakeLLMClient().generar("plan", rol="planner").contenido)


def armar(plan, omitidas=None):
    tracker = TokenTracker()
    planner = PlannerSimulado(tracker, plan)
    planner.omitidas = omitidas or {}
    orquestador = Orquestador(
        planner,
        GeneratorSimulado(tracker),
        ReviewerGuionado(tracker, ["accept"]),
        bus=BusEventos(),
        tracker=tracker,
    )
    return orquestador, tracker


# --- Orquestador ------------------------------------------------------------------


def test_el_modulo_registra_lo_que_no_entro_al_plan_con_su_motivo() -> None:
    orquestador, _ = armar(plan_grabado(), {"sin_docstring": MOTIVO_PLANNER})

    resultado = orquestador.ejecutar(MODULO)

    assert resultado.estado_final is Estado.FIN
    assert [o.objetivo for o in resultado.objetivos] == ["duplicar"]
    assert resultado.omitidos == [
        {
            "objetivo": "sin_docstring",
            "tipo": "funcion",
            "motivo": MOTIVO_PLANNER[0].upper() + MOTIVO_PLANNER[1:] + ".",
        },
        {
            "objetivo": "GET /health",
            "tipo": "endpoint",
            "motivo": MOTIVO_RUTA_SIN_RESOLVER,
        },
    ]


def test_sin_motivo_del_planner_queda_un_motivo_generico() -> None:
    orquestador, _ = armar(plan_grabado())

    resultado = orquestador.ejecutar(MODULO)

    [funcion] = [o for o in resultado.omitidos if o["tipo"] == "funcion"]
    assert funcion == {
        "objetivo": "sin_docstring",
        "tipo": "funcion",
        "motivo": MOTIVO_SIN_CONTRATO,
    }


def test_si_el_planner_falla_nada_cuenta_como_omitido() -> None:
    """Un fallo técnico del Planner deja los objetivos pendientes, no omitidos."""
    orquestador, _ = armar("no es una lista", {"sin_docstring": MOTIVO_PLANNER})

    resultado = orquestador.ejecutar(MODULO)

    assert resultado.estado_final is Estado.FALLO_CONTROLADO
    assert resultado.omitidos == []


# --- Conteo y terminación de la corrida -------------------------------------------


def _resumen(**cambios) -> ResumenCorrida:
    datos = {"run_id": None, "estado": "fin", "motivo": None, "total_funciones": 0}
    return ResumenCorrida(**{**datos, **cambios})


def _resultado(decisiones: list[str], omitidos: int) -> SimpleNamespace:
    return SimpleNamespace(
        objetivos=[SimpleNamespace(decision=d) for d in decisiones],
        omitidos=[{"objetivo": f"o{i}"} for i in range(omitidos)],
        duracion_etapas={},
    )


def test_las_omitidas_se_cuentan_aparte_de_las_pendientes() -> None:
    resumen = _resumen(total_seleccionados=4)

    _contar(resumen, [_resultado(["accept", "accept"], 2)], TokenTracker())

    assert resumen.total_procesados == 2
    assert resumen.objetivos_omitidos == 2
    assert resumen.total_pendientes == 0
    assert tipo_terminacion(resumen) == "completada"


def test_lo_que_una_detencion_dejo_sin_revisar_sigue_siendo_pendiente() -> None:
    resumen = _resumen(total_seleccionados=6)

    _contar(resumen, [_resultado(["accept"], 1)], TokenTracker())

    assert resumen.objetivos_omitidos == 1
    assert resumen.total_pendientes == 4
    assert tipo_terminacion(resumen) == "detenida_error"


@pytest.mark.parametrize(
    ("cambios", "esperado"),
    [
        ({"cancelada": True}, "cancelada"),
        ({"motivo": "Corrida detenida por el usuario."}, "cancelada"),
        ({"motivo": "Se alcanzó el presupuesto de tokens"}, "limitada_recursos"),
        ({"estado": "fallo_controlado"}, "detenida_error"),
        ({"estancadas": 1}, "completada_con_errores"),
        ({"sin_veredicto": 1}, "completada_con_errores"),
        ({"total_pendientes": 2}, "detenida_error"),
        ({"objetivos_omitidos": 3}, "completada"),
        ({}, "completada"),
    ],
)
def test_tipo_terminacion(cambios: dict, esperado: str) -> None:
    assert tipo_terminacion(_resumen(**cambios)) == esperado


# --- results.json y la vista de Resultados ----------------------------------------


def _escribir(tmp_path: Path, con_omitidos: bool = True) -> tuple[dict, list[dict]]:
    """Corre el módulo y escribe su results.json; devuelve (results, omitidos)."""
    orquestador, tracker = armar(plan_grabado(), {"sin_docstring": MOTIVO_PLANNER})
    resultado = orquestador.ejecutar(MODULO)
    omitidos = [{"modulo": resultado.modulo, **o} for o in resultado.omitidos]
    rutas = escribir_corrida(
        tmp_path,
        resultado,
        tracker,
        cargar_precios(),
        perfil="std",
        total_seleccionados=3,
        total_procesados=1,
        total_pendientes=0,
        tipo_terminacion="completada",
        objetivos_omitidos=len(omitidos) if con_omitidos else None,
        omitidos=omitidos if con_omitidos else None,
    )
    return json.loads(rutas.results.read_text(encoding="utf-8")), omitidos


def test_results_json_guarda_las_omitidas_y_cumple_el_schema(tmp_path: Path) -> None:
    results, omitidos = _escribir(tmp_path)

    validar(RUN_LOG, results)
    assert results["omitidos"] == omitidos
    assert results["objetivos_omitidos"] == 2
    assert results["total_pendientes"] == 0
    assert results["tipo_terminacion"] == "completada"


def test_el_schema_rechaza_una_omitida_mal_formada(tmp_path: Path) -> None:
    orquestador, tracker = armar(plan_grabado())
    resultado = orquestador.ejecutar(MODULO)

    with pytest.raises(ContratoInvalido):
        escribir_corrida(
            tmp_path,
            resultado,
            tracker,
            cargar_precios(),
            perfil="std",
            omitidos=[{"modulo": "m.py", "objetivo": "f", "tipo": "clase"}],
        )


def test_la_vista_entrega_las_omitidas_con_su_identidad(tmp_path: Path) -> None:
    results, _ = _escribir(tmp_path)

    vista = vista_ejecucion(results)

    assert vista["total_omitidos"] == 2
    funcion, endpoint = vista["omitidos"]
    assert funcion["identificador"] == "sin_docstring"
    assert funcion["modulo"] == "modulo_simulado.py"
    assert endpoint["identificador"] == "GET /health"
    assert endpoint["metodo"] == "GET" and endpoint["ruta"] == "/health"
    assert endpoint["motivo"] == MOTIVO_RUTA_SIN_RESOLVER
    assert vista["total_pendientes"] == 0
    assert vista["es_parcial"] is False


def test_una_corrida_anterior_sin_omitidas_sigue_funcionando(tmp_path: Path) -> None:
    results, _ = _escribir(tmp_path, con_omitidos=False)

    vista = vista_ejecucion(results)

    assert "omitidos" not in results
    assert vista["omitidos"] == []
    assert vista["total_omitidos"] == 0


# --- Interfaz ---------------------------------------------------------------------


def _js(ruta: str) -> str:
    return (FRONTEND / ruta).read_text(encoding="utf-8")


def _cuerpo(js: str, inicio: str, fin: str) -> str:
    return js[js.index(inicio) : js.index(fin, js.index(inicio))]


def test_resultados_muestra_las_omitidas_en_su_bandeja() -> None:
    js = _js("componentes/ejecucion/ejecucion.js")

    assert "{k:'omitida',  t:'No se probaron'" in js
    assert "return [...elementosProbados(v), ...elementosOmitidos(v)];" in js
    omitidos = _cuerpo(js, "function elementosOmitidos", "function elementosProbados")
    assert "(v.omitidos || [])" in omitidos
    assert "bandeja: 'omitida'" in omitidos
    assert "explicacion: o.motivo" in omitidos


def test_todo_paso_solo_si_se_probo_todo_lo_seleccionado() -> None:
    js = _js("componentes/ejecucion/ejecucion.js")
    estado = _cuerpo(js, "function estadoGeneral", "function renderCabeceraBandeja")
    cabecera = _cuerpo(
        js, "function renderCabeceraBandeja", "function renderFiltrosBandeja"
    )

    # Cada salida que no es «Todo pasó» se revisa antes que él.
    todo_paso = estado.index("corto:'Todo pasó'")
    for condicion in (
        "if (bugs.length)",
        "if (!probados)",
        "if (sinPrueba)",
        "if (omitidas)",
        "if (incompleta)",
    ):
        assert estado.index(condicion) < todo_paso
    assert "v.es_parcial" in estado and "'detenida_error'" in estado
    assert "$('bnjTitulo').textContent = estadoGeneral(todos, v).texto;" in cabecera
    assert "${omitidas} sin probar" in cabecera


def test_exportar_usa_el_mismo_criterio_que_resultados() -> None:
    js = _js("componentes/exportar/exportar.js")

    assert "const estado = estadoGeneral(todos, v);" in js
    assert "Todo pasó" not in js


@pytest.mark.parametrize(
    ("datos", "esperado"),
    [
        (
            {"bugs": 2, "primer_bug": "calcular", "total": 5},
            "2 posibles bugs. Empieza por calcular.",
        ),
        (
            {"total": 0, "incompleta": True},
            "La corrida se detuvo antes de probar algo.",
        ),
        ({"total": 0, "omitidos": 2}, "No se probó nada: 2 objetivos no se probaron."),
        ({"total": 0}, "No se probó ninguna función ni endpoint."),
        (
            {"total": 3, "sin_prueba": 1},
            "Sin posibles bugs, pero faltan pruebas por revisar.",
        ),
        (
            {"total": 2, "omitidos": 1},
            "Sin posibles bugs en lo probado, pero 1 objetivo no se probó.",
        ),
        (
            {"total": 2, "incompleta": True},
            "Sin posibles bugs en lo probado, pero la corrida no terminó.",
        ),
        ({"total": 1}, "Todo pasó: 1 función o endpoint verificado."),
        ({"total": 6}, "Todo pasó: 6 funciones y endpoints verificados."),
    ],
)
def test_respuesta_principal_de_los_informes(datos: dict, esperado: str) -> None:
    base = {
        "bugs": 0,
        "primer_bug": None,
        "sin_prueba": 0,
        "omitidos": 0,
        "incompleta": False,
    }

    assert respuesta_principal(**{**base, **datos}) == esperado


@pytest.mark.parametrize(
    ("datos", "esperado"),
    [
        ({"es_parcial": True}, True),
        ({"tipo_terminacion": "detenida_error"}, True),
        ({"tipo_terminacion": "cancelada"}, True),
        ({"tipo_terminacion": "limitada_recursos"}, True),
        ({"tipo_terminacion": "completada_con_errores"}, False),
        ({"tipo_terminacion": "completada", "es_parcial": False}, False),
    ],
)
def test_corrida_incompleta(datos: dict, esperado: bool) -> None:
    assert corrida_incompleta(datos) is esperado


def test_los_informes_usan_el_criterio_comun() -> None:
    storage = RAIZ / "src" / "qagent" / "storage"
    for archivo in ("exportar_informe.py", "informe_pdf.py"):
        codigo = (storage / archivo).read_text(encoding="utf-8")
        assert "respuesta_principal(" in codigo
        assert 'f"Todo pasó:' not in codigo
    exportar = (storage / "exportar_informe.py").read_text(encoding="utf-8")
    assert '"omitidos": copy.deepcopy(results.get("omitidos") or [])' in exportar


def test_el_monitor_cuenta_las_omitidas_al_terminar() -> None:
    js = _js("componentes/monitor/monitor.js")
    fin = _cuerpo(js, "function monitorFinReal", "\n}\n")

    assert "const omitidos = Number(r.objetivos_omitidos || 0);" in fin
    assert "conAvisos: ok && omitidos > 0" in fin
    assert "PRG.total = Number(r.total_seleccionados)" in fin
    assert "PRG.fin.conAvisos ? 'Corrida completada con avisos'" in js
    assert "(PRG.hechos + omitidos) / PRG.total" in js
