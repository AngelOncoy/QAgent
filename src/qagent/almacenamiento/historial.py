"""Lectura del Historial de corridas y specs modulares (HU-24)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from qagent.almacenamiento.proyecto import AlmacenProyecto, nombre_spec_modulo
from qagent.storage.registro import nombre_perfil

NOMBRES_TERMINACION = {
    "completada": "Completada",
    "completada_con_errores": "Completada con errores",
    "detenida_error": "Detenida por error",
    "cancelada": "Cancelada",
    "limitada_recursos": "Limitada por recursos",
    # #139: la app se cerró a mitad; se marca al volver a abrir el proyecto.
    "interrumpida": "Interrumpida",
}


def clasificar_terminacion(
    run: dict[str, Any],
    results: dict[str, Any],
    total_pendientes: int = 0,
) -> tuple[str, str]:
    """Clasifica el fin de la corrida para distinguir completas y parciales."""
    tipo = (
        results.get("tipo_terminacion")
        or (results.get("resumen") or {}).get("tipo_terminacion")
        or run.get("tipo_terminacion")
    )
    if tipo in NOMBRES_TERMINACION:
        return tipo, NOMBRES_TERMINACION[tipo]

    motivo = (results.get("motivo_fallo") or run.get("motivo") or "").lower()
    if any(p in motivo for p in ("cancelad", "por el usuario")):
        return "cancelada", NOMBRES_TERMINACION["cancelada"]
    if any(
        p in motivo
        for p in ("token", "presupuesto", "tope de gasto", "tiempo agotado", "límite")
    ):
        return "limitada_recursos", NOMBRES_TERMINACION["limitada_recursos"]

    estado_run = run.get("estado")
    estado_results = results.get("estado_final")

    if estado_run == "en_curso":
        return "detenida_error", NOMBRES_TERMINACION["detenida_error"]
    if estado_results == "fallo_controlado" or estado_run == "fallo_controlado":
        return "detenida_error", NOMBRES_TERMINACION["detenida_error"]

    if total_pendientes > 0:
        return "detenida_error", NOMBRES_TERMINACION["detenida_error"]

    resumen = results.get("resumen") or {}
    sin_veredicto = resumen.get("sin_veredicto", 0)
    stalled = resumen.get("stalled", 0)
    if sin_veredicto > 0 or stalled > 0:
        return "completada_con_errores", NOMBRES_TERMINACION["completada_con_errores"]

    return "completada", NOMBRES_TERMINACION["completada"]


def construir_historial(ruta_proyecto: str | Path) -> dict[str, Any]:
    """Construye la vista del Historial usando únicamente datos persistidos."""
    almacen = AlmacenProyecto(ruta_proyecto)
    corridas = [_fila_corrida(almacen, run) for run in reversed(almacen.listar_runs())]
    specs = [_fila_spec(plan) for plan in almacen.listar_planes_modulo()]
    pruebas = [_fila_prueba(ruta) for ruta in almacen.listar_pruebas_aprobadas()]

    try:
        from qagent.orchestrator.regresion import objetivos_repetibles

        repetibles = len(objetivos_repetibles(ruta_proyecto))
    except Exception:  # noqa: BLE001
        repetibles = len(pruebas)

    total_bugs = sum(c.get("posibles_bugs", 0) or 0 for c in corridas)
    total_contratos_specs = sum(len(s.get("funciones", [])) for s in specs)
    total_pruebas_aprobadas = sum(p.get("pruebas", 0) for p in pruebas)

    resumen_guardadas = {
        "planes_almacenados": len(specs),
        "especificaciones_totales": total_contratos_specs,
        "archivos_prueba": len(pruebas),
        "pruebas_aceptadas": total_pruebas_aprobadas,
        "pruebas_regresion": repetibles,
        "defectos_detectados": total_bugs,
    }

    return {
        "corridas": corridas,
        "specs": specs,
        "pruebas_guardadas": pruebas,
        "resumen_guardadas": resumen_guardadas,
    }


def _fila_corrida(almacen: AlmacenProyecto, run: dict[str, Any]) -> dict[str, Any]:
    carpeta = almacen.carpeta_run(run["run_id"])
    results = _leer_json_opcional(carpeta / "results.json")
    log = _leer_json_opcional(carpeta / "log.json")
    resumen = results.get("resumen", {})
    modelos = results.get("modelos", {})
    registros = run.get("specs", [])
    objetivos = results.get("objetivos") or []
    pass_rate = resumen.get("pass_rate")
    if pass_rate is None and isinstance(run.get("resumen"), dict):
        pasaron = run["resumen"].get("pasaron", 0)
        fallaron = run["resumen"].get("fallaron", 0)
        total = pasaron + fallaron
        if total > 0:
            pass_rate = round(pasaron / total * 100.0, 1)

    total_procesados = (
        results.get("total_procesados")
        or resumen.get("total_procesados")
        or (len(objetivos) if objetivos else None)
        or run.get("procesados")
        or (
            run.get("resumen", {}).get("pasaron", 0)
            + run.get("resumen", {}).get("fallaron", 0)
            if isinstance(run.get("resumen"), dict)
            else 0
        )
    )
    total_seleccionados = (
        results.get("total_seleccionados")
        or resumen.get("total_seleccionados")
        or run.get("total_seleccionados")
        or total_procesados
    )
    total_pendientes = (
        results.get("total_pendientes")
        if results.get("total_pendientes") is not None
        else (
            run.get("pendientes")
            if run.get("pendientes") is not None
            else max(0, total_seleccionados - total_procesados)
        )
    )

    tipo_terminacion, terminacion_nombre = clasificar_terminacion(
        run, results, total_pendientes
    )
    es_parcial = total_pendientes > 0 or tipo_terminacion in (
        "cancelada",
        "limitada_recursos",
    )

    pasaron_val = (
        sum(1 for o in objetivos if (o.get("metricas") or {}).get("paso"))
        if objetivos
        else (
            run.get("resumen", {}).get("pasaron")
            if isinstance(run.get("resumen"), dict)
            else None
        )
    )
    pruebas_aprobadas_val = (
        sum(1 for o in objetivos if o.get("decision") == "accept")
        if objetivos
        else (pasaron_val or 0)
    )
    posibles_bugs_val = (
        sum(1 for o in objetivos if o.get("decision") == "bug_detectado")
        if objetivos
        else 0
    )
    errores_tecnicos_val = (
        sum(
            1
            for o in objetivos
            if o.get("decision") in ("stalled", None)
            or o.get("decision")
            not in ("accept", "bug_detectado", "requiere_corrida_nueva")
        )
        if objetivos
        else max(0, total_procesados - ((pasaron_val or 0) + posibles_bugs_val))
    )
    objetivos_omitidos_val = results.get("objetivos_omitidos") or resumen.get(
        "objetivos_omitidos", 0
    )
    no_procesados_val = total_pendientes
    pruebas_ejecutadas_val = (
        sum((o.get("metricas") or {}).get("iteraciones") or 1 for o in objetivos)
        if objetivos
        else total_procesados
    )

    return {
        "run_id": run["run_id"],
        "fecha": results.get("fecha", run["inicio"]),
        "inicio": results.get("inicio", run.get("inicio")),
        "fin": results.get("fin", run.get("fin")),
        "duracion_s": _duracion(results, run),
        "perfil": results.get("perfil"),
        "perfil_nombre": nombre_perfil(results.get("perfil")),
        "estado": run["estado"],
        "modelos": {
            agente: datos.get("modelo")
            for agente, datos in modelos.items()
            if isinstance(datos, dict)
        },
        "specs": registros,
        "resumen_specs": {
            accion: sum(1 for spec in registros if spec["estado"] == accion)
            for accion in ("generado", "reutilizado", "regenerado")
        },
        "pass_rate": pass_rate,
        "total_tokens": log.get("total_tokens", results.get("total_tokens", 0)),
        "tokens_planner": _tokens_planner(log),
        "costo_usd": log.get("total_costo_usd", results.get("total_costo_usd", 0.0)),
        "requieren_corrida_nueva": resumen.get("requieren_corrida_nueva", 0),
        # Para la tabla y la comparación con la corrida anterior (None si no hay results.json).
        "posibles_bugs": posibles_bugs_val if objetivos else None,
        "pasaron": pasaron_val,
        "total_objetivos": total_procesados
        if (objetivos or run.get("resumen"))
        else None,
        "total_seleccionados": total_seleccionados,
        "total_procesados": total_procesados,
        "total_pendientes": total_pendientes,
        "tipo_terminacion": tipo_terminacion,
        "terminacion_nombre": terminacion_nombre,
        "es_parcial": es_parcial,
        "pruebas_ejecutadas": pruebas_ejecutadas_val,
        "pruebas_aprobadas": pruebas_aprobadas_val,
        "errores_tecnicos": errores_tecnicos_val,
        "objetivos_omitidos": objetivos_omitidos_val,
        "no_procesados_por_detencion": no_procesados_val,
        "cobertura_lineas": resumen.get("cobertura_lineas_promedio"),
        "es_simulado": bool(results.get("es_simulado", False)),
    }


def _duracion(results: dict[str, Any], run: dict[str, Any]) -> float | None:
    """Duración medida de la corrida; None en corridas anteriores a #115.

    No se deriva de las marcas de inicio y fin: una corrida antigua no midió su
    duración y el Historial debe mostrar «—», no un valor inventado.
    """
    resumen = results.get("resumen") or {}
    for valor in (
        results.get("duracion_s"),
        resumen.get("duracion_s"),
        run.get("duracion_s"),
    ):
        if _numero(valor) is not None:
            return _numero(valor)
    return None


def _numero(valor: Any) -> float | None:
    """Número no negativo o None (los datos viejos pueden no tenerlo)."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    return round(max(0.0, float(valor)), 3)


def _fila_spec(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "archivo": nombre_spec_modulo(plan["modulo"]),
        "modulo": plan["modulo"],
        "funciones": [contrato["objetivo"] for contrato in plan["contratos"]],
        "huella": plan["huella"],
        "run_origen": plan["run_origen"],
        "estado": plan["estado"],
        "ultima_accion": plan["ultima_accion"],
        "ultima_corrida": plan["ultima_corrida"],
    }


_PRUEBA = re.compile(r"^\s*(?:async\s+)?def\s+test_", re.MULTILINE)


def _fila_prueba(ruta: Path) -> dict[str, Any]:
    """Archivo de pruebas aprobadas y cuántas pruebas (`def test_*`) contiene."""
    try:
        cantidad = len(_PRUEBA.findall(ruta.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError):
        cantidad = 0
    return {"archivo": ruta.name, "pruebas": cantidad}


def _tokens_planner(log: dict[str, Any]) -> int:
    datos = log.get("totales_por_agente", {}).get("planner", {})
    return int(datos.get("prompt_tokens", 0)) + int(datos.get("completion_tokens", 0))


def _leer_json_opcional(ruta: Path) -> dict[str, Any]:
    try:
        dato = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return dato if isinstance(dato, dict) else {}
