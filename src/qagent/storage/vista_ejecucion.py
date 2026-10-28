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
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from qagent import contracts
from qagent.contracts import ContratoInvalido
from qagent.storage.registro import (
    CARPETA_RUNS,
    MUTATION_SCORE_MIN,
    PERFIL_HUMO,
    PERFILES_CON_MUTACION,
    nombre_perfil,
)

ARCHIVO = "results.json"
#: Nombre de cada categoría de caso en singular y plural (#76).
NOMBRES_CATEGORIA = {
    "normal": ("normal", "normales"),
    "limite": ("límite", "límites"),
    "error": ("error", "errores"),
}
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

    omitidos_crudos = results.get("omitidos") or []
    total_omitidos = _primer_entero(
        results.get("objetivos_omitidos"),
        resumen.get("objetivos_omitidos"),
        len(omitidos_crudos),
    )
    total_seleccionados = _primer_entero(
        results.get("total_seleccionados"),
        resumen.get("total_seleccionados"),
        len(objetivos) + total_omitidos,
    )
    total_procesados = len(objetivos)
    total_elegibles = _primer_entero(
        results.get("total_elegibles"),
        resumen.get("total_elegibles"),
        max(0, total_seleccionados - total_omitidos),
    )
    total_pendientes = (
        results.get("total_pendientes")
        if results.get("total_pendientes") is not None
        else (
            resumen.get("total_pendientes")
            if resumen.get("total_pendientes") is not None
            else max(0, total_elegibles - total_procesados)
        )
    )
    tipo_terminacion = (
        results.get("tipo_terminacion")
        or resumen.get("tipo_terminacion")
        or (
            "completada"
            if results.get("estado_final") == "fin" and total_pendientes == 0
            else "detenida_error"
        )
    )
    es_parcial = total_pendientes > 0 or tipo_terminacion in (
        "cancelada",
        "limitada_recursos",
    )

    omitidos = [
        {**o, **identidad_de({"funcion": o["objetivo"], "tipo": o["tipo"]})}
        for o in omitidos_crudos
    ]

    return {
        "total_seleccionados": total_seleccionados,
        "total_elegibles": total_elegibles,
        "total_procesados": total_procesados,
        "total_pendientes": total_pendientes,
        # Seleccionados que no se probaron, con su motivo (no son pendientes).
        "omitidos": omitidos,
        "total_omitidos": total_omitidos,
        "tipo_terminacion": tipo_terminacion,
        "es_parcial": es_parcial,
        "run_id": results["run_id"],
        "fecha": results["fecha"],
        "perfil": results["perfil"],
        "perfil_nombre": nombre_perfil(results["perfil"]),
        # #75: Humo prueba un caso normal por objetivo; el Pass Rate es lo principal y
        # la cobertura de ramas no se exige.
        "es_humo": results["perfil"] == PERFIL_HUMO,
        "es_simulado": results["es_simulado"],
        "estado_final": results["estado_final"],
        "motivo_fallo": results["motivo_fallo"],
        "inicio": results.get("inicio"),
        "fin": results.get("fin"),
        "duracion_total_s": _numero(
            results.get("duracion_s", resumen.get("duracion_s"))
        ),
        "duracion_etapas": results.get("duracion_etapas")
        or resumen.get("duracion_etapas"),
        "total_funciones": resumen["total_funciones"],
        "total_objetivos": len(objetivos),
        "metas_registradas": metas is not None,
        "indicadores": {
            "pass_rate": _pass_rate(objetivos, resumen, metas),
            "cobertura": {
                **_cobertura(objetivos, resumen, metas),
                "exige_ramas": results["perfil"] != PERFIL_HUMO,
            },
            "iteraciones": _iteraciones(objetivos, resumen, metas),
            "costo": _costo(objetivos, resumen, metas),
            "mutation_score": _mutation_score(objetivos, results["perfil"]),
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


def corrida_incompleta(datos: Mapping[str, Any]) -> bool:
    """Si la corrida no revisó todo lo que debía: parcial, detenida o cancelada.

    Recibe una vista (`vista_ejecucion`, `vista_reporte`) o los datos del informe.
    """
    return bool(datos.get("es_parcial")) or datos.get("tipo_terminacion") in (
        "detenida_error",
        "cancelada",
        "limitada_recursos",
    )


def respuesta_principal(
    *,
    bugs: int,
    primer_bug: str | None,
    sin_prueba: int,
    total: int,
    omitidos: int,
    incompleta: bool,
) -> str:
    """La frase que resume la corrida en Resultados y en los informes.

    «Todo pasó» solo si se probó algo, nada falló ni quedó sin prueba, no hubo
    objetivos omitidos y la corrida terminó.

    Args:
        bugs: objetivos con posible bug.
        primer_bug: nombre del primero (el que conviene revisar antes).
        sin_prueba: objetivos sin prueba válida o que requieren corrida nueva.
        total: objetivos probados (sin contar los omitidos).
        omitidos: seleccionados que no se probaron.
        incompleta: `corrida_incompleta()` de la corrida.
    """
    if bugs:
        nombre = primer_bug or "la primera función"
        return (
            f"{bugs} {'posible bug' if bugs == 1 else 'posibles bugs'}. "
            f"Empieza por {nombre}."
        )
    no_se_probaron = f"{omitidos} {'objetivo no se probó' if omitidos == 1 else 'objetivos no se probaron'}"
    if not total:
        if incompleta:
            return "La corrida se detuvo antes de probar algo."
        if omitidos:
            return f"No se probó nada: {no_se_probaron}."
        return "No se probó ninguna función ni endpoint."
    if sin_prueba:
        return "Sin posibles bugs, pero faltan pruebas por revisar."
    if omitidos:
        return f"Sin posibles bugs en lo probado, pero {no_se_probaron}."
    if incompleta:
        return "Sin posibles bugs en lo probado, pero la corrida no terminó."
    return (
        f"Todo pasó: {total} "
        f"{'función o endpoint verificado' if total == 1 else 'funciones y endpoints verificados'}."
    )


def _numero(valor: Any) -> float | None:
    """Duración numérica o None (compatible con corridas anteriores a #115)."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    return round(max(0.0, float(valor)), 3)


def _primer_entero(*valores: Any) -> int:
    """Primer entero no negativo, conservando el cero como dato real."""
    for valor in valores:
        if isinstance(valor, int) and not isinstance(valor, bool) and valor >= 0:
            return valor
    return 0


def categorias_de(objetivo: dict[str, Any]) -> dict[str, int] | None:
    """Casos por categoría de un objetivo (#76); None en corridas anteriores."""
    conteo = objetivo.get("casos_por_categoria")
    return dict(conteo) if isinstance(conteo, dict) else None


def texto_categorias(conteo: dict[str, int] | None) -> str | None:
    """«2 normales · 1 límite · 1 error» (#76); None si no hay conteo."""
    if not conteo:
        return None
    partes = []
    for categoria, (singular, plural) in NOMBRES_CATEGORIA.items():
        cantidad = conteo.get(categoria, 0)
        partes.append(f"{cantidad} {singular if cantidad == 1 else plural}")
    return " · ".join(partes)


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
    tope_tokens = metas.get("tope_tokens_por_corrida") if metas else None
    tokens_total = resumen.get(
        "total_tokens", sum(a["tokens"] for a in agentes.values())
    )
    tokens_reales = resumen.get(
        "tokens_reales",
        sum(a.get("tokens_reales", a["tokens"]) for a in agentes.values()),
    )
    tokens_estimados = resumen.get(
        "tokens_estimados", sum(a.get("tokens_estimados", 0) for a in agentes.values())
    )
    return {
        "por_agente": agentes,
        "tokens_total": tokens_total,
        "tokens_reales": tokens_reales,
        "tokens_estimados": tokens_estimados,
        "costo_total_usd": costo,
        "tope_usd": tope,
        "tope_tokens": tope_tokens,
        "cumple": None if tope is None else costo <= tope,
    }


def _mutation_score(objetivos, perfil: str) -> dict[str, Any]:
    """Promedio del Mutation Score de las funciones críticas y endpoints prioritarios
    que lo tienen (EN-09, #74)."""
    criticas = [o for o in objetivos if o.get("critical")]
    medidos = [o for o in criticas if o["metricas"]["mutation_score"] is not None]
    valores = [o["metricas"]["mutation_score"] for o in medidos]
    if valores:
        valor = round(sum(valores) / len(valores), 1)
        endpoints = sum(1 for o in medidos if tipo_de(o) == "endpoint")
        funciones = len(medidos) - endpoints
        partes = [f"{funciones} función(es) crítica(s)"] if funciones else []
        if endpoints:
            partes.append(f"{endpoints} endpoint(s) prioritario(s)")
        return {
            "disponible": True,
            "valor": valor,
            "meta": MUTATION_SCORE_MIN,
            "cumple": valor >= MUTATION_SCORE_MIN,
            "funciones": funciones,
            "endpoints": endpoints,
            "texto": f"{' y '.join(partes)} · meta ≥ {MUTATION_SCORE_MIN} %",
        }
    if perfil not in PERFILES_CON_MUTACION:
        texto = "No se midió: la corrida no usó Profundizar"
    elif not criticas:
        texto = (
            "No se midió: no hay funciones marcadas para profundizar "
            "ni endpoints prioritarios"
        )
    else:
        texto = "mutmut no dio un Mutation Score: el motivo está en el informe"
    return {"disponible": False, "texto": texto}


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
                **{
                    campo: objetivo[campo]
                    for campo in (
                        "duracion_generacion_s",
                        "duracion_revision_s",
                        "duracion_sandbox_s",
                        "duracion_pytest_s",
                    )
                    if objetivo.get(campo) is not None
                },
                "cobertura_lineas": metricas["cobertura_lineas"],
                "cobertura_ramas": metricas["cobertura_ramas"],
                "motivo_estancado": objetivo["motivo_estancado"],
                # Por qué quedó sin veredicto; las corridas anteriores no lo tienen.
                "motivo_sin_veredicto": objetivo.get("motivo_sin_veredicto"),
                "critical": objetivo["critical"],
                "categorias": texto_categorias(categorias_de(objetivo)),  # #76
            }
        )
    return [{"modulo": m, "pruebas": pruebas} for m, pruebas in modulos.items()]
