"""Lectura del Historial de corridas y specs modulares (HU-24)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from qagent.almacenamiento.proyecto import AlmacenProyecto, nombre_spec_modulo
from qagent.storage.registro import nombre_perfil


def construir_historial(ruta_proyecto: str | Path) -> dict[str, Any]:
    """Construye la vista del Historial usando únicamente datos persistidos."""
    almacen = AlmacenProyecto(ruta_proyecto)
    corridas = [_fila_corrida(almacen, run) for run in reversed(almacen.listar_runs())]
    specs = [_fila_spec(plan) for plan in almacen.listar_planes_modulo()]
    pruebas = [_fila_prueba(ruta) for ruta in almacen.listar_pruebas_aprobadas()]
    return {"corridas": corridas, "specs": specs, "pruebas_guardadas": pruebas}


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
    return {
        "run_id": run["run_id"],
        "fecha": results.get("fecha", run["inicio"]),
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
        "posibles_bugs": (
            sum(1 for o in objetivos if o.get("decision") == "bug_detectado")
            if objetivos
            else None
        ),
        "pasaron": (
            sum(1 for o in objetivos if (o.get("metricas") or {}).get("paso"))
            if objetivos
            else None
        ),
        "total_objetivos": len(objetivos) if objetivos else None,
        "cobertura_lineas": resumen.get("cobertura_lineas_promedio"),
        "es_simulado": bool(results.get("es_simulado", False)),
    }


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
