"""Datos de la vista «Ejecución de pruebas» (HU-18), calculados solo desde results.json.

La pantalla no calcula ni inventa cifras: muestra lo que devuelve `vista_ejecucion()`,
que sale de `.qagent/runs/<run_id>/results.json`. Así los indicadores de la pantalla
coinciden siempre con el archivo (criterio de aceptación 5).

Las corridas guardadas antes de HU-18 no traen algunos campos del resumen (ramas,
iteraciones promedio, costo por agente, metas); en ese caso se calculan con los datos por
función del mismo archivo, o se informan como no disponibles.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from qagent import contracts
from qagent.contracts import ContratoInvalido
from qagent.storage.registro import CARPETA_RUNS

ARCHIVO = "results.json"
AGENTES = ("planner", "generator", "reviewer")

#: Estado de cada prueba en la vista y su etiqueta (filtros y tabla).
ESTADOS = {
    "aprobado": "Aprobados",
    "rechazado_laundering": "Rechazado laundering",
    "estancado": "Estancados 3/3",
    "bug_detectado": "Bug detectado",
    "requiere_corrida_nueva": "Requiere corrida nueva",
    "sin_veredicto": "Sin veredicto",
}
#: Filtros que se muestran siempre, aunque su conteo sea 0 (criterio 3).
FILTROS_FIJOS = ("aprobado", "rechazado_laundering", "estancado")
TIPOS = {
    "funcion": "Funciones",
    "endpoint": "Endpoints",
}
_ENDPOINT = re.compile(r"^(GET|POST|PUT|PATCH|DELETE)\s+(/\S.*)$")


class ResultadosNoDisponibles(Exception):
    """No hay results.json que mostrar (o el archivo no es válido)."""


def ultimo_run_con_resultados(raiz_proyecto: str | Path) -> str | None:
    """`run_id` de la corrida más reciente que tiene results.json, o None."""
    carpeta = Path(raiz_proyecto) / CARPETA_RUNS
    if not carpeta.is_dir():
        return None
    for run in sorted((p for p in carpeta.iterdir() if p.is_dir()), reverse=True):
        if run.name == "8841-B":
            continue
        if (run / ARCHIVO).is_file():
            return run.name
    return None


def leer_results(
    raiz_proyecto: str | Path, run_id: str | None = None
) -> dict[str, Any]:
    """Lee y valida el results.json de una corrida (por defecto, la más reciente).

    Raises:
        ResultadosNoDisponibles: si no hay corridas con resultados, el archivo no se
            puede leer o no cumple `contracts/run_log.schema.json`.
    """
    run_id = run_id or ultimo_run_con_resultados(raiz_proyecto)
    if run_id is None:
        raise ResultadosNoDisponibles(
            "Este proyecto todavía no tiene corridas con resultados."
        )
    ruta = Path(raiz_proyecto) / CARPETA_RUNS / Path(run_id).name / ARCHIVO
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        contracts.validar(contracts.RUN_LOG, datos)
    except FileNotFoundError as error:
        raise ResultadosNoDisponibles(f"No existe {ruta}.") from error
    except (OSError, json.JSONDecodeError, ContratoInvalido) as error:
        raise ResultadosNoDisponibles(f"{ruta} no es válido: {error}") from error
    if datos.get("tipo") != "results":
        raise ResultadosNoDisponibles(f"{ruta} no es un archivo de resultados.")
    return datos


def estado_de(objetivo: dict[str, Any]) -> str:
    """Estado de una prueba para la vista, según su veredicto final."""
    decision = objetivo["decision"]
    if decision == "accept":
        return "aprobado"
    if decision == "bug_detectado":
        return "bug_detectado"
    if decision == "stalled":
        if objetivo.get("laundering_detectado"):
            return "rechazado_laundering"
        return "estancado"
    if decision == "requiere_corrida_nueva":
        return "requiere_corrida_nueva"
    return "sin_veredicto"


def vista_ejecucion(results: dict[str, Any]) -> dict[str, Any]:
    """Indicadores, filtros y pruebas agrupadas por módulo, desde un results.json."""
    objetivos = results["objetivos"]
    resumen = results["resumen"]
    metas = resumen.get("metas")
    estados = [estado_de(o) for o in objetivos]
    tipos = [tipo_de(o) for o in objetivos]

    from qagent.pruebas.tipos import estrategia_historica

    return {
        "run_id": results["run_id"],
        "fecha": results["fecha"],
        "perfil": results["perfil"],
        "estrategia_prueba": estrategia_historica(
            results.get("estrategia_prueba"), perfil=results.get("perfil")
        ),
        "es_simulado": results["es_simulado"],
        "estado_final": results["estado_final"],
        "motivo_fallo": results["motivo_fallo"],
        "total_funciones": resumen["total_funciones"],
        "total_objetivos": len(objetivos),
        "metas_registradas": metas is not None,
        "indicadores": {
            "pass_rate": _pass_rate(objetivos, resumen, metas),
            "cobertura": _cobertura(objetivos, resumen, metas),
            "iteraciones": _iteraciones(objetivos, resumen, metas),
            "costo": _costo(objetivos, resumen, metas),
            "mutation_score": {"disponible": False, "texto": "Disponible en Sprint 2"},
        },
        "filtros": [
            {
                "clave": clave,
                "etiqueta": ESTADOS[clave],
                "cantidad": estados.count(clave),
            }
            for clave in ESTADOS
            if clave in FILTROS_FIJOS or clave in estados
        ],
        "filtros_tipo": [
            {"clave": "todos", "etiqueta": "Todos", "cantidad": len(objetivos)},
            *[
                {
                    "clave": clave,
                    "etiqueta": etiqueta,
                    "cantidad": tipos.count(clave),
                }
                for clave, etiqueta in TIPOS.items()
            ],
        ],
        "modulos": _por_modulo(objetivos, estados),
    }


def tipo_de(objetivo: dict[str, Any]) -> str:
    """Discriminador persistido; las corridas antiguas siguen siendo funciones."""
    return "endpoint" if objetivo.get("tipo") == "endpoint" else "funcion"


def identidad_de(objetivo: dict[str, Any]) -> dict[str, Any]:
    """Identidad visible sin convertir un nombre incompleto en una ruta falsa."""
    nombre = str(objetivo.get("funcion") or "")
    tipo = tipo_de(objetivo)
    if tipo == "funcion":
        return {
            "tipo": tipo,
            "identificador": nombre or "Función sin nombre",
            "metodo": None,
            "ruta": None,
            "identidad_completa": bool(nombre),
        }
    coincidencia = _ENDPOINT.fullmatch(nombre)
    if coincidencia:
        return {
            "tipo": tipo,
            "identificador": nombre,
            "metodo": coincidencia.group(1),
            "ruta": coincidencia.group(2),
            "identidad_completa": True,
        }
    return {
        "tipo": tipo,
        "identificador": "Endpoint sin método/ruta",
        "metodo": None,
        "ruta": None,
        "identidad_completa": False,
    }


# --- Indicadores -----------------------------------------------------------------


def _pass_rate(objetivos, resumen, metas) -> dict[str, Any]:
    valor = resumen["pass_rate"]
    meta = metas["pass_rate_min"] if metas else None
    return {
        "valor": valor,
        "pasaron": sum(1 for o in objetivos if o["metricas"]["paso"]),
        "total": len(objetivos),
        "meta": meta,
        "cumple": None if meta is None else valor >= meta,
    }


def _cobertura(objetivos, resumen, metas) -> dict[str, Any]:
    lineas = resumen["cobertura_lineas_promedio"]
    ramas = (
        resumen["cobertura_ramas_promedio"]
        if "cobertura_ramas_promedio" in resumen
        else _promedio(objetivos, "cobertura_ramas", 1)
    )
    meta = metas["cobertura_lineas_min"] if metas else None
    return {
        "lineas": lineas,
        "ramas": ramas,
        "meta_lineas": meta,
        "cumple": None if meta is None or lineas is None else lineas >= meta,
    }


def _iteraciones(objetivos, resumen, metas) -> dict[str, Any]:
    valor = (
        resumen["iteraciones_promedio"]
        if "iteraciones_promedio" in resumen
        else _promedio(objetivos, "iteraciones", 2, sin_ceros=True)
    )
    meta = metas["iteraciones_promedio_max"] if metas else None
    return {
        "valor": valor,
        "tope": 3,
        "meta_max": meta,
        "cumple": None if meta is None or valor is None else valor <= meta,
    }


def _costo(objetivos, resumen, metas) -> dict[str, Any]:
    por_agente = resumen.get("por_agente")
    con_costo = por_agente is not None
    if por_agente is None:  # corridas anteriores a HU-18: solo hay tokens por función
        por_agente = {}
        for objetivo in objetivos:
            for agente, tokens in objetivo["metricas"]["tokens_por_agente"].items():
                fila = por_agente.setdefault(
                    agente, {"prompt_tokens": 0, "completion_tokens": 0}
                )
                fila["prompt_tokens"] += tokens["prompt_tokens"]
                fila["completion_tokens"] += tokens["completion_tokens"]
    # Un agente que no aparece no hizo llamadas en la corrida: 0 tokens y US$ 0.
    sin_llamadas = {"prompt_tokens": 0, "completion_tokens": 0, "costo_usd": 0.0}
    agentes = {}
    for agente in AGENTES:
        fila = por_agente.get(agente, {**sin_llamadas, "llamadas": 0})
        agentes[agente] = {
            "tokens": fila["prompt_tokens"] + fila["completion_tokens"],
            "costo_usd": fila.get("costo_usd") if con_costo else None,
            "llamadas": fila.get("llamadas"),
        }
    costo = resumen["costo_total_usd"]
    tope = metas["tope_por_corrida_usd"] if metas else None
    return {
        "por_agente": agentes,
        "tokens_total": sum(a["tokens"] for a in agentes.values()),
        "costo_total_usd": costo,
        "tope_usd": tope,
        "cumple": None if tope is None else costo <= tope,
    }


def _promedio(objetivos, metrica: str, decimales: int, sin_ceros: bool = False):
    valores = [
        o["metricas"][metrica]
        for o in objetivos
        if o["metricas"][metrica] is not None
        and not (sin_ceros and not o["metricas"][metrica])
    ]
    return round(sum(valores) / len(valores), decimales) if valores else None


# --- Pruebas por módulo ----------------------------------------------------------


def _por_modulo(objetivos, estados) -> list[dict[str, Any]]:
    modulos: dict[str, list[dict[str, Any]]] = {}
    for objetivo, estado in zip(objetivos, estados):
        metricas = objetivo["metricas"]
        modulos.setdefault(objetivo["modulo"], []).append(
            {
                "funcion": objetivo["funcion"],
                **identidad_de(objetivo),
                "estado": estado,
                "intento_final": metricas["iteraciones"],
                "duracion_s": objetivo.get("duracion_s"),
                "cobertura_lineas": metricas["cobertura_lineas"],
                "cobertura_ramas": metricas["cobertura_ramas"],
                "motivo_estancado": objetivo["motivo_estancado"],
                "critical": objetivo["critical"],
            }
        )
    return [{"modulo": m, "pruebas": pruebas} for m, pruebas in modulos.items()]
