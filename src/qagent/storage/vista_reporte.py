"""Datos del «Reporte de auditoría» de una corrida (HU-21).

Las cifras (Pass Rate, cobertura, costo, controles) salen de `results.json`; el texto
que el auditor lee (contrato del Planner, test generado y traza) sale de `detalle.json`,
en la misma carpeta de la corrida. La pantalla solo muestra lo que devuelve
`vista_reporte()`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from qagent.storage.registro import ARCHIVO_DETALLE, CARPETA_RUNS
from qagent.storage.vista_ejecucion import estado_de, identidad_de, tipo_de

#: Meta de Mutation Score de la carta (ADR-001); se aplica cuando EN-09 ejecute mutmut.
MUTATION_SCORE_MIN = 60

#: Estado de cada control para la pantalla.
OK, FALLA, NO_APLICA, PENDIENTE, SIN_DATO = (
    "ok",
    "falla",
    "no_aplica",
    "pendiente",
    "sin_dato",
)


def leer_detalle(raiz_proyecto: str | Path, run_id: str) -> dict[str, Any] | None:
    """detalle.json de la corrida, o None si no existe (corridas anteriores a HU-21)."""
    ruta = Path(raiz_proyecto) / CARPETA_RUNS / Path(run_id).name / ARCHIVO_DETALLE
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return datos if isinstance(datos, dict) else None


def vista_reporte(
    results: dict[str, Any], detalle: dict[str, Any] | None
) -> dict[str, Any]:
    """Cabecera, 4 indicadores, filtros y una tarjeta por función."""
    resumen = results["resumen"]
    metas = resumen.get("metas") or {}
    textos = {
        (f["modulo"], f["funcion"]): f
        for f in (detalle or {}).get("funciones", [])
        if isinstance(f, dict)
    }
    funciones = [
        _funcion(o, textos.get((o["modulo"], o["funcion"])), metas)
        for o in results["objetivos"]
    ]
    verdes = sum(1 for f in funciones if f["verde"])
    tipos = [tipo_de(o) for o in results["objetivos"]]
    pasaron = sum(1 for o in results["objetivos"] if o["metricas"]["paso"])
    por_agente = resumen.get("por_agente") or {}

    return {
        "run_id": results["run_id"],
        "fecha": results["fecha"],
        "perfil": results["perfil"],
        "rama": results.get("rama"),
        "proyecto": results["proyecto"],
        "es_simulado": results["es_simulado"],
        "estado_final": results["estado_final"],
        "motivo_fallo": results["motivo_fallo"],
        "total_funciones": resumen["total_funciones"],
        "total_objetivos": len(funciones),
        "modelos": {
            agente: {"proveedor": m["proveedor"], "modelo": m["modelo"]}
            for agente, m in results["modelos"].items()
        },
        "detalle_disponible": detalle is not None,
        "indicadores": {
            "pass_rate": {
                "valor": resumen["pass_rate"],
                "pasaron": pasaron,
                "total": len(results["objetivos"]),
                "meta": metas.get("pass_rate_min"),
            },
            "cobertura": {
                "lineas": resumen["cobertura_lineas_promedio"],
                "ramas": resumen.get("cobertura_ramas_promedio"),
            },
            "costo": {
                "usd": resumen["costo_total_usd"],
                "tokens": sum(
                    f["prompt_tokens"] + f["completion_tokens"]
                    for f in por_agente.values()
                ),
                "tope_usd": metas.get("tope_por_corrida_usd"),
            },
            "balance": {"ok": verdes, "alertas": len(funciones) - verdes},
        },
        "filtros": [
            {"clave": "todas", "etiqueta": "Todas", "cantidad": len(funciones)},
            {"clave": "verde", "etiqueta": "En verde", "cantidad": verdes},
            {
                "clave": "incidentes",
                "etiqueta": "Incidentes",
                "cantidad": len(funciones) - verdes,
            },
        ],
        "filtros_tipo": [
            {"clave": "todos", "etiqueta": "Todos", "cantidad": len(funciones)},
            {
                "clave": "funcion",
                "etiqueta": "Funciones",
                "cantidad": tipos.count("funcion"),
            },
            {
                "clave": "endpoint",
                "etiqueta": "Endpoints",
                "cantidad": tipos.count("endpoint"),
            },
        ],
        "funciones": funciones,
    }


# --- Una función ------------------------------------------------------------------


def _funcion(
    objetivo: dict[str, Any], texto: dict[str, Any] | None, metas: dict[str, Any]
) -> dict[str, Any]:
    metricas = objetivo["metricas"]
    contrato = (texto or {}).get("contrato")
    controles = _controles(objetivo, metas)
    verde = objetivo["decision"] == "accept" and all(
        c["estado"] in (OK, NO_APLICA, PENDIENTE) for c in controles
    )
    return {
        "modulo": objetivo["modulo"],
        "funcion": objetivo["funcion"],
        **identidad_de(objetivo),
        "firma": contrato.get("firma") if isinstance(contrato, dict) else None,
        "manejador": contrato.get("manejador") if isinstance(contrato, dict) else None,
        "critical": objetivo["critical"],
        "decision": objetivo["decision"],
        "estado": estado_de(objetivo),
        "verde": verde,
        "iteraciones": metricas["iteraciones"],
        "cobertura_lineas": metricas["cobertura_lineas"],
        "cobertura_ramas": metricas["cobertura_ramas"],
        "mutation_score": metricas["mutation_score"],
        "contrato": contrato,
        "contrato_http": _contrato_http(contrato),
        "codigo": (texto or {}).get("codigo"),
        "traza": (texto or {}).get("traza"),
        "controles": controles,
    }


def _contrato_http(contrato: Any) -> dict[str, Any] | None:
    """Petición y respuesta del endpoint, copiadas sin inferencias del contrato."""
    if not isinstance(contrato, dict) or contrato.get("tipo") != "endpoint":
        return None
    casos = []
    for caso in contrato.get("casos") or []:
        if not isinstance(caso, dict):
            continue
        entrada = caso.get("entrada")
        esperado = caso.get("valor_esperado")
        if not isinstance(entrada, dict) or not isinstance(esperado, dict):
            continue
        casos.append(
            {
                "id": caso.get("id"),
                "descripcion": caso.get("descripcion"),
                "peticion": entrada,
                "respuesta_esperada": esperado,
                "origen": caso.get("origen"),
            }
        )
    return {"casos": casos}


def _controles(objetivo: dict[str, Any], metas: dict[str, Any]) -> list[dict[str, Any]]:
    """Los 5 controles en orden, con su texto; salen de `objetivo["controles"]`."""
    guardados = objetivo.get("controles") or {}
    metricas = objetivo["metricas"]
    minimo = metas.get("cobertura_lineas_min", 60)
    lineas, ramas = metricas["cobertura_lineas"], metricas["cobertura_ramas"]
    texto_ramas = "sin ramas" if ramas is None else f"{ramas:g} %"
    texto_lineas = "—" if lineas is None else f"{lineas:g} %"
    es_bug = objetivo["decision"] == "bug_detectado"

    def control(clave: str, etiqueta: str) -> dict[str, Any]:
        valor = guardados.get(clave)
        estado = SIN_DATO if valor is None else (OK if valor else FALLA)
        return {"clave": clave, "etiqueta": etiqueta, "estado": estado}

    cobertura = control(
        "cobertura",
        f"Cobertura de líneas ({texto_lineas}) y ramas ({texto_ramas}) ≥ {minimo:g} %",
    )
    if cobertura["estado"] == SIN_DATO and lineas is not None:  # corridas anteriores
        cumple = lineas >= minimo and (ramas is None or ramas >= minimo)
        cobertura["estado"] = OK if cumple else FALLA

    if not objetivo["critical"]:
        sujeto = "el endpoint" if tipo_de(objetivo) == "endpoint" else "la función"
        mutation = {
            "clave": "mutation",
            "etiqueta": f"Mutation Score ≥ {MUTATION_SCORE_MIN} %",
            "estado": NO_APLICA,
            "nota": f"No aplica: {sujeto} no es crítico",
        }
    elif metricas["mutation_score"] is None:
        mutation = {
            "clave": "mutation",
            "etiqueta": f"Mutation Score ≥ {MUTATION_SCORE_MIN} %",
            "estado": PENDIENTE,
            "nota": "Pendiente: mutmut llega en el Sprint 2 (EN-09)",
        }
    else:
        score = metricas["mutation_score"]
        mutation = {
            "clave": "mutation",
            "etiqueta": f"Mutation Score ≥ {MUTATION_SCORE_MIN} % (obtenido: {score:g} %)",
            "estado": OK if score >= MUTATION_SCORE_MIN else FALLA,
        }

    return [
        control("sintaxis", "Sin errores de sintaxis"),
        control("sandbox", "Ejecutó en el sandbox sin errores de entorno"),
        control(
            "aserciones",
            "Oráculo trazable al contrato del Planner"
            if es_bug
            else "Aserciones no relajadas (anti-laundering)",
        ),
        cobertura,
        mutation,
    ]
