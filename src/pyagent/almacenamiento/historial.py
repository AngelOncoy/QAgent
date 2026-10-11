"""Lectura del Historial de corridas y specs modulares (HU-24)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pyagent.almacenamiento.proyecto import AlmacenProyecto, nombre_spec_modulo


def construir_historial(ruta_proyecto: str | Path) -> dict[str, Any]:
    """Construye la vista del Historial usando únicamente datos persistidos."""
    almacen = AlmacenProyecto(ruta_proyecto)
    corridas = [_fila_corrida(almacen, run) for run in reversed(almacen.listar_runs())]
    specs = [_fila_spec(plan) for plan in almacen.listar_planes_modulo()]
    return {"corridas": corridas, "specs": specs}


def _fila_corrida(almacen: AlmacenProyecto, run: dict[str, Any]) -> dict[str, Any]:
    carpeta = almacen.carpeta_run(run["run_id"])
    results = _leer_json_opcional(carpeta / "results.json")
    log = _leer_json_opcional(carpeta / "log.json")
    resumen = results.get("resumen", {})
    modelos = results.get("modelos", {})
    registros = run.get("specs", [])
    return {
        "run_id": run["run_id"],
        "fecha": results.get("fecha", run["inicio"]),
        "perfil": results.get("perfil"),
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
        "pass_rate": resumen.get("pass_rate"),
        "total_tokens": log.get("total_tokens", results.get("total_tokens", 0)),
        "tokens_planner": _tokens_planner(log),
        "costo_usd": log.get("total_costo_usd", results.get("total_costo_usd", 0.0)),
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


def _tokens_planner(log: dict[str, Any]) -> int:
    datos = log.get("totales_por_agente", {}).get("planner", {})
    return int(datos.get("prompt_tokens", 0)) + int(datos.get("completion_tokens", 0))


def _leer_json_opcional(ruta: Path) -> dict[str, Any]:
    try:
        dato = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return dato if isinstance(dato, dict) else {}
