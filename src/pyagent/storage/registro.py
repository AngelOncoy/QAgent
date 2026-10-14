"""Escritura de log.json y results.json de una corrida (EN-05).

Ruta: `<proyecto>/.pyagent/runs/<run_id>/`. Ambos archivos se validan contra
`contracts/run_log.schema.json` antes de escribirse y se escriben de forma atómica.
"""

from __future__ import annotations

import ast
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
ARCHIVO_DETALLE = "detalle.json"
#: Mínimo de cobertura si la corrida no trae metas (meta de la carta, ADR-001).
COBERTURA_MINIMA = 60.0
#: Caracteres que se guardan de cada salida de pytest o comentario del Reviewer.
LARGO_MAXIMO_TRAZA = 4000
VERSION = "1"


@dataclass(frozen=True)
class RutasCorrida:
    """Ubicación de los archivos escritos de una corrida."""

    run_id: str
    carpeta: Path
    log: Path
    results: Path
    #: Contrato, último test y traza de cada función, para el Reporte (HU-21).
    detalle: Path | None = None


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
    metas: dict[str, float] | None = None,
    rama: str | None = None,
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
        metas: metas de calidad y tope de gasto de `config.toml` (`[umbrales]` y
            `tope_por_corrida_usd`); se copian a results.json para comparar (HU-18).
        rama: rama Git del proyecto al iniciar la corrida, para el Reporte (HU-21).

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
        run_id, fecha, proyecto, perfil, resultados, tracker, precios, metas
    )
    results["rama"] = rama
    contracts.validar(contracts.RUN_LOG, log)
    contracts.validar(contracts.RUN_LOG, results)
    detalle = construir_detalle(run_id, resultados)

    carpeta = Path(raiz_proyecto) / CARPETA_RUNS / run_id
    carpeta.mkdir(parents=True, exist_ok=True)
    rutas = RutasCorrida(
        run_id,
        carpeta,
        carpeta / "log.json",
        carpeta / "results.json",
        carpeta / ARCHIVO_DETALLE,
    )
    _escribir_json(rutas.log, log)
    _escribir_json(rutas.results, results)
    _escribir_json(rutas.detalle, detalle)
    return rutas


def construir_detalle(
    run_id: str, resultados: Sequence[ResultadoCorrida]
) -> dict[str, Any]:
    """Contenido de detalle.json: lo que el auditor revisa de cada función (HU-21).

    El contrato del Planner, el último test generado y, si no fue aceptado, la traza del
    último intento (salida de pytest o comentario del Reviewer). Las cifras no están
    aquí: siguen en results.json.
    """
    funciones = []
    for resultado in resultados:
        for objetivo in resultado.objetivos:
            ultima = objetivo.revisiones[-1] if objetivo.revisiones else None
            funciones.append(
                {
                    "modulo": resultado.modulo,
                    "funcion": objetivo.objetivo,
                    "contrato": objetivo.contrato,
                    "codigo": objetivo.codigo,
                    "traza": (
                        _recortar(ultima["feedback"])
                        if ultima is not None and objetivo.decision != "accept"
                        else None
                    ),
                    "intentos": [
                        {
                            "intento": r["intento"],
                            "decision": r["decision"],
                            "estado_sandbox": r["estado_sandbox"],
                            "tipo_fallo": r["tipo_fallo"],
                            "laundering_detectado": r["laundering_detectado"],
                        }
                        for r in objetivo.revisiones
                    ],
                }
            )
    return {
        "version": VERSION,
        "tipo": "detalle",
        "run_id": run_id,
        "funciones": funciones,
    }


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
    metas: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Contenido de results.json: las 5 métricas por función y un resumen."""
    objetivos = [
        _objetivo(resultado.modulo, objetivo, tracker, metas)
        for resultado in resultados
        for objetivo in resultado.objetivos
    ]
    return {
        **_cabecera(
            "results", run_id, fecha, proyecto, perfil, resultados, tracker, precios
        ),
        "objetivos": objetivos,
        "resumen": _resumen(objetivos, tracker, metas),
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


def _objetivo(
    modulo: str,
    objetivo: Any,
    tracker: TokenTracker,
    metas: dict[str, float] | None = None,
) -> dict[str, Any]:
    ultima = objetivo.revisiones[-1] if objetivo.revisiones else None
    cobertura = objetivo.cobertura or {}
    return {
        "modulo": modulo,
        "funcion": objetivo.objetivo,
        "tipo": (objetivo.contrato or {}).get("tipo", "funcion"),  # EN-16
        "critical": objetivo.critical,
        "decision": objetivo.decision,
        "motivo_estancado": objetivo.motivo_estancado,  # HU-14
        "reutilizada": objetivo.reutilizada,
        "motivo_regresion": objetivo.motivo_regresion,
        "laundering_detectado": objetivo.laundering_detectado,  # HU-16
        "duracion_s": objetivo.duracion_s,
        "controles": controles(objetivo, metas),  # HU-21
        "metricas": {
            "paso": ultima is not None and ultima["estado_sandbox"] == "ok",
            "cobertura_lineas": cobertura.get("lineas"),
            "cobertura_ramas": cobertura.get("ramas"),
            "iteraciones": objetivo.intentos,
            "tokens_por_agente": tracker.tokens_de_funcion(objetivo.objetivo),
            "mutation_score": None,  # EN-09
        },
    }


def _resumen(
    objetivos: list[dict[str, Any]],
    tracker: TokenTracker,
    metas: dict[str, float] | None = None,
) -> dict[str, Any]:
    total = len(objetivos)
    pasaron = sum(1 for o in objetivos if o["metricas"]["paso"])
    iteraciones = [
        o["metricas"]["iteraciones"] for o in objetivos if o["metricas"]["iteraciones"]
    ]
    resumen: dict[str, Any] = {
        "total_funciones": total,
        "aceptadas": _contar(objetivos, "accept"),
        "bugs_detectados": _contar(objetivos, "bug_detectado"),
        "stalled": _contar(objetivos, "stalled"),
        "sin_veredicto": _contar(objetivos, None),
        "requieren_corrida_nueva": _contar(objetivos, "requiere_corrida_nueva"),
        "pass_rate": round(pasaron / total * 100, 1) if total else 0.0,
        "cobertura_lineas_promedio": _promedio(objetivos, "cobertura_lineas"),
        "cobertura_ramas_promedio": _promedio(objetivos, "cobertura_ramas"),
        "iteraciones_promedio": (
            round(sum(iteraciones) / len(iteraciones), 2) if iteraciones else None
        ),
        "costo_total_usd": round(tracker.total_costo_usd, 8),
        "por_agente": tracker.totales_por_agente(),  # tokens y costo (HU-18)
    }
    if metas is not None:
        resumen["metas"] = dict(metas)
    return resumen


def _promedio(objetivos: list[dict[str, Any]], metrica: str) -> float | None:
    """Promedio de una métrica por función, sin contar las que no la tienen."""
    valores = [
        o["metricas"][metrica] for o in objetivos if o["metricas"][metrica] is not None
    ]
    return round(sum(valores) / len(valores), 1) if valores else None


def controles(objetivo: Any, metas: dict[str, float] | None) -> dict[str, Any]:
    """Los 5 controles del checklist de una función (HU-21).

    Cada uno es True (cumple), False (no cumple) o None (sin dato o no aplica):

    - sintaxis: el último test generado compila (`ast.parse`, sin ejecutarlo).
    - sandbox: el último test se ejecutó en el sandbox sin errores de entorno (ni
      timeout, ni memoria, ni import o colección fallidos).
    - aserciones: el último test no debilitó aserciones (laundering) y cada valor
      esperado es trazable al contrato del Planner.
    - cobertura: líneas y ramas ≥ la meta (si la función no tiene ramas, solo líneas).
    - mutation: Mutation Score ≥ 60 % en funciones críticas; None mientras EN-09 no
      ejecute mutmut o si la función no es crítica.
    """
    ultima = objetivo.revisiones[-1] if objetivo.revisiones else None
    minimo = (metas or {}).get("cobertura_lineas_min", COBERTURA_MINIMA)
    cobertura = objetivo.cobertura or {}
    lineas, ramas = cobertura.get("lineas"), cobertura.get("ramas")
    return {
        "sintaxis": None if objetivo.codigo is None else _compila(objetivo.codigo),
        "sandbox": None
        if ultima is None
        else ultima["estado_sandbox"] in ("ok", "fallo")
        and ultima["tipo_fallo"] != "error_test",
        "aserciones": None
        if ultima is None
        else not ultima["laundering_detectado"]
        and not ultima["feedback"].startswith("Oráculo inválido"),
        "cobertura": None
        if lineas is None
        else lineas >= minimo and (ramas is None or ramas >= minimo),
        "mutation": None,  # EN-09 (Sprint 2): mutmut sobre funciones críticas
    }


def _compila(codigo: str) -> bool:
    try:
        ast.parse(codigo)
    except (SyntaxError, ValueError):
        return False
    return True


def _recortar(texto: str, maximo: int = LARGO_MAXIMO_TRAZA) -> str:
    """El final de la traza: ahí pytest pone el error."""
    return texto if len(texto) <= maximo else "[…]\n" + texto[-maximo:]


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
