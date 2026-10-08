"""Escritura de log.json y results.json de una corrida (EN-05).

Ruta: `<proyecto>/.pyagent/runs/<run_id>/`. Ambos archivos se validan contra
`contracts/run_log.schema.json` antes de escribirse y se escriben de forma atómica.
"""

from __future__ import annotations

import json
import os
import secrets
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pyagent import contracts
from pyagent.llm.precios import PrecioAgente
from pyagent.llm.tracker import TokenTracker

if (
    TYPE_CHECKING
):  # solo para type hints: storage no depende del orquestador en ejecución
    from pyagent.orchestrator import ResultadoCorrida

CARPETA_RUNS = Path(".pyagent") / "runs"
VERSION = "1"


@dataclass(frozen=True)
class RutasCorrida:
    """Ubicación de los archivos escritos de una corrida."""

    run_id: str
    carpeta: Path
    log: Path
    results: Path


def nuevo_run_id(ahora: datetime | None = None) -> str:
    """Identificador único y ordenable: `AAAAMMDD-HHMMSS-xxxx`."""
    ahora = ahora or datetime.now().astimezone()
    return f"{ahora:%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


def escribir_corrida(
    raiz_proyecto: str | Path,
    resultados: ResultadoCorrida | Sequence[ResultadoCorrida],
    tracker: TokenTracker,
    precios: dict[str, PrecioAgente],
    perfil: str,
    run_id: str | None = None,
    fecha: str | None = None,
) -> RutasCorrida:
    """Genera, valida y escribe log.json y results.json de una corrida.

    Args:
        raiz_proyecto: carpeta del proyecto analizado (donde vive `.pyagent/`).
        resultados: un `ResultadoCorrida` por módulo procesado.
        tracker: registro de llamadas compartido con los agentes.
        precios: modelos y precios por agente (`cargar_precios()`).
        perfil: perfil de la corrida (ej. "deep").
        run_id: identificador; si es None se genera uno nuevo.
        fecha: inicio de la corrida en ISO 8601; si es None, ahora.

    Returns:
        Rutas de la carpeta y de los dos archivos.

    Raises:
        ContratoInvalido: si algún archivo no cumple el schema (no se escribe nada).
    """
    if not isinstance(resultados, Sequence):
        resultados = [resultados]
    run_id = run_id or nuevo_run_id()
    fecha = fecha or datetime.now().astimezone().isoformat(timespec="seconds")
    proyecto = str(Path(raiz_proyecto).resolve())

    log = construir_log(run_id, fecha, proyecto, perfil, resultados, tracker, precios)
    results = construir_results(
        run_id, fecha, proyecto, perfil, resultados, tracker, precios
    )
    contracts.validar(contracts.RUN_LOG, log)
    contracts.validar(contracts.RUN_LOG, results)

    carpeta = Path(raiz_proyecto) / CARPETA_RUNS / run_id
    carpeta.mkdir(parents=True, exist_ok=True)
    rutas = RutasCorrida(
        run_id, carpeta, carpeta / "log.json", carpeta / "results.json"
    )
    _escribir_json(rutas.log, log)
    _escribir_json(rutas.results, results)
    return rutas


def construir_log(
    run_id: str,
    fecha: str,
    proyecto: str,
    perfil: str,
    resultados: Sequence[ResultadoCorrida],
    tracker: TokenTracker,
    precios: dict[str, PrecioAgente],
) -> dict[str, Any]:
    """Contenido de log.json: cada llamada a la IA con sus tokens y costo."""
    return {
        **_cabecera(
            "log", run_id, fecha, proyecto, perfil, resultados, tracker, precios
        ),
        "llamadas": [ll.a_log() for ll in tracker.llamadas],
        "totales_por_agente": tracker.totales_por_agente(),
        "total_tokens": tracker.total_tokens,
        "total_costo_usd": round(tracker.total_costo_usd, 8),
    }


def construir_results(
    run_id: str,
    fecha: str,
    proyecto: str,
    perfil: str,
    resultados: Sequence[ResultadoCorrida],
    tracker: TokenTracker,
    precios: dict[str, PrecioAgente],
) -> dict[str, Any]:
    """Contenido de results.json: las 5 métricas por función y un resumen."""
    objetivos = [
        _objetivo(resultado.modulo, objetivo, tracker)
        for resultado in resultados
        for objetivo in resultado.objetivos
    ]
    return {
        **_cabecera(
            "results", run_id, fecha, proyecto, perfil, resultados, tracker, precios
        ),
        "objetivos": objetivos,
        "resumen": _resumen(objetivos, tracker),
    }


# --- Partes de los archivos -------------------------------------------------------


def _cabecera(
    tipo: str,
    run_id: str,
    fecha: str,
    proyecto: str,
    perfil: str,
    resultados: Sequence[ResultadoCorrida],
    tracker: TokenTracker,
    precios: dict[str, PrecioAgente],
) -> dict[str, Any]:
    fallos = [r for r in resultados if r.estado_final.value == "fallo_controlado"]
    return {
        "version": VERSION,
        "tipo": tipo,
        "run_id": run_id,
        "fecha": fecha,
        "proyecto": proyecto,
        "perfil": perfil,
        "modelos": {agente: _modelo(precio) for agente, precio in precios.items()},
        "estado_final": "fallo_controlado" if fallos else "fin",
        "motivo_fallo": f"{fallos[0].modulo}: {fallos[0].motivo_fallo}"
        if fallos
        else None,
        "es_simulado": all(ll.es_simulado for ll in tracker.llamadas),
    }


def _modelo(precio: PrecioAgente) -> dict[str, Any]:
    return {
        "proveedor": precio.proveedor,
        "modelo": precio.modelo,
        "precio_entrada_usd_m": precio.entrada_usd_m,
        "precio_salida_usd_m": precio.salida_usd_m,
    }


def _objetivo(modulo: str, objetivo: Any, tracker: TokenTracker) -> dict[str, Any]:
    ultima = objetivo.revisiones[-1] if objetivo.revisiones else None
    cobertura = objetivo.cobertura or {}
    return {
        "modulo": modulo,
        "funcion": objetivo.objetivo,
        "critical": objetivo.critical,
        "decision": objetivo.decision,
        "motivo_estancado": objetivo.motivo_estancado,  # HU-14
        "metricas": {
            "paso": ultima is not None and ultima["estado_sandbox"] == "ok",
            "cobertura_lineas": cobertura.get("lineas"),
            "cobertura_ramas": cobertura.get("ramas"),
            "iteraciones": objetivo.intentos,
            "tokens_por_agente": tracker.tokens_de_funcion(objetivo.objetivo),
            "mutation_score": None,  # EN-09
        },
    }


def _resumen(objetivos: list[dict[str, Any]], tracker: TokenTracker) -> dict[str, Any]:
    total = len(objetivos)
    coberturas = [
        o["metricas"]["cobertura_lineas"]
        for o in objetivos
        if o["metricas"]["cobertura_lineas"] is not None
    ]
    pasaron = sum(1 for o in objetivos if o["metricas"]["paso"])
    return {
        "total_funciones": total,
        "aceptadas": _contar(objetivos, "accept"),
        "bugs_detectados": _contar(objetivos, "bug_detectado"),
        "stalled": _contar(objetivos, "stalled"),
        "sin_veredicto": _contar(objetivos, None),
        "pass_rate": round(pasaron / total * 100, 1) if total else 0.0,
        "cobertura_lineas_promedio": (
            round(sum(coberturas) / len(coberturas), 1) if coberturas else None
        ),
        "costo_total_usd": round(tracker.total_costo_usd, 8),
    }


def _contar(objetivos: Iterable[dict[str, Any]], decision: str | None) -> int:
    return sum(1 for o in objetivos if o["decision"] == decision)


def _escribir_json(ruta: Path, datos: dict[str, Any]) -> None:
    """Escribe en un temporal de la misma carpeta y lo renombra (escritura atómica)."""
    descriptor, temporal = tempfile.mkstemp(
        prefix=f".{ruta.name}.", suffix=".tmp", dir=ruta.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as archivo:
            json.dump(datos, archivo, indent=2, ensure_ascii=False)
        os.replace(temporal, ruta)
    except BaseException:
        Path(temporal).unlink(missing_ok=True)
        raise
