"""Exportación del informe de auditoría como evidencia formal (HU-22).

Genera el informe de una corrida en tres formatos:
- PDF (`informe_<run_id>.pdf`)
- Markdown (`informe_<run_id>.md`)
- JSON (`results_<run_id>.json`)

Por defecto se guarda en `<proyecto>/.qagent/runs/<run_id>/`, o en la carpeta que el
usuario elija. Todas las cifras salen de `results.json` (las mismas que muestra la
pantalla en HU-18 y HU-21), y todo el contenido pasa por el filtro de secretos (RN-07)
para que nunca incluya claves de IA.
"""

from __future__ import annotations

import copy
import json
import os
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from qagent import __version__
from qagent.config import carga as config_carga
from qagent.config.auditoria import PATRONES, Hallazgo
from qagent.config.carga import Claves, leer_env
from qagent.storage.registro import CARPETA_RUNS
from qagent.storage.vista_ejecucion import (
    AGENTES,
    leer_results,
    vista_ejecucion,
)
from qagent.storage.vista_reporte import (
    MUTATION_SCORE_MIN,
    leer_detalle,
    vista_reporte,
)

FORMATOS = ("pdf", "md", "json", "html")

NOMBRES_AGENTE = {
    "planner": "Planner",
    "generator": "Generator",
    "reviewer": "Reviewer",
}

ETIQUETAS_ESTADO = {
    "aprobado": "APROBADO",
    "bug_detectado": "BUG DETECTADO",
    "rechazado_laundering": "RECHAZADO: LAUNDERING",
    "estancado": "ESTANCADO",
    "sin_veredicto": "SIN VEREDICTO",
}

ETIQUETAS_CONTROL = {
    "ok": "OK",
    "falla": "NO CUMPLE",
    "no_aplica": "NO APLICA",
    "pendiente": "PENDIENTE",
    "sin_dato": "SIN DATO",
}

_PATRON_ASIGNACION = re.compile(
    r"""(?ix)(\b[A-Z0-9_]*(?:API_?KEY|SECRET|PASSWORD|(?:ACCESS|AUTH|API)_?TOKEN)\b\s*[=:]\s*["']?)
    (?!os\.|environ|getenv)[A-Za-z0-9_\-/+=]{16,}"""
)


class FormatoInvalido(ValueError):
    """El formato solicitado no es pdf, md, json ni html."""


def nombre_archivo_informe(run_id: str, formato: str) -> str:
    """Nombre estándar del archivo exportado según el formato (Criterio 2)."""
    fmt = (formato or "").strip().lower()
    nombre_run = Path(run_id).name
    if fmt == "pdf":
        return f"informe_{nombre_run}.pdf"
    if fmt == "md":
        return f"informe_{nombre_run}.md"
    if fmt == "json":
        return f"results_{nombre_run}.json"
    if fmt == "html":
        return f"informe_{nombre_run}.html"
    raise FormatoInvalido(
        f"Formato de exportación no válido: {formato!r} (se espera pdf, md, json o html)."
    )


def carpeta_por_defecto(raiz_proyecto: str | Path, run_id: str) -> Path:
    """Carpeta por defecto donde se guarda el informe: `<proyecto>/.qagent/runs/<run_id>/`."""
    return Path(raiz_proyecto) / CARPETA_RUNS / Path(run_id).name


def normalizar_opciones(opciones: Mapping[str, Any] | None = None) -> dict[str, bool]:
    """Normaliza qué incluir en el informe (el resumen va siempre: Criterio 1)."""
    src = opciones or {}
    return {
        "resumen": True,
        "detalle": bool(src.get("detalle", True)),
        "trazas": bool(src.get("trazas", True)),
        "codigo": bool(src.get("codigo", True)),
        "contratos": bool(src.get("contratos", True)),
    }


def sanitizar_secretos(texto: str, claves: Claves | None = None) -> str:
    """Elimina cualquier clave de IA o patrón de secreto del texto (RN-07, Criterio 5)."""
    if not texto:
        return texto
    if claves is not None:
        texto = claves.redactar(texto)
    try:
        ruta_env = Path(config_carga.RUTA_ENV)
        if ruta_env.is_file():
            texto = Claves(leer_env(ruta_env)).redactar(texto)
    except (OSError, UnicodeDecodeError):
        pass

    texto = _PATRON_ASIGNACION.sub(r"\1***", texto)
    for nombre, patron in PATRONES.items():
        if nombre == "asignación de clave":
            continue
        texto = patron.sub("***", texto)
    return texto


def _sanitizar_estructura(dato: Any, claves: Claves | None = None) -> Any:
    """Aplica `sanitizar_secretos` recursivamente sobre diccionarios y listas."""
    if isinstance(dato, str):
        return sanitizar_secretos(dato, claves)
    if isinstance(dato, list):
        return [_sanitizar_estructura(item, claves) for item in dato]
    if isinstance(dato, dict):
        return {
            sanitizar_secretos(str(k), claves) if isinstance(k, str) else k: (
                _sanitizar_estructura(v, claves)
            )
            for k, v in dato.items()
        }
    return dato


def resumen_specs_corrida(raiz_proyecto: str | Path, run_id: str) -> dict[str, Any]:
    """Obtiene los specs reutilizados, regenerados y generados en la corrida (Criterio 3)."""
    from qagent.almacenamiento.proyecto import AlmacenProyecto, ErrorAlmacen

    almacen = AlmacenProyecto(raiz_proyecto)
    registros: list[dict[str, Any]] = []
    try:
        run = almacen.leer_run(run_id)
        if isinstance(run.get("specs"), list):
            registros = list(run["specs"])
    except ErrorAlmacen:
        ruta_run = Path(raiz_proyecto) / CARPETA_RUNS / Path(run_id).name / "run.json"
        try:
            datos_run = json.loads(ruta_run.read_text(encoding="utf-8"))
            if isinstance(datos_run.get("specs"), list):
                registros = list(datos_run["specs"])
        except (OSError, json.JSONDecodeError):
            registros = []

    if not registros and almacen.existe():
        planes = almacen.listar_planes_modulo()
        de_corrida = [p for p in planes if p.get("ultima_corrida") == run_id]
        fuente = de_corrida or planes
        registros = [
            {
                "modulo": p["modulo"],
                "huella": p["huella"],
                "run_origen": p["run_origen"],
                "estado": p["ultima_accion"],
            }
            for p in fuente
        ]

    por_estado: dict[str, list[str]] = {
        "reutilizado": [],
        "regenerado": [],
        "generado": [],
    }
    for reg in registros:
        estado = reg.get("estado")
        modulo = reg.get("modulo")
        if estado in por_estado and isinstance(modulo, str):
            por_estado[estado].append(modulo)

    reutilizados = len(por_estado["reutilizado"])
    regenerados = len(por_estado["regenerado"])
    generados = len(por_estado["generado"])

    partes: list[str] = []
    if reutilizados or not (regenerados or generados):
        mods = (
            f" ({', '.join(por_estado['reutilizado'])})"
            if por_estado["reutilizado"]
            else ""
        )
        partes.append(f"{reutilizados} reutilizados{mods}")
    if regenerados:
        mods = f" ({', '.join(por_estado['regenerado'])})"
        partes.append(f"{regenerados} regenerados{mods}")
    if generados:
        mods = f" ({', '.join(por_estado['generado'])})"
        partes.append(f"{generados} generados{mods}")
    texto = " · ".join(partes) + " · guardados en `.qagent/specs/`"

    return {
        "reutilizados": reutilizados,
        "regenerados": regenerados,
        "generados": generados,
        "modulos_reutilizados": por_estado["reutilizado"],
        "modulos_regenerados": por_estado["regenerado"],
        "modulos_generados": por_estado["generado"],
        "registros": registros,
        "texto": texto,
    }


def construir_cinco_metricas(results: dict[str, Any]) -> list[dict[str, Any]]:
    """Calcula las 5 métricas con su meta y estado (Cumple / No cumple) desde results.json."""
    ejec = vista_ejecucion(results)
    ind = ejec["indicadores"]
    resumen = results["resumen"]
    metas = resumen.get("metas") or {}
    objetivos = results["objetivos"]

    # 1. Pass Rate
    pr = ind["pass_rate"]
    pr_meta = pr["meta"] if pr["meta"] is not None else metas.get("pass_rate_min", 70)
    pr_cumple = bool(pr["valor"] >= pr_meta)

    # 2. Cobertura de líneas / ramas
    cv = ind["cobertura"]
    cv_meta = (
        cv["meta_lineas"]
        if cv["meta_lineas"] is not None
        else metas.get("cobertura_lineas_min", 60)
    )
    cv_cumple = bool(cv["lineas"] is not None and cv["lineas"] >= cv_meta)

    # 3. Iteraciones promedio
    it = ind["iteraciones"]
    it_meta = (
        it["meta_max"]
        if it["meta_max"] is not None
        else metas.get("iteraciones_promedio_max", 2.0)
    )
    it_cumple = bool(it["valor"] is not None and it["valor"] <= it_meta)

    # 4. Tokens y costo por corrida
    cs = ind["costo"]
    cs_meta = (
        cs["tope_usd"]
        if cs["tope_usd"] is not None
        else metas.get("tope_por_corrida_usd", 1.0)
    )
    cs_cumple = bool(cs["costo_total_usd"] <= cs_meta)

    # 5. Mutation Score
    criticas = [o for o in objetivos if o.get("critical")]
    fuente_ms = criticas if criticas else objetivos
    valores_ms = [
        o["metricas"]["mutation_score"]
        for o in fuente_ms
        if o["metricas"].get("mutation_score") is not None
    ]
    ms_valor = round(sum(valores_ms) / len(valores_ms), 1) if valores_ms else None
    ms_meta = float(MUTATION_SCORE_MIN)
    ms_cumple = bool(ms_valor is not None and ms_valor >= ms_meta)
    if ms_valor is not None:
        ms_resultado = f"{ms_valor:.1f}% ({len(criticas)} críticas)"
        ms_estado = "Cumple" if ms_cumple else "No cumple"
    else:
        ms_resultado = f"N/A ({len(criticas)} críticas)"
        ms_estado = "No cumple (sin medición)"

    return [
        {
            "clave": "pass_rate",
            "nombre": "Pass Rate",
            "valor": pr["valor"],
            "pasaron": pr["pasaron"],
            "total": pr["total"],
            "resultado": f"{pr['valor']:.1f}% ({pr['pasaron']}/{pr['total']})",
            "meta_valor": pr_meta,
            "meta": f"≥ {pr_meta:g}%",
            "cumple": pr_cumple,
            "estado": "Cumple" if pr_cumple else "No cumple",
        },
        {
            "clave": "cobertura",
            "nombre": "Cobertura de líneas / ramas",
            "lineas": cv["lineas"],
            "ramas": cv["ramas"],
            "resultado": f"{_fmt_pct(cv['lineas'])} / {_fmt_pct(cv['ramas'])}",
            "meta_valor": cv_meta,
            "meta": f"≥ {cv_meta:g}% líneas",
            "cumple": cv_cumple,
            "estado": "Cumple" if cv_cumple else "No cumple",
        },
        {
            "clave": "iteraciones",
            "nombre": "Iteraciones promedio",
            "valor": it["valor"],
            "tope": it["tope"],
            "resultado": "—" if it["valor"] is None else f"{it['valor']:.2f}",
            "meta_valor": it_meta,
            "meta": f"≤ {it_meta:g} (máx. {it['tope']})",
            "cumple": it_cumple,
            "estado": "Cumple" if it_cumple else "No cumple",
        },
        {
            "clave": "costo",
            "nombre": "Tokens y costo de la corrida",
            "tokens_total": cs["tokens_total"],
            "costo_total_usd": cs["costo_total_usd"],
            "por_agente": cs["por_agente"],
            "resultado": (
                f"{cs['tokens_total']} tokens · US$ {cs['costo_total_usd']:.4f}"
            ),
            "meta_valor": cs_meta,
            "meta": f"≤ US$ {cs_meta:.2f}",
            "cumple": cs_cumple,
            "estado": "Cumple" if cs_cumple else "No cumple",
        },
        {
            "clave": "mutation_score",
            "nombre": f"Mutation Score ({len(criticas)} funciones críticas)",
            "valor": ms_valor,
            "criticas": len(criticas),
            "resultado": ms_resultado,
            "meta_valor": ms_meta,
            "meta": f"≥ {ms_meta:g}%",
            "cumple": ms_cumple,
            "estado": ms_estado,
        },
    ]


# Casos de pytest y datos de la ejecución (EN-17): lo que comparten las cuatro salidas.

_ETIQUETA_CASO = {
    "paso": "PASÓ",
    "fallo": "FALLÓ",
    "error": "ERROR",
    "omitido": "OMITIDO",
}
_ETIQUETA_DECISION = {
    "accept": "Aceptado",
    "retry": "Reintento",
    "bug_detectado": "Bug detectado",
    "stalled": "Estancado",
}
_MOTIVO_FALLO = {
    "bug_codigo": "el código no cumple el contrato",
    "error_test": "el test estaba mal escrito",
}


def _resumen_casos_planner(contrato: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Extrae los casos planificados por el Planner de forma estructurada."""
    if not isinstance(contrato, dict):
        return []
    casos = []
    if isinstance(contrato.get("casos"), list):
        for idx, c in enumerate(contrato["casos"]):
            if not isinstance(c, dict):
                continue
            casos.append(
                {
                    "id": c.get("id") or f"caso_{idx + 1}",
                    "descripcion": c.get("descripcion") or f"Caso {idx + 1}",
                    "tipo": c.get("tipo", "normal"),
                    "entrada": c.get("entrada") or c.get("entradas"),
                    "esperado": c.get("valor_esperado") or c.get("esperado"),
                    "excepcion": c.get("excepcion"),
                    "origen": c.get("origen"),
                }
            )
    elif isinstance(contrato.get("comportamiento_esperado"), list):
        for idx, comp in enumerate(contrato["comportamiento_esperado"]):
            casos.append(
                {
                    "id": f"regla_{idx + 1}",
                    "descripcion": str(comp),
                    "tipo": "especificacion",
                    "entrada": None,
                    "esperado": str(comp),
                    "excepcion": None,
                    "origen": "docstring / especificación",
                }
            )
    return casos


def _salud_proyecto(datos: dict[str, Any]) -> dict[str, Any]:
    """Sintetiza métricas prácticas, fortalezas, deficiencias y plan de mejora del proyecto."""
    funciones = datos.get("funciones") or []
    total = len(funciones)
    aprobadas = sum(1 for f in funciones if f.get("estado") == "aprobado")
    bugs = sum(1 for f in funciones if f.get("estado") == "bug_detectado")
    laundering = sum(
        1
        for f in funciones
        if f.get("estado") == "rechazado_laundering" or f.get("laundering_detectado")
    )
    estancadas = sum(1 for f in funciones if f.get("estado") == "estancado")

    lineas_vals = [float(f.get("cobertura_lineas") or 0.0) for f in funciones]
    ramas_vals = [float(f.get("cobertura_ramas") or 0.0) for f in funciones]
    prom_lineas = round(sum(lineas_vals) / len(lineas_vals), 1) if lineas_vals else 0.0
    prom_ramas = round(sum(ramas_vals) / len(ramas_vals), 1) if ramas_vals else 0.0

    criticas_fns = [f for f in funciones if f.get("critical")]
    ms_vals = [
        float(f["mutation_score"])
        for f in criticas_fns
        if f.get("mutation_score") is not None
    ]
    prom_ms = round(sum(ms_vals) / len(ms_vals), 1) if ms_vals else None

    pct_aprobadas = (aprobadas / total * 100.0) if total else 0.0
    pts_pass = (aprobadas / total * 45.0) if total else 0.0
    pts_lin = (min(100.0, prom_lineas) / 100.0) * 25.0
    pts_ram = (min(100.0, prom_ramas) / 100.0) * 15.0
    pts_ms = ((prom_ms / 100.0) * 15.0) if prom_ms is not None else 12.0
    penalizacion_laund = laundering * 8.0
    penalizacion_bugs = bugs * 5.0
    indice_salud = max(
        0,
        min(
            100,
            round(
                pts_pass
                + pts_lin
                + pts_ram
                + pts_ms
                - penalizacion_laund
                - penalizacion_bugs
            ),
        ),
    )

    if indice_salud >= 90:
        nivel_madurez = "Excelente (Listo para producción)"
        estado_salud = "excelente"
    elif indice_salud >= 75:
        nivel_madurez = "Estable (Observaciones menores)"
        estado_salud = "estable"
    elif indice_salud >= 50:
        nivel_madurez = "En Riesgo (Requiere correcciones prioritarias)"
        estado_salud = "riesgo"
    else:
        nivel_madurez = "Crítico (Defectos estructurales detectados)"
        estado_salud = "critico"

    fortalezas: list[str] = []
    fns_alta_cob = [
        f
        for f in funciones
        if (f.get("cobertura_lineas") or 0.0) >= 90.0 and f.get("verde", True)
    ]
    if fns_alta_cob:
        nombres = ", ".join(
            f"`{f['funcion']}` ({f['modulo']})" for f in fns_alta_cob[:3]
        )
        if len(fns_alta_cob) > 3:
            nombres += f" y {len(fns_alta_cob) - 3} más"
        fortalezas.append(
            f"Alta cobertura de código: {len(fns_alta_cob)}/{total} funciones ({nombres}) "
            f"alcanzan >= 90% de cobertura en líneas con pruebas unitarias sólidas."
        )
    fns_ms_ok = [f for f in criticas_fns if (f.get("mutation_score") or 0.0) >= 60.0]
    if fns_ms_ok:
        crit_nombres = ", ".join(f"`{f['funcion']}`" for f in fns_ms_ok)
        fortalezas.append(
            f"Resistencia frente a mutaciones: Funciones críticas ({crit_nombres}) superan "
            f"el 60% de Mutation Score, garantizando aserciones sensibles a cambios de lógica."
        )
    fns_sin_laund = [
        f
        for f in funciones
        if not f.get("laundering_detectado") and f.get("verde", True)
    ]
    if fns_sin_laund:
        fortalezas.append(
            f"Integridad de contratos: {len(fns_sin_laund)}/{total} funciones mantuvieron "
            f"oráculos estrictos sin debilitar ni relajar aserciones."
        )
    if prom_lineas >= 80.0:
        fortalezas.append(
            f"Promedio general de cobertura saludable: {prom_lineas:.1f}% en líneas y {prom_ramas:.1f}% en ramas evaluadas."
        )

    deficiencias: list[str] = []
    fns_bugs = [f for f in funciones if f.get("estado") == "bug_detectado"]
    for fb in fns_bugs:
        ejec = fb.get("ejecucion") or {}
        casos_f = [
            c for c in ejec.get("casos", []) if c.get("resultado") in ("fallo", "error")
        ]
        prim = casos_f[0] if casos_f else None
        ubicacion = (
            f"{prim['archivo']}:{prim.get('linea')}"
            if prim and prim.get("archivo")
            else f"{fb['modulo']}::{fb['funcion']}"
        )
        esp_obt = (
            f" (esperado: {prim.get('esperado')}, obtenido: {prim.get('obtenido')})"
            if prim and prim.get("esperado") is not None
            else ""
        )
        deficiencias.append(
            f"Defecto de lógica detectado en `{fb['modulo']}::{fb['funcion']}`: "
            f"Fallo en aserción en `{ubicacion}`{esp_obt}. El código de producción no cumple el contrato esperado."
        )
    fns_laund = [
        f
        for f in funciones
        if f.get("laundering_detectado") or f.get("estado") == "rechazado_laundering"
    ]
    for fl in fns_laund:
        deficiencias.append(
            f"Intento de alteración de aserciones (Assertion Laundering) en `{fl['modulo']}::{fl['funcion']}`: "
            f"Se intentó debilitar el oráculo para ocultar un fallo, lo cual fue bloqueado por el Reviewer."
        )
    fns_bajas_ramas = [
        f for f in funciones if (f.get("cobertura_ramas") or 100.0) < 85.0
    ]
    if fns_bajas_ramas:
        bajas_txt = ", ".join(
            f"`{f['funcion']}` ({f.get('cobertura_ramas', 0):g}% ramas)"
            for f in fns_bajas_ramas[:3]
        )
        deficiencias.append(
            f"Ramas condicionales sin evaluar: {bajas_txt} dejan bifurcaciones (`if/else`) sin probar."
        )
    if not deficiencias:
        deficiencias.append(
            "No se detectaron deficiencias críticas ni anomalías en la lógica analizada."
        )

    recomendaciones: list[str] = []
    if fns_bugs:
        for fb in fns_bugs:
            recomendaciones.append(
                f"Prioridad 1 — Corregir la lógica de `{fb['modulo']}::{fb['funcion']}`: "
                f"Modificar el cálculo o condición en el código de producción para que retorne el valor esperado según la especificación del negocio."
            )
    if fns_bajas_ramas:
        bajas_nom = ", ".join(f"`{f['funcion']}`" for f in fns_bajas_ramas[:2])
        recomendaciones.append(
            f"Prioridad 2 — Agregar casos límite para ramas en {bajas_nom}: "
            f"Probar entradas vacías, bordes numéricos o condiciones alternas para alcanzar 100% de cobertura de ramas."
        )
    if fns_laund:
        recomendaciones.append(
            "Prioridad 3 — Auditar oráculos de prueba: Evitar modificar los valores esperados de las aserciones para forzar el paso de los tests; resolver siempre el defecto en el código fuente."
        )
    if not recomendaciones:
        recomendaciones.append(
            "Mantener la ejecución automatizada de esta suite en el pipeline de Integración Continua (CI) para prevenir regresiones."
        )

    incidentes_detallados = []
    for f in funciones:
        if not f.get("verde", True) or f.get("traza"):
            ejec = f.get("ejecucion") or {}
            fallos_casos = [
                c
                for c in ejec.get("casos", [])
                if c.get("resultado") in ("fallo", "error")
            ]
            primer_fallo = fallos_casos[0] if fallos_casos else None
            donde = (
                f"{primer_fallo['archivo']}:{primer_fallo['linea']}"
                if primer_fallo and primer_fallo.get("archivo")
                else f"{f['modulo']}::{f['funcion']}"
            )
            motivo = f.get("motivo_fallo") or (
                primer_fallo.get("mensaje")
                if primer_fallo
                else "Discrepancia detectada en aserción de prueba"
            )
            accion = (
                f"Corregir cálculo/retorno en `{f['modulo']}::{f['funcion']}`"
                if f.get("estado") == "bug_detectado"
                else (
                    f"Restaurar aserción estricta en suite de tests de `{f['funcion']}`"
                    if f.get("laundering_detectado")
                    else "Revisar traza de ejecución en el sandbox"
                )
            )
            incidentes_detallados.append(
                {
                    "funcion": f["funcion"],
                    "modulo": f["modulo"],
                    "estado": f.get("estado"),
                    "ubicacion": donde,
                    "causa": motivo,
                    "tipo_error": (
                        primer_fallo.get("tipo_error")
                        if primer_fallo
                        else "AssertionError"
                    ),
                    "esperado": primer_fallo.get("esperado") if primer_fallo else None,
                    "obtenido": primer_fallo.get("obtenido") if primer_fallo else None,
                    "laundering": bool(f.get("laundering_detectado")),
                    "accion_sugerida": accion,
                }
            )

    if bugs == 0 and laundering == 0 and estancadas == 0:
        diagnostico = (
            f"El proyecto supera con éxito las pruebas unitarias ({aprobadas}/{total} funciones aprobadas, "
            f"{pct_aprobadas:.1f}%). No se detectaron defectos en la lógica evaluada."
        )
    else:
        partes = [f"{aprobadas}/{total} aprobadas ({pct_aprobadas:.1f}%)"]
        if bugs:
            partes.append(f"{bugs} con defecto confirmado en código (bug detectado)")
        if laundering:
            partes.append(f"{laundering} con aserciones relajadas rechazadas")
        if estancadas:
            partes.append(f"{estancadas} estancadas")
        diagnostico = (
            f"El proyecto presenta observaciones de calidad: {', '.join(partes)}. "
            "Consulte las deficiencias y el plan de mejora para corregir las líneas afectadas en su código."
        )

    return {
        "total": total,
        "aprobadas": aprobadas,
        "bugs": bugs,
        "laundering": laundering,
        "estancadas": estancadas,
        "pct_aprobadas": pct_aprobadas,
        "indice_salud": indice_salud,
        "nivel_madurez": nivel_madurez,
        "estado_salud": estado_salud,
        "diagnostico": diagnostico,
        "fortalezas": fortalezas,
        "deficiencias": deficiencias,
        "recomendaciones": recomendaciones,
        "incidentes": incidentes_detallados,
    }


def _filas_entorno(datos: dict[str, Any]) -> list[tuple[str, str]]:
    """Pares (etiqueta, valor) con los datos de la ejecución; vacío si no los hay."""
    entorno = datos.get("entorno")
    if not entorno:
        return []
    limites = entorno.get("limites") or {}
    totales = datos.get("totales_casos") or {}

    def valor(dato: Any) -> str:
        return "—" if dato in (None, "") else str(dato)

    texto_limites = (
        f"{valor(limites.get('cpus'))} CPU · {valor(limites.get('memoria'))} · "
        f"{valor(limites.get('timeout_s'))} s"
    )
    filas = [
        ("Imagen del sandbox", valor(entorno.get("imagen"))),
        ("Python", valor(entorno.get("python"))),
        ("pytest", valor(entorno.get("pytest"))),
        ("Plataforma", valor(entorno.get("plataforma"))),
        ("Límites", texto_limites),
        ("Red", "desactivada (--network none)"),
        ("Comando", valor(entorno.get("comando"))),
    ]
    if totales:
        resumen = (
            f"{totales.get('total', 0)} ({totales.get('pasaron', 0)} pasaron · "
            f"{totales.get('fallaron', 0)} fallaron · {totales.get('errores', 0)} "
            f"errores · {totales.get('omitidos', 0)} omitidos)"
        )
        filas.append(("Casos ejecutados", resumen))
    return filas


def _funciones_con_casos(datos: dict[str, Any]) -> list[dict[str, Any]]:
    return [f for f in datos["funciones"] if f.get("ejecucion")]


def _historial_intentos(f: dict[str, Any]) -> list[str]:
    """Una línea por intento: decisión del Reviewer y causa."""
    lineas = []
    for i in f.get("intentos") or []:
        decision = _ETIQUETA_DECISION.get(
            str(i.get("decision")), str(i.get("decision"))
        )
        extra = []
        causa = _MOTIVO_FALLO.get(str(i.get("tipo_fallo")), "")
        if causa:
            extra.append(causa)
        if i.get("laundering_detectado"):
            extra.append("aserciones relajadas")
        if not i.get("ejecucion"):
            extra.append("no llegó al sandbox")
        sufijo = f" ({'; '.join(extra)})" if extra else ""
        lineas.append(f"Intento {i.get('intento')}: {decision}{sufijo}")
    return lineas


def _lineas_caso(caso: dict[str, Any], con_traza: bool = True) -> list[str]:
    """Texto plano de un caso: resultado y, si falló, dónde, qué y esperado/obtenido."""
    etiqueta = _ETIQUETA_CASO.get(caso["resultado"], str(caso["resultado"]).upper())
    duracion = float(caso.get("duracion_s") or 0)
    lineas = [f"[{etiqueta}] {caso['nombre']} ({duracion:.2f} s)"]
    if caso["resultado"] in ("fallo", "error"):
        if caso.get("archivo"):
            lineas.append(f"  Dónde: {caso['archivo']}:{caso.get('linea')}")
        if caso.get("codigo"):
            lineas.append(f"  Línea: {caso['codigo']}")
        mensaje = str(caso.get("mensaje") or "").splitlines()
        partes = (caso.get("tipo_error"), mensaje[0] if mensaje else "")
        error = " — ".join(p for p in partes if p)
        if error:
            lineas.append(f"  Qué falló: {error}")
        if caso.get("esperado") is not None or caso.get("obtenido") is not None:
            lineas.append(f"  Esperado: {caso.get('esperado')}")
            lineas.append(f"  Obtenido: {caso.get('obtenido')}")
        if con_traza and caso.get("pila"):
            lineas.append("  Pila de llamadas:")
            for marco in caso["pila"]:
                detalle = " ".join(
                    p for p in (marco.get("detalle"), marco.get("codigo")) if p
                )
                lineas.append(
                    f"    {marco['archivo']}:{marco['linea']} {detalle}".rstrip()
                )
    elif caso["resultado"] == "omitido" and caso.get("mensaje"):
        lineas.append(f"  Motivo: {caso['mensaje']}")
    return lineas


def _sin_cubrir_texto(ejecucion: dict[str, Any]) -> str | None:
    sin_cubrir = ejecucion.get("lineas_sin_cubrir")
    if sin_cubrir is None:
        return None
    return "Líneas de la función sin cubrir: " + (
        ", ".join(str(n) for n in sin_cubrir) if sin_cubrir else "ninguna"
    )


def _markdown_ejecucion(datos: dict[str, Any], con_traza: bool) -> list[str]:
    """Secciones 2.1 y 2.2 del Markdown: datos de la ejecución y casos por función."""
    lineas = ["## 2.1 Datos de la ejecución", ""]
    filas = _filas_entorno(datos)
    if not filas:
        lineas.append(
            "_Esta corrida no guardó datos de ejecución (IA simulada sin sandbox o "
            "corrida anterior al informe detallado)._"
        )
        lineas.append("")
        return lineas
    lineas.extend(["| Dato | Valor |", "|---|---|"])
    lineas.extend(f"| {k} | `{v}` |" for k, v in filas)
    lineas.extend(["", "## 2.2 Casos de prueba por función", ""])
    for f in _funciones_con_casos(datos):
        estado_lbl = ETIQUETAS_ESTADO.get(f["estado"], f["estado"])
        lineas.extend([f"### {f['funcion']} ({f['modulo']}) — {estado_lbl}", ""])
        historial = _historial_intentos(f)
        if historial:
            lineas.extend(f"- {h}" for h in historial)
            lineas.append("")

        # Documentación concisa orientada al usuario
        contrato = f.get("contrato") or {}
        casos_plan = _resumen_casos_planner(contrato)
        firma = (
            f.get("firma")
            or contrato.get("firma")
            or f.get("manejador")
            or f["funcion"]
        )
        crit_txt = "Crítica" if f["critical"] else "Estándar"
        lineas.append(
            f"- **Objetivo analizado:** `{firma}` ({len(casos_plan)} casos deducidos del AST · {crit_txt})"
        )
        lineas.append(
            f"- **Suite pytest:** `tests/test_{f['funcion']}.py` ({f['iteraciones']}/3 iteraciones en sandbox hermético)"
        )
        laund_txt = (
            "DETECTADO (aserciones alteradas)"
            if f.get("laundering_detectado")
            else "Aserciones estrictas e íntegras"
        )
        lineas.append(
            f"- **Evaluación del Reviewer:** {estado_lbl} · Cobertura: {_fmt_pct(f['cobertura_lineas'])} líneas / {_fmt_pct(f['cobertura_ramas'])} ramas · Laundering: {laund_txt}"
        )
        for it in f.get("intentos") or []:
            fb = it.get("feedback")
            if fb:
                lineas.append(
                    f"  - *Diagnóstico Reviewer (Intento {it.get('intento')}):* {fb}"
                )
        lineas.append("")

        ejecucion = f["ejecucion"]
        lineas.extend(["| Resultado | Caso | Duración | Dónde |", "|---|---|---|---|"])
        for c in ejecucion["casos"]:
            donde = f"{c['archivo']}:{c['linea']}" if c.get("archivo") else "—"
            icono = {"paso": "✅", "omitido": "⏭️"}.get(c["resultado"], "❌")
            etiqueta = _ETIQUETA_CASO.get(c["resultado"], c["resultado"])
            duracion = float(c.get("duracion_s") or 0)
            lineas.append(
                f"| {icono} {etiqueta} | {c['nombre']} | {duracion:.2f} s | {donde} |"
            )
        lineas.append("")
        fallos = [c for c in ejecucion["casos"] if c["resultado"] in ("fallo", "error")]
        if fallos:
            lineas.append("```text")
            for c in fallos:
                lineas.extend(_lineas_caso(c, con_traza))
                lineas.append("")
            lineas.extend(["```", ""])
        cubierta = _sin_cubrir_texto(ejecucion)
        if cubierta:
            lineas.extend([cubierta, ""])
        if con_traza and ejecucion.get("salida"):
            lineas.extend(
                ["<details><summary>Salida completa de pytest</summary>", "", "```text"]
            )
            lineas.append(str(ejecucion["salida"]))
            lineas.extend(["```", "", "</details>", ""])
    return lineas


def _json_ejecucion(datos: dict[str, Any], con_traza: bool) -> dict[str, Any]:
    """Bloque `ejecucion` del JSON exportado: entorno, totales y casos por función."""
    funciones = []
    for f in _funciones_con_casos(datos):
        intentos = []
        for i in f["intentos"]:
            item = {k: v for k, v in i.items() if k != "ejecucion"}
            ejecucion = copy.deepcopy(i.get("ejecucion"))
            if ejecucion is not None and not con_traza:
                ejecucion.pop("salida", None)
                for caso in ejecucion.get("casos", []):
                    caso.pop("traza", None)
                    caso["pila"] = []
            item["ejecucion"] = ejecucion
            intentos.append(item)
        funciones.append(
            {
                "modulo": f["modulo"],
                "funcion": f["funcion"],
                "estado": f["estado"],
                "intentos": intentos,
            }
        )
    return {
        "entorno": copy.deepcopy(datos.get("entorno")),
        "totales_casos": copy.deepcopy(datos.get("totales_casos")),
        "funciones": funciones,
    }


def _html_ejecucion(datos: dict[str, Any], con_traza: bool, esc: Any) -> str:
    """Contenido de la pestaña «Casos y ejecución» del HTML."""
    filas = _filas_entorno(datos)
    if not filas:
        return (
            "<p>Esta corrida no guardó datos de ejecución (IA simulada sin sandbox o "
            "corrida anterior al informe detallado).</p>"
        )
    entorno = "".join(
        f"<tr><th>{esc(k)}</th><td><code>{esc(v)}</code></td></tr>" for k, v in filas
    )
    partes = [f"<table><tbody>{entorno}</tbody></table>"]
    for f in _funciones_con_casos(datos):
        estado_lbl = ETIQUETAS_ESTADO.get(f["estado"], f["estado"])
        ejecucion = f["ejecucion"]
        historial = "".join(f"<li>{esc(h)}</li>" for h in _historial_intentos(f))
        casos = []
        for c in ejecucion["casos"]:
            falla = c["resultado"] in ("fallo", "error")
            clase = {"paso": "paso", "omitido": "omitido"}.get(c["resultado"], "fallo")
            detalle = ""
            if falla:
                texto = "\n".join(_lineas_caso(c, con_traza)[1:])
                traza = ""
                if con_traza and c.get("traza"):
                    traza = (
                        "<details><summary>Traza completa</summary>"
                        f"<pre>{esc(c['traza'])}</pre></details>"
                    )
                detalle = f"<pre class='fallo'>{esc(texto)}</pre>{traza}"
            etiqueta = _ETIQUETA_CASO.get(c["resultado"], c["resultado"])
            duracion = float(c.get("duracion_s") or 0)
            casos.append(
                f"<div class='caso {clase}'><b>{esc(etiqueta)}</b> {esc(c['nombre'])} "
                f"<small>{duracion:.2f} s</small>{detalle}</div>"
            )
        cubierta = _sin_cubrir_texto(ejecucion)
        cubierta_html = f"<p><small>{esc(cubierta)}</small></p>" if cubierta else ""
        salida = (
            "<details><summary>Salida completa de pytest</summary>"
            f"<pre>{esc(ejecucion['salida'])}</pre></details>"
            if con_traza and ejecucion.get("salida")
            else ""
        )
        partes.append(
            f"<div class='fn-card'><b>{esc(f['funcion'])}</b> "
            f"<span>({esc(f['modulo'])})</span> — <span class='badge'>{esc(estado_lbl)}</span>"
            f"<ul>{historial}</ul>{''.join(casos)}{cubierta_html}{salida}</div>"
        )
    return "".join(partes)


def _bloques_ejecucion(
    datos: dict[str, Any], con_traza: bool, limpiar: Any
) -> list[dict[str, Any]]:
    """Bloques del PDF (sección «Detalle»): datos de la ejecución y casos por función."""
    filas = _filas_entorno(datos)
    bloques: list[dict[str, Any]] = [
        {"tipo": "h2", "seccion": 3, "texto": "2.1 Datos de la ejecución"}
    ]
    if not filas:
        bloques.append(
            {
                "tipo": "texto",
                "seccion": 3,
                "texto": "Esta corrida no guardó datos de ejecución (IA simulada o anterior).",
            }
        )
        return bloques
    meta: list[tuple[str, str]] = []
    for etiqueta, valor in filas:
        for idx, linea in enumerate(_envolver_linea(limpiar(valor), 82)):
            meta.append((etiqueta + ":" if idx == 0 else "", linea))
    bloques.append({"tipo": "ficha_meta", "seccion": 3, "filas": meta})
    bloques.append(
        {"tipo": "h2", "seccion": 3, "texto": "2.2 Casos de prueba por función"}
    )
    for f in _funciones_con_casos(datos):
        ejecucion = f["ejecucion"]
        hay_fallo = any(
            c["resultado"] in ("fallo", "error") for c in ejecucion["casos"]
        )
        acento = "incidente" if hay_fallo else "codigo"
        bloques.append(
            {
                "tipo": "encabezado_bloque",
                "seccion": 3,
                "titulo": limpiar(f"{f['funcion']} ({f['modulo']})"),
                "etiqueta": "CASOS DE PYTEST",
                "acento": acento,
            }
        )
        lineas: list[str] = list(_historial_intentos(f))
        for caso in ejecucion["casos"]:
            lineas.extend(_lineas_caso(caso, con_traza))
        cubierta = _sin_cubrir_texto(ejecucion)
        if cubierta:
            lineas.append(cubierta)
        envueltas: list[str] = []
        for linea in lineas:
            envueltas.extend(_envolver_linea(limpiar(linea), 84) or [""])
        for idx, linea in enumerate(envueltas):
            bloques.append(
                {
                    "tipo": "linea_codigo",
                    "seccion": 3,
                    "texto": linea,
                    "acento": acento,
                    "primera": idx == 0,
                    "ultima": idx == len(envueltas) - 1,
                }
            )
        bloques.append({"tipo": "espacio", "seccion": 3, "alto": 6})
    return bloques


def datos_informe(
    raiz_proyecto: str | Path,
    run_id: str | None = None,
    claves: Claves | None = None,
) -> dict[str, Any]:
    """Reúne todos los datos del informe desde `results.json`, `detalle.json` y `run.json`."""
    from qagent.storage.corrida_demo import CORRIDA_DEMO_ID, leer_results_demo

    if run_id == CORRIDA_DEMO_ID:
        results = leer_results_demo(raiz_proyecto, run_id)
    else:
        results = leer_results(raiz_proyecto, run_id)
    run_actual = results["run_id"]
    detalle = leer_detalle(raiz_proyecto, run_actual)
    vista = vista_reporte(results, detalle)
    ejec = vista_ejecucion(results)
    metricas = construir_cinco_metricas(results)
    specs = resumen_specs_corrida(raiz_proyecto, run_actual)
    por_agente = ejec["indicadores"]["costo"]["por_agente"]

    # Tokens por función y por agente desde results.json
    tokens_funcion: dict[tuple[str, str], int] = {}
    tokens_agente_funcion: dict[tuple[str, str], dict[str, Any]] = {}
    for obj in results["objetivos"]:
        tok_ag = obj["metricas"].get("tokens_por_agente") or {}
        total_fn = sum(
            int(t.get("prompt_tokens", 0)) + int(t.get("completion_tokens", 0))
            for t in tok_ag.values()
        )
        tokens_funcion[(obj["modulo"], obj["funcion"])] = total_fn
        tokens_agente_funcion[(obj["modulo"], obj["funcion"])] = tok_ag

    funciones_enriquecidas = []
    for fn in vista["funciones"]:
        copia = dict(fn)
        copia["tokens"] = tokens_funcion.get((fn["modulo"], fn["funcion"]), 0)
        copia["tokens_por_agente"] = tokens_agente_funcion.get(
            (fn["modulo"], fn["funcion"]), {}
        )
        funciones_enriquecidas.append(copia)

    datos = {
        "run_id": run_actual,
        "fecha": results["fecha"],
        "proyecto": results["proyecto"],
        "rama": results.get("rama"),
        "perfil": results["perfil"],
        "es_simulado": results["es_simulado"],
        "estado_final": results["estado_final"],
        "motivo_fallo": results["motivo_fallo"],
        "total_funciones": results["resumen"]["total_funciones"],
        "criticas": sum(1 for o in results["objetivos"] if o.get("critical")),
        "modelos": copy.deepcopy(results["modelos"]),
        "costo_por_agente": por_agente,
        "specs": specs,
        "metricas": metricas,
        "indicadores": vista["indicadores"],
        "entorno": vista["entorno"],
        "totales_casos": vista["totales_casos"],
        "funciones": funciones_enriquecidas,
        "results": copy.deepcopy(results),
    }
    return _sanitizar_estructura(datos, claves)


def construir_markdown_informe(
    datos: dict[str, Any],
    opciones: Mapping[str, Any] | None = None,
    claves: Claves | None = None,
) -> str:
    """Construye el informe en formato Markdown (.md) según las opciones elegidas."""
    opts = normalizar_opciones(opciones)
    run_id = datos["run_id"]
    rama = datos.get("rama") or "sin repositorio Git"
    modelos_txt = " · ".join(
        f"{NOMBRES_AGENTE.get(ag, ag)}: {m['modelo']} ({m['proveedor']}, "
        f"entrada US$ {m['precio_entrada_usd_m']:g}/M · salida US$ {m['precio_salida_usd_m']:g}/M)"
        for ag in AGENTES
        if ag in datos["modelos"]
        for m in [datos["modelos"][ag]]
    )
    por_ag = datos["costo_por_agente"]
    costo_agentes_txt = " · ".join(
        f"{NOMBRES_AGENTE.get(ag, ag)}: {por_ag[ag]['tokens']} tokens "
        f"(US$ {(por_ag[ag]['costo_usd'] or 0.0):.4f})"
        for ag in AGENTES
        if ag in por_ag
    )

    lineas = [
        f"# Informe de auditoría de pruebas unitarias — Corrida #{run_id}",
        "",
        f"- **Proyecto:** {datos['proyecto']}",
        f"- **Rama:** {rama}",
        f"- **Fecha:** {datos['fecha']}",
        f"- **Perfil:** {datos['perfil']} · **Funciones evaluadas:** {datos['total_funciones']} ({datos['criticas']} críticas)",
        "- **Generado por:** QAgent (Planner → Generator → Reviewer)",
        f"- **Modelos usados:** {modelos_txt}",
        f"- **Costo por agente:** {costo_agentes_txt}",
        f"- **Specs:** {datos['specs']['texto']}",
        "",
        "## 1. Resumen de las 5 métricas",
        "",
        "| Métrica | Resultado | Meta | Estado |",
        "|---|---|---|---|",
    ]
    for m in datos["metricas"]:
        icono = "✅" if m["cumple"] else "❌"
        lineas.append(
            f"| {m['nombre']} | {m['resultado']} | {m['meta']} | {icono} {m['estado']} |"
        )
    lineas.append(
        f"| Costo por agente | {costo_agentes_txt} | Desglose por agente | Reportado |"
    )
    lineas.append("")

    salud = _salud_proyecto(datos)
    lineas.extend(
        [
            "### 1.1 Estado de salud del proyecto",
            "",
            f"- **Índice de salud del código:** {salud['indice_salud']}/100 — **Nivel:** {salud['nivel_madurez']}",
            f"- **Progreso del proyecto:** {salud['aprobadas']}/{salud['total']} funciones aprobadas ({salud['pct_aprobadas']:.1f}%)",
            f"- **Diagnóstico global:** {salud['diagnostico']}",
            (
                f"- **Balance de calidad:** ✅ {salud['aprobadas']} aprobadas · "
                f"🐛 {salud['bugs']} defectos en código · "
                f"🛡️ {salud['laundering']} laundering bloqueado · "
                f"⏳ {salud['estancadas']} estancadas (de {salud['total']} evaluadas)"
            ),
            "",
            "#### Fortalezas del proyecto",
        ]
    )
    for fort in salud["fortalezas"]:
        lineas.append(f"- ✅ {fort}")
    lineas.extend(
        [
            "",
            "#### Deficiencias detectadas (áreas de riesgo)",
        ]
    )
    for defic in salud["deficiencias"]:
        lineas.append(f"- ⚠️ {defic}")
    lineas.extend(
        [
            "",
            "#### Cómo mejorar su proyecto (Plan de acción recomendado)",
        ]
    )
    for idx_rec, rec in enumerate(salud["recomendaciones"], start=1):
        lineas.append(f"{idx_rec}. {rec}")
    lineas.append("")
    if salud["incidentes"]:
        lineas.append("- **Puntos críticos que requieren corrección en el código:**")
        for inc in salud["incidentes"]:
            det = f"`{inc['funcion']}` en `{inc['ubicacion']}`: {inc['causa']}"
            if inc["esperado"] is not None and inc["obtenido"] is not None:
                det += (
                    f" (Esperado: `{inc['esperado']}` | Obtenido: `{inc['obtenido']}`)"
                )
            if inc.get("accion_sugerida"):
                det += f" — *Sugerencia:* {inc['accion_sugerida']}"
            lineas.append(f"  - {det}")
    lineas.append("")

    if opts["detalle"]:
        lineas.extend(
            [
                "## 2. Resultado por función",
                "",
                "| Función | Módulo | Estado | Intentos | Cob. líneas | Cob. ramas | Mutation Score | Tokens |",
                "|---|---|---|---|---|---|---|---|\n".rstrip("\n"),
            ]
        )
        for f in datos["funciones"]:
            estado_lbl = ETIQUETAS_ESTADO.get(f["estado"], f["estado"])
            ms_lbl = (
                "N/A (no crítica)"
                if not f["critical"]
                else (
                    "Pendiente"
                    if f["mutation_score"] is None
                    else f"{f['mutation_score']:g}%"
                )
            )
            lineas.append(
                f"| {f['funcion']} | {f['modulo']} | {estado_lbl} | {f['iteraciones']}/3 | "
                f"{_fmt_pct(f['cobertura_lineas'])} | {_fmt_pct(f['cobertura_ramas'])} | "
                f"{ms_lbl} | {f['tokens']} |"
            )
        lineas.append("")
        lineas.extend(_markdown_ejecucion(datos, opts["trazas"]))

    if opts["trazas"]:
        lineas.extend(["## 3. Trazas del Reviewer de los incidentes", ""])
        incidentes = [f for f in datos["funciones"] if not f["verde"] or f.get("traza")]
        if not incidentes:
            lineas.append(
                "No se registraron incidentes ni trazas de fallo en esta corrida."
            )
            lineas.append("")
        else:
            for f in incidentes:
                estado_lbl = ETIQUETAS_ESTADO.get(f["estado"], f["estado"])
                lineas.append(f"### {f['funcion']} ({f['modulo']}) — {estado_lbl}")
                lineas.append("")
                # Diagnóstico formal del incidente: qué parte falló y por qué
                lineas.append(
                    f"- **Parte del código afectada:** `{f['modulo']}::{f['funcion']}`"
                )
                lineas.append(f"- **Veredicto del Reviewer:** {estado_lbl}")
                causa_incidente = f.get("motivo_fallo") or (
                    "Assertion Laundering detectado (el Generator intentó debilitar o relajar aserciones para enmascarar un fallo)."
                    if f.get("laundering_detectado")
                    else (
                        "Defecto confirmado en código (el test detectó una discrepancia frente a la especificación esperada)."
                        if f.get("estado") == "bug_detectado"
                        else "Ejecución estancada o fallo durante la validación en el sandbox."
                    )
                )
                lineas.append(f"- **¿Por qué falló?:** {causa_incidente}")
                if f.get("laundering_detectado"):
                    lineas.append(
                        "- **Incidente de seguridad:** Assertion Laundering detectado "
                        "(el Generator intentó debilitar o relajar aserciones para enmascarar un fallo)."
                    )
                intentos = f.get("intentos") or []
                if intentos:
                    lineas.append(
                        f"- **Historial de intentos del Reviewer ({len(intentos)}/3):**"
                    )
                    for it in intentos:
                        dec = _ETIQUETA_DECISION.get(
                            str(it.get("decision")), it.get("decision")
                        )
                        fb = it.get("feedback") or "Sin retroalimentación adicional."
                        lineas.append(
                            f"  - *Intento {it.get('intento')}:* Decisión `{dec}` · Diagnóstico: {fb}"
                        )
                ejec = f.get("ejecucion")
                if ejec and ejec.get("casos"):
                    fallos_caso = [
                        c
                        for c in ejec["casos"]
                        if c.get("resultado") in ("fallo", "error")
                    ]
                    if fallos_caso:
                        lineas.append("- **Casos fallidos en pytest:**")
                        for fc in fallos_caso:
                            partes_fc = [f"`{fc['nombre']}`"]
                            if fc.get("linea"):
                                partes_fc.append(f"Línea: {fc['linea']}")
                            if (
                                fc.get("esperado") is not None
                                or fc.get("obtenido") is not None
                            ):
                                partes_fc.append(
                                    f"Esperado: `{fc.get('esperado')}` | Obtenido: `{fc.get('obtenido')}`"
                                )
                            lineas.append(f"  - {' — '.join(partes_fc)}")
                lineas.append("")
                if f.get("traza"):
                    lineas.append("```text")
                    lineas.append(str(f["traza"]))
                    lineas.append("```")
                else:
                    lineas.append("_Sin traza registrada en este incidente._")
                lineas.append("")

    if opts["codigo"]:
        lineas.extend(
            [
                "## 4. Código de las pruebas generadas",
                "",
                "_Anexo de referencia: suites de prueba pytest generadas por el Generator._",
                "",
            ]
        )
        for f in datos["funciones"]:
            estado_lbl = ETIQUETAS_ESTADO.get(f["estado"], f["estado"])
            lineas.append(f"### tests/test_{f['funcion']}.py ({f['modulo']})")
            lineas.append("")
            lineas.append(
                f"- **Autor:** Generator (QAgent) · **Estado:** {estado_lbl} · "
                f"**Iteraciones:** {f['iteraciones']}/3"
            )
            lineas.append(
                "- **Entorno de prueba:** Ejecución hermética en sandbox Docker sin acceso a red"
            )
            lineas.append("")
            if f.get("codigo"):
                lineas.append("```python")
                lineas.append(str(f["codigo"]).rstrip())
                lineas.append("```")
            else:
                lineas.append("_Sin código registrado para esta función._")
            lineas.append("")

    if opts["contratos"]:
        lineas.extend(
            [
                "## 5. Contratos JSON del Planner",
                "",
                "_Anexo técnico secundario: especificaciones y contratos formales del Planner para auditoría de oráculos._",
                "",
            ]
        )
        for f in datos["funciones"]:
            contrato = f.get("contrato") or {}
            casos_plan = _resumen_casos_planner(contrato)
            crit_txt = (
                "Sí (crítica, evaluada con mutation testing)"
                if f["critical"]
                else "No (función estándar)"
            )
            lineas.append(f"### {f['funcion']} ({f['modulo']})")
            lineas.append("")
            lineas.append(
                f"- **Diseñado por:** Planner (QAgent) mediante análisis estático AST · "
                f"**Criticidad:** {crit_txt}"
            )
            lineas.append(
                f"- **Casos planificados:** {len(casos_plan)} casos deducidos formalmente"
            )
            lineas.append("")
            if f.get("contrato") is not None:
                lineas.append("```json")
                lineas.append(json.dumps(f["contrato"], indent=2, ensure_ascii=False))
                lineas.append("```")
            else:
                lineas.append("_Sin contrato registrado para esta función._")
            lineas.append("")

    return sanitizar_secretos("\n".join(lineas), claves)


def construir_json_informe(
    datos: dict[str, Any],
    opciones: Mapping[str, Any] | None = None,
    claves: Claves | None = None,
) -> str:
    """Construye el archivo `results_<run_id>.json` con las cifras de `results.json`."""
    opts = normalizar_opciones(opciones)
    base = copy.deepcopy(datos["results"])
    base["specs"] = copy.deepcopy(datos["specs"])
    base["costo_por_agente"] = copy.deepcopy(datos["costo_por_agente"])
    base["metricas"] = copy.deepcopy(datos["metricas"])
    base["salud_proyecto"] = _salud_proyecto(datos)
    base["agentes"] = {
        "modelos": copy.deepcopy(datos["modelos"]),
        "costo_por_agente": copy.deepcopy(datos["costo_por_agente"]),
        "roles": {
            "planner": "Analiza el AST del código, firmas, docstrings y dependencias para deducir casos de prueba formales.",
            "generator": "Escribe las suites de pruebas pytest herméticas a partir de los contratos del Planner.",
            "reviewer": "Ejecuta las pruebas en sandbox Docker, audita Assertion Laundering y emite veredictos de calidad.",
        },
    }

    if opts["detalle"]:
        base["ejecucion"] = _json_ejecucion(datos, opts["trazas"])
        detalles_fn = []
        for fn in datos["funciones"]:
            item: dict[str, Any] = {
                "modulo": fn["modulo"],
                "funcion": fn["funcion"],
                "estado": fn["estado"],
            }
            if opts["trazas"]:
                item["traza"] = fn.get("traza")
            if opts["codigo"]:
                item["codigo"] = fn.get("codigo")
            if opts["contratos"]:
                item["contrato"] = fn.get("contrato")

            contrato_fn = fn.get("contrato") or {}
            casos_plan = _resumen_casos_planner(contrato_fn)
            tok_ag = fn.get("tokens_por_agente") or {}
            item["planner"] = {
                "firma": fn.get("firma") or contrato_fn.get("firma") or fn["funcion"],
                "critical": bool(fn.get("critical")),
                "total_casos_planificados": len(casos_plan),
                "casos_planificados": casos_plan,
                "llama_a": contrato_fn.get("llama_a", []),
                "tokens": tok_ag.get("planner", {}),
            }
            item["generator"] = {
                "archivo_test": f"tests/test_{fn['funcion']}.py",
                "iteraciones": fn.get("iteraciones", 1),
                "aislamiento": "sandbox_docker_sin_red",
                "codigo": fn.get("codigo") if opts["codigo"] else None,
                "tokens": tok_ag.get("generator", {}),
            }
            item["reviewer"] = {
                "veredicto": fn.get("estado"),
                "laundering_detectado": bool(fn.get("laundering_detectado")),
                "cobertura_lineas": fn.get("cobertura_lineas"),
                "cobertura_ramas": fn.get("cobertura_ramas"),
                "intentos": fn.get("intentos", []),
                "tokens": tok_ag.get("reviewer", {}),
            }
            ejecucion_fn = fn.get("ejecucion") or {}
            casos_fallidos = [
                {
                    "nombre": c.get("nombre"),
                    "resultado": c.get("resultado"),
                    "archivo": c.get("archivo"),
                    "linea": c.get("linea"),
                    "esperado": c.get("esperado"),
                    "obtenido": c.get("obtenido"),
                    "mensaje": c.get("mensaje"),
                }
                for c in ejecucion_fn.get("casos", [])
                if c.get("resultado") in ("fallo", "error")
            ]
            item["errores"] = {
                "hay_incidente": not fn.get("verde", True) or bool(fn.get("traza")),
                "estado": fn.get("estado"),
                "motivo_fallo": fn.get("motivo_fallo"),
                "casos_fallidos": casos_fallidos,
                "traza": fn.get("traza") if opts["trazas"] else None,
            }
            ubicacion_fallo = None
            if not fn.get("verde", True):
                for c in ejecucion_fn.get("casos", []):
                    if c.get("archivo"):
                        ubicacion_fallo = f"{c['archivo']}:{c.get('linea')}"
                        break
                if not ubicacion_fallo:
                    ubicacion_fallo = f"{fn['modulo']}::{fn['funcion']}"
            motivo_fallo = fn.get("motivo_fallo") or (
                "Assertion Laundering detectado"
                if fn.get("laundering_detectado")
                else (
                    "Defecto confirmado en código"
                    if fn.get("estado") == "bug_detectado"
                    else (
                        "Fallo detectado durante la validación"
                        if not fn.get("verde", True)
                        else None
                    )
                )
            )
            item["diagnostico"] = {
                "aprobada": bool(fn.get("verde", True)),
                "estado": fn.get("estado"),
                "motivo_fallo": motivo_fallo,
                "ubicacion_fallo": ubicacion_fallo,
            }
            detalles_fn.append(item)
        base["detalle_funciones"] = detalles_fn
    else:
        base["objetivos"] = []

    limpio = _sanitizar_estructura(base, claves)
    texto = json.dumps(limpio, indent=2, ensure_ascii=False)
    return sanitizar_secretos(texto, claves)


def construir_html_informe(
    datos: dict[str, Any],
    opciones: Mapping[str, Any] | None = None,
    claves: Claves | None = None,
) -> str:
    """Construye un informe HTML interactivo con pestañas, gráficas y estadísticas."""
    import html as html_mod

    opts = normalizar_opciones(opciones)

    def esc(val: Any) -> str:
        return html_mod.escape(sanitizar_secretos(str(val or ""), claves))

    run_id = esc(datos["run_id"])
    proyecto = esc(datos["proyecto"])
    rama = esc(datos.get("rama") or "sin repositorio Git")
    fecha = esc(datos["fecha"])
    perfil = esc(datos["perfil"])
    total_fn = int(datos["total_funciones"])
    criticas = int(datos["criticas"])
    specs_txt = esc(datos["specs"]["texto"])
    metricas = datos["metricas"]
    cumple_count = sum(1 for m in metricas if m["cumple"])

    filas_metricas = []
    for m in metricas:
        pill = (
            '<span class="pill pass">✓ Cumple</span>'
            if m["cumple"]
            else '<span class="pill fail">✗ No cumple</span>'
        )
        filas_metricas.append(
            f"<tr><td><b>{esc(m['nombre'])}</b></td><td>{esc(m['resultado'])}</td>"
            f"<td>{esc(m['meta'])}</td><td>{pill}</td></tr>"
        )

    salud = _salud_proyecto(datos)
    filas_puntos = []
    for inc in salud["incidentes"]:
        esp_obt = (
            f"Esperado: <code>{esc(inc['esperado'])}</code> | Obtenido: <code>{esc(inc['obtenido'])}</code>"
            if inc["esperado"] is not None and inc["obtenido"] is not None
            else "—"
        )
        accion_txt = (
            f"<br><small style='color:#38bdf8'><b>Acción sugerida:</b> {esc(inc['accion_sugerida'])}</small>"
            if inc.get("accion_sugerida")
            else ""
        )
        filas_puntos.append(
            f"<tr><td><b>{esc(inc['funcion'])}</b></td>"
            f"<td><code>{esc(inc['ubicacion'])}</code></td>"
            f"<td>{esc(inc['causa'])}{accion_txt}</td>"
            f"<td><small>{esp_obt}</small></td></tr>"
        )
    tabla_puntos_html = (
        f"<h3 style='margin:16px 0 6px 0;font-size:13.5px;color:#cbd5e1'>Puntos de atención que requieren corrección en el código</h3>"
        f"<table><thead><tr><th>Función</th><th>Ubicación (archivo:línea)</th><th>Causa del fallo y sugerencia</th><th>Esperado vs Obtenido</th></tr></thead>"
        f"<tbody>{''.join(filas_puntos)}</tbody></table>"
        if filas_puntos
        else ""
    )

    fortalezas_items = "".join(
        f"<li style='margin-bottom:6px'><b>✅</b> {esc(f)}</li>"
        for f in salud["fortalezas"]
    )
    deficiencias_items = "".join(
        f"<li style='margin-bottom:6px'><b>⚠️</b> {esc(d)}</li>"
        for d in salud["deficiencias"]
    )
    recomendaciones_items = "".join(
        f"<li style='margin-bottom:6px'><b>👉</b> {esc(r)}</li>"
        for r in salud["recomendaciones"]
    )
    color_score = (
        "#10b981"
        if salud["indice_salud"] >= 75
        else ("#f59e0b" if salud["indice_salud"] >= 50 else "#ef4444")
    )

    salud_html = (
        f"<div style='background:#111c33;border:1px solid #334155;border-left:4px solid #3b82f6;border-radius:10px;padding:18px;margin:18px 0'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:12px'>"
        f"<div>"
        f"<h3 style='margin:0 0 4px 0;font-size:16px;color:#93c5fd'>🏥 Estado de Salud del Proyecto</h3>"
        f"<p style='margin:0;font-size:13px;color:#94a3b8'>Evaluación técnica para desarrolladores y auditoría de calidad</p>"
        f"</div>"
        f"<div style='text-align:right'>"
        f"<div style='font-size:24px;font-weight:800;color:{color_score}'>{salud['indice_salud']}/100</div>"
        f"<small style='color:#cbd5e1;font-weight:600'>{esc(salud['nivel_madurez'])}</small>"
        f"</div>"
        f"</div>"
        f"<p style='margin:0 0 12px 0;font-size:13px;line-height:1.5'>{esc(salud['diagnostico'])}</p>"
        f"<div style='display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px'>"
        f"<span class='pill pass'>✓ {salud['aprobadas']} aprobadas ({salud['pct_aprobadas']:.1f}%)</span>"
        f"<span class='pill fail'>🐛 {salud['bugs']} defectos en código</span>"
        f"<span class='pill fail'>🛡️ {salud['laundering']} laundering bloqueado</span>"
        f"<span class='pill' style='color:#f59e0b;font-weight:700'>⏳ {salud['estancadas']} estancadas</span>"
        f"</div>"
        f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px;margin-top:14px'>"
        f"<div style='background:#0d1527;border:1px solid #1e293b;border-radius:8px;padding:12px'>"
        f"<h4 style='margin:0 0 8px 0;font-size:13px;color:#34d399'>🛡️ Fortalezas del Proyecto</h4>"
        f"<ul style='margin:0;padding-left:16px;font-size:12.5px;color:#cbd5e1;line-height:1.45'>{fortalezas_items}</ul>"
        f"</div>"
        f"<div style='background:#0d1527;border:1px solid #1e293b;border-radius:8px;padding:12px'>"
        f"<h4 style='margin:0 0 8px 0;font-size:13px;color:#f87171'>⚠️ Deficiencias Detectadas</h4>"
        f"<ul style='margin:0;padding-left:16px;font-size:12.5px;color:#cbd5e1;line-height:1.45'>{deficiencias_items}</ul>"
        f"</div>"
        f"<div style='background:#0d1527;border:1px solid #1e293b;border-radius:8px;padding:12px'>"
        f"<h4 style='margin:0 0 8px 0;font-size:13px;color:#38bdf8'>🚀 Plan de Mejora Accionable</h4>"
        f"<ul style='margin:0;padding-left:16px;font-size:12.5px;color:#cbd5e1;line-height:1.45'>{recomendaciones_items}</ul>"
        f"</div>"
        f"</div>"
        f"{tabla_puntos_html}"
        f"</div>"
    )

    tarjetas_fn = []
    for f in datos["funciones"]:
        est = esc(ETIQUETAS_ESTADO.get(str(f.get("estado", "")), f.get("estado", "")))
        ms_lbl = (
            "N/A"
            if not f["critical"]
            else (
                "Pendiente"
                if f["mutation_score"] is None
                else f"{f['mutation_score']:g}%"
            )
        )
        contrato = f.get("contrato") or {}
        casos_plan = _resumen_casos_planner(contrato)
        firma = (
            f.get("firma")
            or contrato.get("firma")
            or f.get("manejador")
            or f["funcion"]
        )
        casos_plan_txt = "".join(
            f"<li><b>[{esc(cp['id'])}]</b> {esc(cp['descripcion'])}"
            + (
                f" · Entrada: <code>{esc(cp['entrada'])}</code>"
                if cp.get("entrada") is not None
                else ""
            )
            + (
                f" · Esperado: <code>{esc(cp['esperado'])}</code>"
                if cp.get("esperado") is not None
                else ""
            )
            + (
                f" · Excepción: <code>{esc(cp['excepcion'])}</code>"
                if cp.get("excepcion")
                else ""
            )
            + "</li>"
            for cp in casos_plan
        )
        casos_plan_html = (
            f"<ul>{casos_plan_txt}</ul>"
            if casos_plan_txt
            else "<p><i>Sin casos planificados.</i></p>"
        )

        intentos_items = []
        for it in f.get("intentos") or []:
            dec = _ETIQUETA_DECISION.get(str(it.get("decision")), it.get("decision"))
            fb = it.get("feedback")
            fb_txt = f" — <i>{esc(fb)}</i>" if fb else ""
            intentos_items.append(
                f"<li>Intento {it.get('intento')}: {esc(dec)}{fb_txt}</li>"
            )
        intentos_html = (
            f"<ul>{''.join(intentos_items)}</ul>"
            if intentos_items
            else "<p><i>1 intento registrado.</i></p>"
        )

        laund_txt = (
            "<span class='pill fail'>Laundering detectado</span>"
            if f.get("laundering_detectado")
            else "<span class='pill pass'>Aserciones estrictas</span>"
        )
        llama_a = contrato.get("llama_a")
        llama_html = (
            f"<p><small><b>Dependencias simuladas:</b> {', '.join(f'<code>{esc(m)}</code>' for m in llama_a)}</small></p>"
            if llama_a
            else ""
        )

        tarjetas_fn.append(
            f"<div class='fn-card'>"
            f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:8px'>"
            f"<b>{esc(f['funcion'])}</b> <span>({esc(f['modulo'])})</span> — <span class='badge'>{est}</span>"
            f"</div>"
            f"<small>Intentos: {f['iteraciones']}/3 · Cob. líneas: {_fmt_pct(f['cobertura_lineas'])} · "
            f"Cob. ramas: {_fmt_pct(f['cobertura_ramas'])} · Mutation Score: {esc(ms_lbl)} · "
            f"Tokens: {f['tokens']}</small>"
            f"<div class='agent-grid'>"
            f"<div class='agent-box'><h4>📋 Planner (Análisis AST)</h4>"
            f"<p><small><b>Firma:</b> <code>{esc(firma)}</code> | <b>Criticidad:</b> {'Crítica' if f['critical'] else 'Estándar'}</small></p>"
            f"{llama_html}"
            f"<details><summary>Casos planificados ({len(casos_plan)})</summary>{casos_plan_html}</details>"
            f"</div>"
            f"<div class='agent-box'><h4>⚙️ Generator (Suite pytest)</h4>"
            f"<p><small><b>Archivo:</b> <code>tests/test_{esc(f['funcion'])}.py</code></small></p>"
            f"<p><small><b>Iteraciones:</b> {f['iteraciones']}/3 | <b>Aislamiento:</b> Sandbox Docker hermético</small></p>"
            f"</div>"
            f"<div class='agent-box'><h4>🛡️ Reviewer & Ejecutor</h4>"
            f"<p><small><b>Veredicto:</b> {est} | <b>Laundering:</b> {laund_txt}</small></p>"
            f"<details><summary>Historial de intentos y diagnósticos</summary>{intentos_html}</details>"
            f"</div>"
            f"</div>"
            f"</div>"
        )

    tarjetas_inc = []
    incidentes = [f for f in datos["funciones"] if not f["verde"] or f.get("traza")]
    if not incidentes:
        tarjetas_inc.append(
            "<p>No se registraron incidentes ni trazas de fallo en esta corrida.</p>"
        )
    else:
        for f in incidentes:
            est = esc(
                ETIQUETAS_ESTADO.get(str(f.get("estado", "")), f.get("estado", ""))
            )
            motivo = f.get("motivo_fallo") or "Error detectado durante la validación"
            ejec_f = f.get("ejecucion") or {}
            casos_fallidos = [
                c
                for c in ejec_f.get("casos", [])
                if c.get("resultado") in ("fallo", "error")
            ]
            filas_cf = []
            for cf in casos_fallidos:
                donde = f"{cf['archivo']}:{cf['linea']}" if cf.get("archivo") else "—"
                esp_obt = ""
                if cf.get("esperado") is not None or cf.get("obtenido") is not None:
                    esp_obt = (
                        f" · Esperado: <code>{esc(cf.get('esperado'))}</code> | "
                        f"Obtenido: <code>{esc(cf.get('obtenido'))}</code>"
                    )
                filas_cf.append(
                    f"<li><b>{esc(cf['nombre'])}</b> (en <code>{esc(donde)}</code>){esp_obt}</li>"
                )
            casos_fallidos_html = (
                f"<ul style='margin:6px 0 10px 18px'>{''.join(filas_cf)}</ul>"
                if filas_cf
                else ""
            )

            laund_alerta = (
                "<div style='background:#450a0a;border:1px solid #991b1b;color:#fecdd3;padding:8px 12px;border-radius:6px;margin:8px 0;font-size:12px'>"
                "<b>🛡️ Alerta de integridad:</b> Assertion Laundering detectado "
                "(el Generator intentó debilitar o relajar aserciones para ocultar un fallo)."
                "</div>"
                if f.get("laundering_detectado")
                else ""
            )

            fb_list = "".join(
                f"<li><b>Intento {it.get('intento')}:</b> {esc(it.get('feedback') or 'Sin diagnóstico')}</li>"
                for it in (f.get("intentos") or [])
                if it.get("feedback")
            )
            fb_html = (
                f"<details style='margin:8px 0'><summary style='cursor:pointer;color:#93c5fd;font-size:12px'>"
                f"Diagnósticos del Reviewer por intento ({len(f.get('intentos') or [])})</summary>"
                f"<ul>{fb_list}</ul></details>"
                if fb_list
                else ""
            )
            traza_html = (
                f"<details open style='margin-top:8px'><summary style='cursor:pointer;color:#f87171;font-size:12px'>Traza del error en pytest</summary>"
                f"<pre class='fallo'>{esc(f['traza'])}</pre></details>"
                if f.get("traza")
                else "<p><i>Sin traza registrada.</i></p>"
            )
            tarjetas_inc.append(
                f"<div class='fn-card'>"
                f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:8px'>"
                f"<h3>{esc(f['funcion'])} <span style='font-weight:400;color:#94a3b8'>({esc(f['modulo'])})</span></h3>"
                f"<span class='badge'>{est}</span>"
                f"</div>"
                f"<p style='margin:4px 0;font-size:13px'><b>Parte del código afectada:</b> <code>{esc(f['modulo'])}::{esc(f['funcion'])}</code></p>"
                f"<p style='margin:4px 0;font-size:13px'><b>¿Por qué falló?:</b> {esc(motivo)}</p>"
                f"{laund_alerta}"
                f"{casos_fallidos_html}"
                f"{fb_html}"
                f"{traza_html}"
                f"</div>"
            )

    tarjetas_cod = []
    for f in datos["funciones"]:
        cod = f.get("codigo")
        cod_html = (
            f"<pre><code>{esc(cod)}</code></pre>"
            if cod
            else "<p><i>Sin código registrado.</i></p>"
        )
        tarjetas_cod.append(
            f"<div class='fn-card'><b>tests/test_{esc(f['funcion'])}.py</b> ({esc(f['modulo'])})<br>{cod_html}</div>"
        )

    tarjetas_con = []
    for f in datos["funciones"]:
        con = f.get("contrato")
        con_str = json.dumps(con, indent=2, ensure_ascii=False) if con else None
        con_html = (
            f"<pre><code>{esc(con_str)}</code></pre>"
            if con_str
            else "<p><i>Sin contrato registrado.</i></p>"
        )
        tarjetas_con.append(
            f"<div class='fn-card'><b>{esc(f['funcion'])}</b> ({esc(f['modulo'])})<br>{con_html}</div>"
        )

    por_ag = datos["costo_por_agente"]
    modelos_str = " · ".join(
        f"{NOMBRES_AGENTE.get(ag, ag)}: {esc(datos['modelos'][ag]['modelo'])}"
        for ag in AGENTES
        if ag in datos["modelos"]
    )
    costo_str = " · ".join(
        f"{NOMBRES_AGENTE.get(ag, ag)}: {por_ag[ag]['tokens']} tokens (US$ {(por_ag[ag]['costo_usd'] or 0.0):.4f})"
        for ag in AGENTES
        if ag in por_ag
    )

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Informe Interactivo QAgent — Corrida #{run_id}</title>
<style>
body{{font-family:system-ui,-apple-system,sans-serif;background:#0f172a;color:#f8fafc;margin:0;padding:24px}}
.wrap{{max-width:1100px;margin:0 auto}}
.header{{background:linear-gradient(135deg,#1e293b,#0f172a);border:1px solid #334155;border-radius:14px;padding:24px;margin-bottom:18px}}
.tabs{{display:flex;gap:8px;margin-bottom:18px;flex-wrap:wrap}}
.tab{{padding:10px 18px;border-radius:10px;background:#1e293b;border:1px solid #334155;color:#cbd5e1;cursor:pointer;font-weight:700}}
.tab.active{{background:#2563eb;border-color:#3b82f6;color:#fff}}
.panel{{display:none;background:#1e293b;border:1px solid #334155;border-radius:14px;padding:20px}}
.panel.active{{display:block}}
table{{width:100%;border-collapse:collapse;margin-top:12px}}
th,td{{padding:10px 12px;border-bottom:1px solid #334155;text-align:left}}
.pill.pass{{color:#34d399;font-weight:700}}.pill.fail{{color:#fb7185;font-weight:700}}
.fn-card{{padding:14px;border:1px solid #334155;border-radius:10px;margin-bottom:12px;background:#0f172a}}
.agent-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:10px;margin-top:10px}}
.agent-box{{background:#111c33;border:1px solid #334155;border-radius:8px;padding:10px}}
.agent-box h4{{margin:0 0 6px 0;font-size:13px;color:#93c5fd}}
.agent-box p{{margin:4px 0;font-size:12px}}
.agent-box ul{{margin:4px 0 4px 18px;padding:0;font-size:11.5px}}
.agent-box details summary{{cursor:pointer;color:#60a5fa;font-size:12px;margin-top:4px}}
.caso{{padding:8px 10px;border-left:3px solid #334155;margin:6px 0;background:#111c33;border-radius:6px}}
.caso.paso{{border-color:#34d399}}.caso.fallo{{border-color:#fb7185}}.caso.omitido{{border-color:#94a3b8}}
.caso pre,details pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#020617;border:1px solid #334155;border-radius:6px;padding:8px;font-size:12px}}
.caso pre.fallo,pre.fallo{{color:#fecdd3;background:#450a0a;border:1px solid #991b1b;padding:10px;border-radius:6px;white-space:pre-wrap}}
code{{font-family:ui-monospace,monospace}}
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <h1>Informe Interactivo de Auditoría — Corrida #{run_id}</h1>
    <p>Proyecto: {proyecto} · Rama: {rama} · Fecha: {fecha} · Perfil: {perfil} · Funciones: {total_fn} ({criticas} críticas) · Cumplimiento: {cumple_count}/5</p>
    <p><small>Modelos: {modelos_str} | Costo por agente: {costo_str} | Specs: {specs_txt}</small></p>
  </div>
  <div class="tabs">
    <button class="tab active" onclick="verTab('t1',this)">1. Resumen y KPIs</button>
    <button class="tab" onclick="verTab('t2',this)">2. Detalle por Función</button>
    <button class="tab" onclick="verTab('t3',this)">3. Casos y ejecución</button>
    <button class="tab" onclick="verTab('t4',this)">4. Incidentes y Errores</button>
    <button class="tab" onclick="verTab('t5',this)">5. Suites Generadas (Anexo)</button>
    <button class="tab" onclick="verTab('t6',this)">6. Contratos Planner (Anexo Secundario)</button>
  </div>
  <div id="t1" class="panel active">
    <h2>1. Resumen de las 5 métricas</h2>
    {salud_html}
    <table><thead><tr><th>Métrica</th><th>Resultado</th><th>Meta</th><th>Estado</th></tr></thead>
    <tbody>{"".join(filas_metricas)}</tbody></table>
  </div>
  <div id="t2" class="panel">
    <h2>2. Resultado por función y actividad de agentes</h2>
    {"".join(tarjetas_fn) if opts["detalle"] else "<p>Sección opcional desactivada.</p>"}
  </div>
  <div id="t3" class="panel">
    <h2>3. Casos de prueba y datos de la ejecución</h2>
    {_html_ejecucion(datos, opts["trazas"], esc) if opts["detalle"] else "<p>Sección opcional desactivada.</p>"}
  </div>
  <div id="t4" class="panel">
    <h2>4. Dónde falló el código (Incidentes y Errores)</h2>
    {"".join(tarjetas_inc) if opts["trazas"] else "<p>Sección opcional desactivada.</p>"}
  </div>
  <div id="t5" class="panel">
    <h2>5. Código de las pruebas generadas (Generator — Anexo)</h2>
    {"".join(tarjetas_cod) if opts["codigo"] else "<p>Sección opcional desactivada.</p>"}
  </div>
  <div id="t6" class="panel">
    <h2>6. Contratos JSON del Planner (Anexo Secundario)</h2>
    {"".join(tarjetas_con) if opts["contratos"] else "<p>Sección opcional desactivada.</p>"}
  </div>
</div>
<script>
function verTab(id,btn){{
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(b=>b.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  btn.classList.add('active');
}}
</script>
</body>
</html>"""


def construir_pdf_informe(
    datos: dict[str, Any],
    opciones: Mapping[str, Any] | None = None,
    claves: Claves | None = None,
) -> bytes:
    """Construye un documento PDF-1.4 válido y multipágina sin dependencias externas."""
    opts = normalizar_opciones(opciones)
    bloques = _bloques_pdf(datos, opts, claves)
    return _renderizar_pdf(bloques, run_id=str(datos["run_id"]))


def exportar_informe(
    raiz_proyecto: str | Path,
    run_id: str | None = None,
    formato: str = "pdf",
    opciones: Mapping[str, Any] | None = None,
    carpeta_destino: str | Path | None = None,
    claves: Claves | None = None,
) -> dict[str, Any]:
    """Exporta el informe de la corrida en el formato e ubicación indicados (HU-22).

    Returns:
        dict con `ok`, `run_id`, `formato`, `nombre`, `ruta`, `carpeta` y `opciones`.
    """
    fmt = (formato or "").strip().lower()
    if fmt not in FORMATOS:
        raise FormatoInvalido(
            f"Formato de exportación no válido: {formato!r} (se espera pdf, md, json o html)."
        )

    datos = datos_informe(raiz_proyecto, run_id=run_id, claves=claves)
    run_actual = datos["run_id"]
    opts = normalizar_opciones(opciones)
    nombre = nombre_archivo_informe(run_actual, fmt)

    if carpeta_destino is not None and str(carpeta_destino).strip():
        carpeta = Path(carpeta_destino)
    else:
        carpeta = carpeta_por_defecto(raiz_proyecto, run_actual)

    carpeta.mkdir(parents=True, exist_ok=True)
    ruta_archivo = carpeta / nombre

    if fmt == "md":
        contenido_md = construir_markdown_informe(datos, opts, claves)
        _escribir_bytes_atomico(ruta_archivo, contenido_md.encode("utf-8"))
    elif fmt == "json":
        contenido_json = construir_json_informe(datos, opts, claves)
        _escribir_bytes_atomico(ruta_archivo, contenido_json.encode("utf-8"))
    elif fmt == "html":
        contenido_html = construir_html_informe(datos, opts, claves)
        _escribir_bytes_atomico(ruta_archivo, contenido_html.encode("utf-8"))
    else:
        contenido_pdf = construir_pdf_informe(datos, opts, claves)
        _escribir_bytes_atomico(ruta_archivo, contenido_pdf)

    return {
        "ok": True,
        "run_id": run_actual,
        "formato": fmt,
        "nombre": nombre,
        "ruta": str(ruta_archivo),
        "carpeta": str(carpeta),
        "opciones": opts,
    }


def extraer_texto_pdf(origen: str | Path | bytes) -> str:
    """Extrae el texto legible de un PDF generado por QAgent para verificación y auditoría."""
    datos = (
        origen.read_bytes()
        if isinstance(origen, Path)
        else (Path(origen).read_bytes() if isinstance(origen, str) else bytes(origen))
    )
    texto_raw = datos.decode("latin-1", errors="replace")
    fragmentos: list[str] = []
    for coincidencia in re.finditer(r"\((?:\\.|[^\\()])*\)\s*Tj", texto_raw):
        literal = coincidencia.group(0)
        inicio = literal.find("(")
        fin = literal.rfind(")")
        cuerpo = literal[inicio + 1 : fin]
        fragmentos.append(_decodificar_literal_pdf(cuerpo))
    return "\n".join(fragmentos)


def verificar_archivo_sin_claves(ruta: str | Path) -> list[Hallazgo]:
    """Verifica que un archivo exportado (.pdf, .md o .json) no contenga claves (RN-07)."""
    ruta_path = Path(ruta)
    textos: list[str] = []
    try:
        textos.append(ruta_path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return []
    if ruta_path.suffix.lower() == ".pdf":
        try:
            textos.append(extraer_texto_pdf(ruta_path))
        except OSError:
            pass

    hallazgos: list[Hallazgo] = []
    for texto in textos:
        for num, linea in enumerate(texto.splitlines(), start=1):
            if "base64," in linea:
                continue
            for nombre, patron in PATRONES.items():
                if patron.search(linea):
                    hallazgos.append(Hallazgo(ruta_path.name, num, nombre))
                    break
        if hallazgos:
            break
    return hallazgos


# --- Generación de PDF-1.4 sin dependencias externas ------------------------------


def _fmt_pct(valor: float | None) -> str:
    return "—" if valor is None else f"{valor:.1f}%"


def _normalizar_para_pdf(texto: str) -> str:
    """Convierte símbolos fuera de Windows-1252 a equivalentes legibles en Type1."""
    reemplazos = {
        "≥": ">=",
        "≤": "<=",
        "→": "->",
        "✅": "[OK]",
        "❌": "[NO]",
        "☑️": "[OK]",
        "⚠️": "[!]",
        "♻": "",
        "↻": "",
        "★": "*",
        "—": "-",
        "–": "-",
        "…": "...",
    }
    for orig, dest in reemplazos.items():
        texto = texto.replace(orig, dest)
    return texto


def _escapar_literal_pdf(texto: str) -> str:
    """Codifica una cadena en literal PDF con escapes octales para caracteres no ASCII.

    Al usar escapes octales `\\ddd` (WinAnsiEncoding / cp1252), el archivo PDF es
    100 % ASCII/UTF-8 en disco (revisable directamente por `auditoria.py`) y muestra
    todas las tildes y eñes correctamente en cualquier visor PDF.
    """
    normalizado = _normalizar_para_pdf(texto).replace("\t", "    ")
    datos = normalizado.encode("cp1252", errors="replace")
    partes: list[str] = []
    for byte in datos:
        if byte == 0x5C:  # \
            partes.append("\\\\")
        elif byte == 0x28:  # (
            partes.append("\\(")
        elif byte == 0x29:  # )
            partes.append("\\)")
        elif 32 <= byte <= 126:
            partes.append(chr(byte))
        elif byte >= 128:
            partes.append(f"\\{byte:03o}")
    return "".join(partes)


def _decodificar_literal_pdf(cuerpo: str) -> str:
    """Inversa de `_escapar_literal_pdf` para pruebas y auditoría."""
    salida = bytearray()
    i = 0
    n = len(cuerpo)
    while i < n:
        ch = cuerpo[i]
        if ch == "\\" and i + 1 < n:
            sig = cuerpo[i + 1]
            if sig in "\\()":
                salida.append(ord(sig))
                i += 2
                continue
            if i + 4 <= n and all(c in "01234567" for c in cuerpo[i + 1 : i + 4]):
                salida.append(int(cuerpo[i + 1 : i + 4], 8))
                i += 4
                continue
        salida.append(ord(ch) if ord(ch) < 256 else ord("?"))
        i += 1
    return bytes(salida).decode("cp1252", errors="replace")


def _envolver_linea(texto: str, max_caracteres: int = 92) -> list[str]:
    """Envuelve una línea larga respetando palabras."""
    if len(texto) <= max_caracteres:
        return [texto]
    palabras = texto.split(" ")
    lineas: list[str] = []
    actual = ""
    for palabra in palabras:
        while len(palabra) > max_caracteres:
            if actual:
                lineas.append(actual)
                actual = ""
            lineas.append(palabra[:max_caracteres])
            palabra = palabra[max_caracteres:]
        if not actual:
            actual = palabra
        elif len(actual) + 1 + len(palabra) <= max_caracteres:
            actual = f"{actual} {palabra}"
        else:
            lineas.append(actual)
            actual = palabra
    if actual or not lineas:
        lineas.append(actual)
    return lineas


def _bloques_pdf(
    datos: dict[str, Any],
    opts: dict[str, bool],
    claves: Claves | None = None,
) -> list[dict[str, Any]]:
    """Construye los elementos visuales estructurados e interactivos para maquetar el PDF."""
    bloques: list[dict[str, Any]] = []
    run_id = str(datos["run_id"])
    rama = datos.get("rama") or "sin repositorio Git"

    def limpiar(texto: str) -> str:
        return sanitizar_secretos(str(texto), claves)

    modelos_txt = " | ".join(
        f"{NOMBRES_AGENTE.get(ag, ag)}: {datos['modelos'][ag]['modelo']} "
        f"({datos['modelos'][ag]['proveedor']})"
        for ag in AGENTES
        if ag in datos["modelos"]
    )

    por_ag = datos["costo_por_agente"]
    costo_ag_txt = " | ".join(
        f"{NOMBRES_AGENTE.get(ag, ag)}: {por_ag[ag]['tokens']} tokens "
        f"(US$ {(por_ag[ag]['costo_usd'] or 0.0):.4f})"
        for ag in AGENTES
        if ag in por_ag
    )

    bloques.append(
        {
            "tipo": "banner",
            "seccion": 1,
            "titulo": limpiar(
                f"Informe de auditoría de pruebas unitarias — Corrida #{run_id}"
            ),
            "sub1": limpiar(f"Proyecto: {datos['proyecto']}  |  Rama: {rama}"),
            "sub2": limpiar(
                f"Fecha: {datos['fecha']}  |  Perfil: {datos['perfil']}  |  "
                f"Funciones evaluadas: {datos['total_funciones']} ({datos['criticas']} críticas)"
            ),
        }
    )

    # Tarjetas KPI interactivas (Estadísticas Relevantes)
    m_map = {m["clave"]: m for m in datos["metricas"]}
    pr_val = float(m_map["pass_rate"]["valor"] or 0.0)
    cv_lin = float(m_map["cobertura"]["lineas"] or 0.0)
    cv_ram = float(m_map["cobertura"]["ramas"] or 0.0)
    it_val = float(m_map["iteraciones"]["valor"] or 0.0)
    it_max = float(m_map["iteraciones"]["meta_valor"] or 2.0)
    cs_usd = float(m_map["costo"]["costo_total_usd"] or 0.0)
    cs_tok = int(m_map["costo"]["tokens_total"] or 0)
    ms_val = float(m_map["mutation_score"]["valor"] or 0.0)

    kpis = [
        {
            "titulo": "PASS RATE",
            "valor": f"{pr_val:.1f}%",
            "sub": f"{m_map['pass_rate']['pasaron']}/{m_map['pass_rate']['total']} aprobadas",
            "pct": max(0.0, min(100.0, pr_val)),
            "cumple": bool(m_map["pass_rate"]["cumple"]),
        },
        {
            "titulo": "COB. LINEAS",
            "valor": f"{cv_lin:.1f}%",
            "sub": f"Ramas: {cv_ram:.1f}%",
            "pct": max(0.0, min(100.0, cv_lin)),
            "cumple": bool(m_map["cobertura"]["cumple"]),
        },
        {
            "titulo": "ITERACIONES",
            "valor": f"{it_val:.2f}",
            "sub": f"Meta <= {it_max:g} (max 3)",
            "pct": max(0.0, min(100.0, (1.0 - max(0.0, it_val - 1.0) / 2.0) * 100.0)),
            "cumple": bool(m_map["iteraciones"]["cumple"]),
        },
        {
            "titulo": "COSTO CORRIDA",
            "valor": f"US$ {cs_usd:.4f}",
            "sub": f"{cs_tok} tokens",
            "pct": max(
                12.0,
                min(
                    100.0,
                    (cs_usd / max(0.01, float(m_map["costo"]["meta_valor"] or 1.0)))
                    * 100.0,
                ),
            ),
            "cumple": bool(m_map["costo"]["cumple"]),
        },
        {
            "titulo": "MUTATION SCORE",
            "valor": f"{ms_val:.1f}%"
            if m_map["mutation_score"]["valor"] is not None
            else "N/A",
            "sub": f"{datos['criticas']} criticas (>=60%)",
            "pct": max(0.0, min(100.0, ms_val)),
            "cumple": bool(m_map["mutation_score"]["cumple"]),
        },
    ]
    bloques.append({"tipo": "panel_kpis", "seccion": 1, "kpis": kpis})

    lineas_meta: list[tuple[str, str]] = []
    for i, ln in enumerate(_envolver_linea(limpiar(modelos_txt), 82)):
        lineas_meta.append(("Modelos usados:" if i == 0 else "", ln))
    for i, ln in enumerate(_envolver_linea(limpiar(costo_ag_txt), 82)):
        lineas_meta.append(("Costo por agente:" if i == 0 else "", ln))
    for i, ln in enumerate(_envolver_linea(limpiar(datos["specs"]["texto"]), 82)):
        lineas_meta.append(("Specs:" if i == 0 else "", ln))
    bloques.append({"tipo": "ficha_meta", "seccion": 1, "filas": lineas_meta})

    bloques.append(
        {"tipo": "h2", "seccion": 1, "texto": "1. Resumen de las 5 métricas"}
    )
    bloques.append({"tipo": "tabla_cabecera", "seccion": 1})
    for idx, m in enumerate(datos["metricas"]):
        bloques.append(
            {
                "tipo": "tabla_metrica",
                "seccion": 1,
                "par": idx % 2 == 1,
                "nombre": limpiar(m["nombre"]),
                "resultado": limpiar(m["resultado"]),
                "meta": limpiar(m["meta"]),
                "estado": limpiar(m["estado"]),
                "cumple": bool(m["cumple"]),
            }
        )
    bloques.append(
        {
            "tipo": "nota_agentes",
            "seccion": 1,
            "lineas": _envolver_linea(
                limpiar(
                    f"Desglose de costo por agente: {costo_ag_txt} (Estado: Reportado)"
                ),
                90,
            ),
        }
    )

    salud_pdf = _salud_proyecto(datos)
    bloques.append(
        {
            "tipo": "panel_salud",
            "seccion": 1,
            "indice": salud_pdf["indice_salud"],
            "nivel": limpiar(salud_pdf["nivel_madurez"]),
            "progreso": limpiar(
                f"{salud_pdf['aprobadas']}/{salud_pdf['total']} aprobadas ({salud_pdf['pct_aprobadas']:.1f}%)"
            ),
            "diagnostico": _envolver_linea(limpiar(salud_pdf["diagnostico"]), 88),
            "fortalezas": [
                _envolver_linea(limpiar(f), 82) for f in salud_pdf["fortalezas"][:2]
            ],
            "deficiencias": [
                _envolver_linea(limpiar(d), 82) for d in salud_pdf["deficiencias"][:2]
            ],
            "recomendaciones": [
                _envolver_linea(limpiar(r), 82)
                for r in salud_pdf["recomendaciones"][:2]
            ],
        }
    )

    # Sección de Gráficas y Estadísticas Relevantes (Pestaña 2)
    funciones_graf = []
    for f in datos["funciones"][:6]:
        funciones_graf.append(
            {
                "nombre": limpiar(str(f["funcion"]))[:18],
                "lineas": float(f.get("cobertura_lineas") or 0.0),
                "ramas": float(f.get("cobertura_ramas") or 0.0),
                "ms": float(f.get("mutation_score") or 0.0),
                "tiene_ms": f.get("mutation_score") is not None
                and bool(f.get("critical")),
            }
        )

    conteo_estados = {
        "aprobado": 0,
        "rechazado_laundering": 0,
        "bug_detectado": 0,
        "otros": 0,
    }
    for f in datos["funciones"]:
        est_k = str(f.get("estado", ""))
        if est_k in conteo_estados:
            conteo_estados[est_k] += 1
        else:
            conteo_estados["otros"] += 1

    agentes_graf = []
    total_tok_ag = max(
        1, sum(int(por_ag.get(ag, {}).get("tokens", 0)) for ag in AGENTES)
    )
    for ag in AGENTES:
        if ag in por_ag:
            toks = int(por_ag[ag].get("tokens", 0))
            usd = float(por_ag[ag].get("costo_usd") or 0.0)
            agentes_graf.append(
                {
                    "nombre": NOMBRES_AGENTE.get(ag, ag),
                    "tokens": toks,
                    "usd": usd,
                    "pct": (toks / total_tok_ag) * 100.0,
                }
            )

    cumplidas_n = sum(1 for m in datos["metricas"] if m["cumple"])
    insights = [
        limpiar(
            f"Cumplimiento global: {cumplidas_n}/5 metricas dentro de la meta de la carta "
            f"(Pass Rate: {pr_val:.1f}% vs. meta >= {m_map['pass_rate']['meta_valor']:g}%)."
        ),
        limpiar(
            f"Calidad estructural: cobertura media de {cv_lin:.1f}% en lineas y {cv_ram:.1f}% en ramas; "
            f"Mutation Score promedio de {ms_val:.1f}% en funciones criticas."
        ),
        limpiar(
            f"Auditoria de incidentes: {conteo_estados['aprobado']} aprobadas, "
            f"{conteo_estados['rechazado_laundering']} rechazadas por Laundering, "
            f"{conteo_estados['bug_detectado']} bugs de oraculo y {conteo_estados['otros']} estancadas."
        ),
    ]

    bloques.append(
        {
            "tipo": "panel_graficas",
            "seccion": 2,
            "funciones": funciones_graf,
            "estados": conteo_estados,
            "total_fn": max(1, len(datos["funciones"])),
            "agentes": agentes_graf,
            "insights": insights,
        }
    )

    if opts["detalle"]:
        bloques.append(
            {"tipo": "h2", "seccion": 3, "texto": "2. Resultado por función"}
        )
        for f in datos["funciones"]:
            estado_clave = str(f.get("estado", ""))
            estado_lbl = ETIQUETAS_ESTADO.get(estado_clave, estado_clave)
            ms_lbl = (
                "N/A (no crítica)"
                if not f["critical"]
                else (
                    "Pendiente"
                    if f["mutation_score"] is None
                    else f"{f['mutation_score']:g}%"
                )
            )
            controles_txt = "; ".join(
                f"{c['etiqueta']}: {ETIQUETAS_CONTROL.get(c['estado'], c['estado'])}"
                for c in f.get("controles", [])
            )
            lineas_ctrl = (
                _envolver_linea(limpiar(f"Controles: {controles_txt}"), 88)
                if controles_txt
                else []
            )
            contrato_fn = f.get("contrato") or {}
            casos_plan = _resumen_casos_planner(contrato_fn)
            laund_lbl = (
                "Laundering DETECTADO"
                if f.get("laundering_detectado")
                else "Sin laundering"
            )
            lineas_ctrl.append(
                f"Planner: {len(casos_plan)} casos planificados | "
                f"Generator: {f['iteraciones']}/3 intentos | Reviewer: {laund_lbl}"
            )
            bloques.append(
                {
                    "tipo": "tarjeta_funcion",
                    "seccion": 3,
                    "titulo": limpiar(f"{f['funcion']} ({f['modulo']})"),
                    "estado_clave": estado_clave,
                    "estado_lbl": limpiar(estado_lbl),
                    "cob_lineas": float(f.get("cobertura_lineas") or 0.0),
                    "cob_ramas": float(f.get("cobertura_ramas") or 0.0),
                    "metricas": limpiar(
                        f"Intentos: {f['iteraciones']}/3  |  "
                        f"Cob. líneas: {_fmt_pct(f['cobertura_lineas'])}  |  "
                        f"Cob. ramas: {_fmt_pct(f['cobertura_ramas'])}  |  "
                        f"Mutation Score: {ms_lbl}  |  Tokens: {f['tokens']}"
                    ),
                    "controles": lineas_ctrl,
                }
            )
        bloques.extend(_bloques_ejecucion(datos, opts["trazas"], limpiar))

    if opts["trazas"]:
        bloques.append(
            {
                "tipo": "h2",
                "seccion": 4,
                "texto": "3. Trazas del Reviewer de los incidentes",
            }
        )
        incidentes = [f for f in datos["funciones"] if not f["verde"] or f.get("traza")]
        if not incidentes:
            bloques.append(
                {
                    "tipo": "texto",
                    "seccion": 4,
                    "texto": "No se registraron incidentes ni trazas de fallo.",
                }
            )
        for f in incidentes:
            estado_clave = str(f.get("estado", ""))
            estado_lbl = ETIQUETAS_ESTADO.get(estado_clave, estado_clave)
            bloques.append(
                {
                    "tipo": "encabezado_bloque",
                    "seccion": 4,
                    "titulo": limpiar(f"{f['funcion']} ({f['modulo']})"),
                    "etiqueta": limpiar(estado_lbl),
                    "acento": "incidente",
                }
            )
            diag_lines = []
            if f.get("motivo_fallo"):
                diag_lines.append(f"Causa: {f['motivo_fallo']}")
            for it in f.get("intentos") or []:
                fb = it.get("feedback")
                if fb:
                    diag_lines.append(f"Intento {it.get('intento')}: {fb}")
            if f.get("laundering_detectado"):
                diag_lines.append(
                    "Alerta: Assertion Laundering detectado por el Reviewer."
                )

            traza_txt = limpiar(
                f.get("traza") or "Sin traza registrada en este incidente."
            )
            lineas_traza: list[str] = []
            for d in diag_lines:
                lineas_traza.extend(_envolver_linea(limpiar(d), 84))
            for sub in traza_txt.splitlines() or [""]:
                lineas_traza.extend(_envolver_linea(sub, 84))
            for idx_l, ln in enumerate(lineas_traza):
                bloques.append(
                    {
                        "tipo": "linea_codigo",
                        "seccion": 4,
                        "texto": ln,
                        "acento": "incidente",
                        "primera": idx_l == 0,
                        "ultima": idx_l == len(lineas_traza) - 1,
                    }
                )
            bloques.append({"tipo": "espacio", "seccion": 4, "alto": 6})

    if opts["codigo"]:
        bloques.append(
            {"tipo": "h2", "seccion": 5, "texto": "4. Código de las pruebas generadas"}
        )
        for f in datos["funciones"]:
            bloques.append(
                {
                    "tipo": "encabezado_bloque",
                    "seccion": 5,
                    "titulo": limpiar(f"tests/test_{f['funcion']}.py ({f['modulo']})"),
                    "etiqueta": "PYTEST SUITE",
                    "acento": "codigo",
                }
            )
            cod_txt = limpiar(
                (f.get("codigo") or "Sin código registrado para esta función.").rstrip()
            )
            lineas_cod: list[str] = []
            for sub in cod_txt.splitlines() or [""]:
                lineas_cod.extend(_envolver_linea(sub, 84))
            for idx_l, ln in enumerate(lineas_cod):
                bloques.append(
                    {
                        "tipo": "linea_codigo",
                        "seccion": 5,
                        "texto": ln,
                        "acento": "codigo",
                        "primera": idx_l == 0,
                        "ultima": idx_l == len(lineas_cod) - 1,
                    }
                )
            bloques.append({"tipo": "espacio", "seccion": 5, "alto": 6})

    if opts["contratos"]:
        bloques.append(
            {"tipo": "h2", "seccion": 5, "texto": "5. Contratos JSON del Planner"}
        )
        for f in datos["funciones"]:
            bloques.append(
                {
                    "tipo": "encabezado_bloque",
                    "seccion": 5,
                    "titulo": limpiar(f"{f['funcion']} ({f['modulo']})"),
                    "etiqueta": "PLANNER CONTRACT JSON",
                    "acento": "contrato",
                }
            )
            contrato_txt = (
                limpiar(json.dumps(f["contrato"], indent=2, ensure_ascii=False))
                if f.get("contrato") is not None
                else "Sin contrato registrado para esta función."
            )
            lineas_con: list[str] = []
            for sub in contrato_txt.splitlines() or [""]:
                lineas_con.extend(_envolver_linea(sub, 84))
            for idx_l, ln in enumerate(lineas_con):
                bloques.append(
                    {
                        "tipo": "linea_codigo",
                        "seccion": 5,
                        "texto": ln,
                        "acento": "contrato",
                        "primera": idx_l == 0,
                        "ultima": idx_l == len(lineas_con) - 1,
                    }
                )
            bloques.append({"tipo": "espacio", "seccion": 5, "alto": 6})

    return bloques


def _colores_estado_pdf(estado_clave: str) -> tuple[str, str, str]:
    """Devuelve `(rgb_acento, rgb_fondo_badge, rgb_texto_badge)` según el estado."""
    if estado_clave == "aprobado":
        return ("0.06 0.68 0.46", "0.84 0.96 0.89", "0.04 0.42 0.24")
    if estado_clave == "rechazado_laundering":
        return ("0.88 0.18 0.30", "0.99 0.88 0.90", "0.68 0.10 0.20")
    if estado_clave == "bug_detectado":
        return ("0.72 0.16 0.82", "0.96 0.89 0.99", "0.48 0.08 0.58")
    return ("0.85 0.48 0.04", "0.99 0.94 0.83", "0.58 0.30 0.04")


_SECCIONES_PDF = (
    (1, "1. Resumen y KPIs"),
    (2, "2. Graficas y Estadisticas"),
    (3, "3. Detalle por Funcion"),
    (4, "4. Incidentes y Trazas"),
    (5, "5. Codigo y Contratos"),
)


def _renderizar_pdf(bloques: list[dict[str, Any]], run_id: str) -> bytes:
    """Maqueta los bloques con diseño formal de documento, gráficas y marcadores en PDF-1.4."""
    paginas: list[list[str]] = []
    secciones_pagina: list[int] = []
    pagina_inicio_seccion: dict[int, int] = {1: 0}
    comandos: list[str] = []
    y = 788.0
    margen_inf = 48.0
    seccion_actual = 1

    def nueva_pagina(sec: int | None = None) -> None:
        nonlocal comandos, y, seccion_actual
        if sec is not None:
            seccion_actual = sec
        if comandos:
            paginas.append(comandos)
            secciones_pagina.append(seccion_actual)
        esc_id = _escapar_literal_pdf(run_id)
        comandos = [
            # Barra superior ejecutiva con acento esmeralda
            "0.06 0.09 0.16 rg 36 804 523 22 re f",
            "0.06 0.73 0.51 rg 36 804 4 22 re f",
            f"BT /F2 8.5 Tf 1 1 1 rg 48 812 Td (QAgent v{__version__}  |  Informe de Auditoria  |  Corrida #{esc_id}) Tj ET",
            "BT /F1 7.8 Tf 0.70 0.78 0.90 rg 425 812 Td (Verificacion RN-07 Activa) Tj ET",
        ]
        y = 788.0

    def asegurar_espacio(alto_necesario: float, sec: int | None = None) -> None:
        nonlocal y, seccion_actual
        if sec is not None:
            seccion_actual = sec
            if sec not in pagina_inicio_seccion:
                pagina_inicio_seccion[sec] = len(paginas)
        if y - alto_necesario < margen_inf:
            nueva_pagina(seccion_actual)
            if sec is not None and pagina_inicio_seccion.get(sec) == len(paginas) - 1:
                pagina_inicio_seccion[sec] = len(paginas)

    nueva_pagina(1)

    for b in bloques:
        tipo = b["tipo"]
        sec_b = int(b.get("seccion", seccion_actual))
        if sec_b != seccion_actual and sec_b not in pagina_inicio_seccion:
            pagina_inicio_seccion[sec_b] = len(paginas)
        seccion_actual = sec_b

        if tipo == "espacio":
            y -= float(b.get("alto", 8))
            continue

        if tipo == "banner":
            alto_b = 62.0
            asegurar_espacio(alto_b + 6, sec_b)
            top = y
            base = top - alto_b
            comandos.append(f"0.08 0.12 0.22 rg 36 {base:.1f} 523 {alto_b:.1f} re f")
            comandos.append(f"0.23 0.51 0.96 rg 36 {top - 3:.1f} 523 3 re f")
            comandos.append(f"0.06 0.45 0.33 rg 48 {top - 18:.1f} 295 11 re f")
            comandos.append(
                f"BT /F2 7.2 Tf 0.85 0.99 0.92 rg 54 {top - 15:.1f} Td "
                "(INFORME DE AUDITORIA DE PRUEBAS UNITARIAS) Tj ET"
            )
            comandos.append(
                f"BT /F2 12.5 Tf 1 1 1 rg 48 {top - 33:.1f} Td "
                f"({_escapar_literal_pdf(b['titulo'])}) Tj ET"
            )
            comandos.append(
                f"BT /F1 8.2 Tf 0.80 0.86 0.95 rg 48 {top - 46:.1f} Td "
                f"({_escapar_literal_pdf(b['sub1'])}) Tj ET"
            )
            comandos.append(
                f"BT /F1 8.2 Tf 0.72 0.80 0.92 rg 48 {top - 56:.1f} Td "
                f"({_escapar_literal_pdf(b['sub2'])}) Tj ET"
            )
            y = base - 7.0
            continue

        if tipo == "panel_kpis":
            alto_k = 50.0
            asegurar_espacio(alto_k + 6, sec_b)
            top = y
            base = top - alto_k
            ancho_card = 100.0
            gap_card = 5.75
            for idx_k, kpi in enumerate(b["kpis"]):
                cx = 36.0 + idx_k * (ancho_card + gap_card)
                acento_c = "0.06 0.68 0.46" if kpi["cumple"] else "0.88 0.18 0.30"
                bg_pill = "0.84 0.96 0.89" if kpi["cumple"] else "0.99 0.88 0.90"
                fg_pill = "0.04 0.42 0.24" if kpi["cumple"] else "0.68 0.10 0.20"
                lbl_pill = "OK" if kpi["cumple"] else "META"
                comandos.append(
                    f"0.98 0.99 1.00 rg {cx:.1f} {base:.1f} {ancho_card:.1f} {alto_k:.1f} re f"
                )
                comandos.append(
                    f"0.83 0.87 0.93 RG 0.6 w {cx:.1f} {base:.1f} {ancho_card:.1f} {alto_k:.1f} re S"
                )
                comandos.append(
                    f"{acento_c} rg {cx:.1f} {top - 3:.1f} {ancho_card:.1f} 3 re f"
                )
                comandos.append(
                    f"BT /F2 6.8 Tf 0.35 0.42 0.52 rg {cx + 6:.1f} {top - 12:.1f} Td "
                    f"({_escapar_literal_pdf(kpi['titulo'])}) Tj ET"
                )
                comandos.append(f"{bg_pill} rg {cx + 72:.1f} {top - 14:.1f} 23 9 re f")
                comandos.append(
                    f"BT /F2 6 Tf {fg_pill} rg {cx + 75:.1f} {top - 11.5:.1f} Td ({lbl_pill}) Tj ET"
                )
                comandos.append(
                    f"BT /F2 11 Tf 0.08 0.12 0.22 rg {cx + 6:.1f} {top - 26:.1f} Td "
                    f"({_escapar_literal_pdf(kpi['valor'])}) Tj ET"
                )
                comandos.append(
                    f"BT /F1 6.8 Tf 0.38 0.44 0.54 rg {cx + 6:.1f} {top - 36:.1f} Td "
                    f"({_escapar_literal_pdf(kpi['sub'])}) Tj ET"
                )
                # Barra de progreso del KPI
                ancho_barra = 88.0
                relleno = max(
                    3.0, min(ancho_barra, (float(kpi["pct"]) / 100.0) * ancho_barra)
                )
                comandos.append(
                    f"0.88 0.91 0.96 rg {cx + 6:.1f} {base + 5:.1f} {ancho_barra:.1f} 4 re f"
                )
                comandos.append(
                    f"{acento_c} rg {cx + 6:.1f} {base + 5:.1f} {relleno:.1f} 4 re f"
                )
            y = base - 7.0
            continue

        if tipo == "ficha_meta":
            filas = b["filas"]
            alto_f = 10.0 + len(filas) * 11.5
            asegurar_espacio(alto_f + 6, sec_b)
            top = y
            base = top - alto_f
            comandos.append(f"0.96 0.97 0.99 rg 36 {base:.1f} 523 {alto_f:.1f} re f")
            comandos.append(
                f"0.82 0.86 0.92 RG 0.6 w 36 {base:.1f} 523 {alto_f:.1f} re S"
            )
            comandos.append(f"0.23 0.51 0.96 rg 36 {base:.1f} 3.5 {alto_f:.1f} re f")
            cy = top - 12.0
            for etq, valor in filas:
                if etq:
                    comandos.append(
                        f"BT /F2 8 Tf 0.12 0.18 0.28 rg 46 {cy:.1f} Td "
                        f"({_escapar_literal_pdf(etq)}) Tj ET"
                    )
                comandos.append(
                    f"BT /F1 8 Tf 0.20 0.25 0.34 rg 128 {cy:.1f} Td "
                    f"({_escapar_literal_pdf(valor)}) Tj ET"
                )
                cy -= 11.5
            y = base - 7.0
            continue

        if tipo == "h2":
            asegurar_espacio(34.0, sec_b)
            y -= 3.0
            base = y - 17.0
            comandos.append(f"0.92 0.95 0.99 rg 36 {base:.1f} 523 17 re f")
            comandos.append(f"0.15 0.39 0.92 rg 36 {base:.1f} 4 17 re f")
            comandos.append(
                f"BT /F2 10 Tf 0.08 0.14 0.26 rg 46 {base + 4.8:.1f} Td "
                f"({_escapar_literal_pdf(b['texto'])}) Tj ET"
            )
            y = base - 5.0
            continue

        if tipo == "tabla_cabecera":
            asegurar_espacio(36.0, sec_b)
            base = y - 16.0
            comandos.append(f"0.11 0.16 0.26 rg 36 {base:.1f} 523 16 re f")
            comandos.append(
                f"BT /F2 8 Tf 1 1 1 rg 44 {base + 4.8:.1f} Td (METRICA DE AUDITORIA) Tj ET"
            )
            comandos.append(
                f"BT /F2 8 Tf 1 1 1 rg 225 {base + 4.8:.1f} Td (RESULTADO OBTENIDO) Tj ET"
            )
            comandos.append(
                f"BT /F2 8 Tf 1 1 1 rg 370 {base + 4.8:.1f} Td (META) Tj ET"
            )
            comandos.append(
                f"BT /F2 8 Tf 1 1 1 rg 478 {base + 4.8:.1f} Td (ESTADO) Tj ET"
            )
            y = base
            continue

        if tipo == "tabla_metrica":
            asegurar_espacio(20.0, sec_b)
            base = y - 18.0
            bg = "0.96 0.98 1.00" if b["par"] else "1 1 1"
            comandos.append(f"{bg} rg 36 {base:.1f} 523 18 re f")
            comandos.append(f"0.85 0.89 0.94 RG 0.5 w 36 {base:.1f} 523 18 re S")
            comandos.append(
                f"BT /F2 8.2 Tf 0.10 0.15 0.24 rg 44 {base + 5.8:.1f} Td "
                f"({_escapar_literal_pdf(b['nombre'])}) Tj ET"
            )
            comandos.append(
                f"BT /F1 8.2 Tf 0.14 0.19 0.28 rg 225 {base + 5.8:.1f} Td "
                f"({_escapar_literal_pdf(b['resultado'])}) Tj ET"
            )
            comandos.append(
                f"BT /F1 8.2 Tf 0.28 0.34 0.44 rg 370 {base + 5.8:.1f} Td "
                f"({_escapar_literal_pdf(b['meta'])}) Tj ET"
            )
            if b["cumple"]:
                pill_bg, pill_fg = "0.84 0.96 0.89", "0.04 0.42 0.24"
            else:
                pill_bg, pill_fg = "0.99 0.88 0.90", "0.68 0.10 0.20"
            comandos.append(f"{pill_bg} rg 468 {base + 3.0:.1f} 82 12 re f")
            comandos.append(
                f"BT /F2 7.5 Tf {pill_fg} rg 476 {base + 6.2:.1f} Td "
                f"({_escapar_literal_pdf(b['estado'])}) Tj ET"
            )
            y = base
            continue

        if tipo == "nota_agentes":
            lineas = b["lineas"]
            alto_n = 7.0 + len(lineas) * 11.0
            asegurar_espacio(alto_n + 5, sec_b)
            base = y - alto_n
            comandos.append(f"0.94 0.96 0.99 rg 36 {base:.1f} 523 {alto_n:.1f} re f")
            comandos.append(
                f"0.85 0.89 0.94 RG 0.5 w 36 {base:.1f} 523 {alto_n:.1f} re S"
            )
            cy = y - 10.5
            for ln in lineas:
                comandos.append(
                    f"BT /F1 7.8 Tf 0.22 0.28 0.38 rg 44 {cy:.1f} Td "
                    f"({_escapar_literal_pdf(ln)}) Tj ET"
                )
                cy -= 11.0
            y = base - 7.0
            continue

        if tipo == "panel_salud":
            filas_f = [ln for f_list in b["fortalezas"] for ln in f_list]
            filas_d = [ln for d_list in b["deficiencias"] for ln in d_list]
            filas_r = [ln for r_list in b["recomendaciones"] for ln in r_list]
            total_items = len(filas_f) + len(filas_d) + len(filas_r)
            alto_s = 28.0 + len(b["diagnostico"]) * 9.5 + total_items * 9.5
            asegurar_espacio(alto_s + 6.0, sec_b)
            top = y
            base = top - alto_s
            comandos.append(f"0.96 0.98 1.00 rg 36 {base:.1f} 523 {alto_s:.1f} re f")
            comandos.append(
                f"0.75 0.85 0.96 RG 0.6 w 36 {base:.1f} 523 {alto_s:.1f} re S"
            )
            comandos.append(f"0.15 0.39 0.92 rg 36 {base:.1f} 4 {alto_s:.1f} re f")
            hdr = f"SALUD DEL PROYECTO: {b['indice']}/100 — {b['nivel']} | Progreso: {b['progreso']}"
            comandos.append(
                f"BT /F2 8.2 Tf 0.08 0.18 0.36 rg 46 {top - 12:.1f} Td "
                f"({_escapar_literal_pdf(hdr)}) Tj ET"
            )
            cy = top - 22.5
            for ln in b["diagnostico"]:
                comandos.append(
                    f"BT /F1 7.4 Tf 0.20 0.26 0.38 rg 46 {cy:.1f} Td ({_escapar_literal_pdf(ln)}) Tj ET"
                )
                cy -= 9.5
            for f_list in b["fortalezas"]:
                for idx_ln, ln in enumerate(f_list):
                    prefix = "[+] Fortaleza: " if idx_ln == 0 else "    "
                    comandos.append(
                        f"BT /F1 7.2 Tf 0.04 0.45 0.26 rg 46 {cy:.1f} Td ({_escapar_literal_pdf(prefix + ln)}) Tj ET"
                    )
                    cy -= 9.5
            for d_list in b["deficiencias"]:
                for idx_ln, ln in enumerate(d_list):
                    prefix = "[!] Deficiencia: " if idx_ln == 0 else "    "
                    comandos.append(
                        f"BT /F1 7.2 Tf 0.75 0.15 0.20 rg 46 {cy:.1f} Td ({_escapar_literal_pdf(prefix + ln)}) Tj ET"
                    )
                    cy -= 9.5
            for r_list in b["recomendaciones"]:
                for idx_ln, ln in enumerate(r_list):
                    prefix = "[->] Plan mejora: " if idx_ln == 0 else "    "
                    comandos.append(
                        f"BT /F1 7.2 Tf 0.10 0.35 0.65 rg 46 {cy:.1f} Td ({_escapar_literal_pdf(prefix + ln)}) Tj ET"
                    )
                    cy -= 9.5
            y = base - 7.0
            continue

        if tipo == "panel_graficas":
            fns = b["funciones"]
            alto_g = max(136.0, 38.0 + len(fns) * 17.0)
            alto_ins = 44.0
            asegurar_espacio(alto_g + alto_ins + 12.0, sec_b)
            pagina_inicio_seccion[2] = len(paginas)
            top = y
            base = top - alto_g

            # Panel izquierdo: Gráfica comparativa por función (Cobertura y Mutation Score)
            comandos.append(f"0.98 0.99 1.00 rg 36 {base:.1f} 266 {alto_g:.1f} re f")
            comandos.append(
                f"0.82 0.86 0.92 RG 0.6 w 36 {base:.1f} 266 {alto_g:.1f} re S"
            )
            comandos.append(f"0.11 0.16 0.26 rg 36 {top - 16:.1f} 266 16 re f")
            comandos.append(
                f"BT /F2 7.6 Tf 1 1 1 rg 44 {top - 11:.1f} Td "
                "(GRAFICA 1: COBERTURA Y MUTATION POR FUNCION) Tj ET"
            )
            # Leyenda de series
            ly = top - 26.0
            comandos.append(f"0.23 0.51 0.96 rg 44 {ly:.1f} 7 5 re f")
            comandos.append(
                f"BT /F1 6.6 Tf 0.25 0.30 0.40 rg 54 {ly:.1f} Td (Lineas) Tj ET"
            )
            comandos.append(f"0.02 0.71 0.83 rg 88 {ly:.1f} 7 5 re f")
            comandos.append(
                f"BT /F1 6.6 Tf 0.25 0.30 0.40 rg 98 {ly:.1f} Td (Ramas) Tj ET"
            )
            comandos.append(f"0.55 0.36 0.96 rg 132 {ly:.1f} 7 5 re f")
            comandos.append(
                f"BT /F1 6.6 Tf 0.25 0.30 0.40 rg 142 {ly:.1f} Td (Mutation) Tj ET"
            )
            comandos.append(
                f"BT /F2 6.6 Tf 0.04 0.48 0.30 rg 202 {ly:.1f} Td (| Meta >= 60%) Tj ET"
            )

            bar_x = 126.0
            bar_w = 132.0
            meta_x = bar_x + 0.60 * bar_w
            fy = top - 38.0
            for fn_item in fns:
                comandos.append(
                    f"BT /F2 7 Tf 0.12 0.18 0.28 rg 42 {fy - 4:.1f} Td "
                    f"({_escapar_literal_pdf(fn_item['nombre'])}) Tj ET"
                )
                # Fondo de pista + 3 barras (Líneas, Ramas, Mutation)
                comandos.append(
                    f"0.91 0.94 0.98 rg {bar_x:.1f} {fy - 8:.1f} {bar_w:.1f} 11 re f"
                )
                w_lin = max(2.0, min(bar_w, (fn_item["lineas"] / 100.0) * bar_w))
                w_ram = max(2.0, min(bar_w, (fn_item["ramas"] / 100.0) * bar_w))
                comandos.append(
                    f"0.23 0.51 0.96 rg {bar_x:.1f} {fy - 0.5:.1f} {w_lin:.1f} 3.2 re f"
                )
                comandos.append(
                    f"0.02 0.71 0.83 rg {bar_x:.1f} {fy - 4.2:.1f} {w_ram:.1f} 3.2 re f"
                )
                if fn_item["tiene_ms"]:
                    w_ms = max(2.0, min(bar_w, (fn_item["ms"] / 100.0) * bar_w))
                    comandos.append(
                        f"0.55 0.36 0.96 rg {bar_x:.1f} {fy - 7.9:.1f} {w_ms:.1f} 3.2 re f"
                    )
                comandos.append(
                    f"BT /F1 6.5 Tf 0.20 0.26 0.36 rg {bar_x + bar_w + 4:.1f} {fy - 4:.1f} Td "
                    f"({fn_item['lineas']:.0f}%/{fn_item['ramas']:.0f}%) Tj ET"
                )
                fy -= 16.5
            # Línea vertical de meta al 60 %
            comandos.append(
                f"0.06 0.68 0.46 RG 0.8 w {meta_x:.1f} {base + 6:.1f} m {meta_x:.1f} {top - 30:.1f} l S"
            )

            # Panel derecho superior: Gráfica 2 (Distribución de estados)
            alto_d1 = 66.0
            base_d1 = top - alto_d1
            comandos.append(
                f"0.98 0.99 1.00 rg 310 {base_d1:.1f} 249 {alto_d1:.1f} re f"
            )
            comandos.append(
                f"0.82 0.86 0.92 RG 0.6 w 310 {base_d1:.1f} 249 {alto_d1:.1f} re S"
            )
            comandos.append(f"0.11 0.16 0.26 rg 310 {top - 16:.1f} 249 16 re f")
            comandos.append(
                f"BT /F2 7.6 Tf 1 1 1 rg 318 {top - 11:.1f} Td "
                "(GRAFICA 2: DISTRIBUCION DE ESTADOS DE AUDITORIA) Tj ET"
            )
            est = b["estados"]
            tot_fn = float(b["total_fn"])
            sx = 318.0
            ancho_st = 233.0
            segmentos = [
                ("Aprobadas", est["aprobado"], "0.06 0.68 0.46"),
                ("Laundering", est["rechazado_laundering"], "0.88 0.18 0.30"),
                ("Bug Oraculo", est["bug_detectado"], "0.72 0.16 0.82"),
                ("Flaky/Otros", est["otros"], "0.85 0.48 0.04"),
            ]
            comandos.append(
                f"0.90 0.93 0.97 rg {sx:.1f} {top - 32:.1f} {ancho_st:.1f} 10 re f"
            )
            cur_x = sx
            for _, cnt, col in segmentos:
                if cnt > 0:
                    seg_w = (cnt / tot_fn) * ancho_st
                    comandos.append(
                        f"{col} rg {cur_x:.1f} {top - 32:.1f} {seg_w:.1f} 10 re f"
                    )
                    cur_x += seg_w
            for idx_s, (nom_s, cnt, col) in enumerate(segmentos):
                col_x = 318.0 + (idx_s % 2) * 118.0
                row_y = (top - 45.0) if idx_s < 2 else (top - 57.0)
                pct_s = (cnt / tot_fn) * 100.0
                comandos.append(f"{col} rg {col_x:.1f} {row_y:.1f} 6 6 re f")
                comandos.append(
                    f"BT /F1 7 Tf 0.18 0.24 0.34 rg {col_x + 10:.1f} {row_y:.1f} Td "
                    f"({_escapar_literal_pdf(f'{nom_s}: {cnt} ({pct_s:.0f}%)')}) Tj ET"
                )

            # Panel derecho inferior: Gráfica 3 (Tokens y Costo por Agente)
            top_d2 = base_d1 - 6.0
            alto_d2 = top_d2 - base
            comandos.append(f"0.98 0.99 1.00 rg 310 {base:.1f} 249 {alto_d2:.1f} re f")
            comandos.append(
                f"0.82 0.86 0.92 RG 0.6 w 310 {base:.1f} 249 {alto_d2:.1f} re S"
            )
            comandos.append(f"0.11 0.16 0.26 rg 310 {top_d2 - 15:.1f} 249 15 re f")
            comandos.append(
                f"BT /F2 7.5 Tf 1 1 1 rg 318 {top_d2 - 10.5:.1f} Td "
                "(GRAFICA 3: TOKENS Y COSTO POR AGENTE IA) Tj ET"
            )
            colores_ag = ["0.39 0.40 0.95", "0.96 0.62 0.04", "0.06 0.73 0.51"]
            ay = top_d2 - 27.0
            for idx_a, ag_item in enumerate(b["agentes"]):
                col_a = colores_ag[idx_a % len(colores_ag)]
                comandos.append(
                    f"BT /F2 7.2 Tf 0.14 0.20 0.30 rg 318 {ay:.1f} Td "
                    f"({_escapar_literal_pdf(ag_item['nombre'])}) Tj ET"
                )
                comandos.append(f"0.90 0.93 0.97 rg 368 {ay - 1:.1f} 96 7 re f")
                w_ag = max(3.0, min(96.0, (ag_item["pct"] / 100.0) * 96.0))
                comandos.append(f"{col_a} rg 368 {ay - 1:.1f} {w_ag:.1f} 7 re f")
                ag_lbl = _escapar_literal_pdf(
                    f"{ag_item['pct']:.0f}% | US$ {ag_item['usd']:.4f}"
                )
                comandos.append(
                    f"BT /F1 6.8 Tf 0.22 0.28 0.38 rg 468 {ay:.1f} Td ({ag_lbl}) Tj ET"
                )
                ay -= 14.0

            # Síntesis del Experto en Análisis de Datos (debajo de las gráficas)
            top_ins = base - 5.0
            base_ins = top_ins - alto_ins
            comandos.append(
                f"0.93 0.97 1.00 rg 36 {base_ins:.1f} 523 {alto_ins:.1f} re f"
            )
            comandos.append(
                f"0.75 0.85 0.96 RG 0.6 w 36 {base_ins:.1f} 523 {alto_ins:.1f} re S"
            )
            comandos.append(
                f"0.02 0.52 0.78 rg 36 {base_ins:.1f} 4 {alto_ins:.1f} re f"
            )
            comandos.append(
                f"BT /F2 7.8 Tf 0.05 0.28 0.48 rg 46 {top_ins - 11:.1f} Td "
                "(SINTESIS DEL EXPERTO EN ANALISIS DE DATOS - HALLAZGOS ESTADISTICOS CLAVE) Tj ET"
            )
            iy = top_ins - 21.5
            for ins_ln in b["insights"]:
                comandos.append(
                    f"BT /F1 7.4 Tf 0.14 0.22 0.34 rg 48 {iy:.1f} Td "
                    f"(- {_escapar_literal_pdf(ins_ln)}) Tj ET"
                )
                iy -= 9.5

            y = base_ins - 8.0
            continue

        if tipo == "tarjeta_funcion":
            ctrl = b["controles"]
            alto_t = 38.0 + len(ctrl) * 11.0
            asegurar_espacio(alto_t + 6, sec_b)
            top = y
            base = top - alto_t
            acento, badge_bg, badge_fg = _colores_estado_pdf(b["estado_clave"])
            comandos.append(f"0.98 0.99 1.00 rg 36 {base:.1f} 523 {alto_t:.1f} re f")
            comandos.append(
                f"0.83 0.87 0.93 RG 0.6 w 36 {base:.1f} 523 {alto_t:.1f} re S"
            )
            comandos.append(f"{acento} rg 36 {base:.1f} 4 {alto_t:.1f} re f")
            comandos.append(
                f"BT /F2 9.2 Tf 0.08 0.12 0.20 rg 46 {top - 13:.1f} Td "
                f"({_escapar_literal_pdf(b['titulo'])}) Tj ET"
            )
            # Mini barra visual de cobertura dentro de la tarjeta
            cob_l = max(0.0, min(100.0, float(b.get("cob_lineas", 0.0))))
            comandos.append(f"0.88 0.92 0.97 rg 330 {top - 13:.1f} 80 5 re f")
            comandos.append(
                f"{acento} rg 330 {top - 13:.1f} {(cob_l / 100.0) * 80.0:.1f} 5 re f"
            )
            comandos.append(f"{badge_bg} rg 422 {top - 16.5:.1f} 130 13 re f")
            comandos.append(
                f"BT /F2 7.5 Tf {badge_fg} rg 428 {top - 12.5:.1f} Td "
                f"({_escapar_literal_pdf(b['estado_lbl'])}) Tj ET"
            )
            comandos.append(f"0.93 0.95 0.98 rg 44 {top - 29:.1f} 508 12 re f")
            comandos.append(
                f"BT /F1 8 Tf 0.16 0.22 0.32 rg 48 {top - 25.5:.1f} Td "
                f"({_escapar_literal_pdf(b['metricas'])}) Tj ET"
            )
            cy = top - 40.0
            for ln in ctrl:
                comandos.append(
                    f"BT /F1 7.8 Tf 0.26 0.31 0.40 rg 46 {cy:.1f} Td "
                    f"({_escapar_literal_pdf(ln)}) Tj ET"
                )
                cy -= 11.0
            y = base - 6.0
            continue

        if tipo == "encabezado_bloque":
            asegurar_espacio(32.0, sec_b)
            base = y - 16.0
            ac = b.get("acento", "codigo")
            if ac == "incidente":
                bg_h, bar_c, txt_c = (
                    "0.99 0.92 0.93",
                    "0.88 0.18 0.30",
                    "0.48 0.08 0.16",
                )
            elif ac == "contrato":
                bg_h, bar_c, txt_c = (
                    "0.91 0.95 0.99",
                    "0.15 0.39 0.92",
                    "0.08 0.22 0.48",
                )
            else:
                bg_h, bar_c, txt_c = (
                    "0.94 0.92 0.99",
                    "0.52 0.26 0.88",
                    "0.26 0.12 0.48",
                )
            comandos.append(f"{bg_h} rg 36 {base:.1f} 523 16 re f")
            comandos.append(f"{bar_c} rg 36 {base:.1f} 3.5 16 re f")
            comandos.append(
                f"BT /F2 8.8 Tf {txt_c} rg 45 {base + 4.5:.1f} Td "
                f"({_escapar_literal_pdf(b['titulo'])}) Tj ET"
            )
            comandos.append(
                f"BT /F2 7.2 Tf {txt_c} rg 430 {base + 5:.1f} Td "
                f"({_escapar_literal_pdf(b['etiqueta'])}) Tj ET"
            )
            y = base
            continue

        if tipo == "linea_codigo":
            asegurar_espacio(12.0, sec_b)
            base = y - 11.0
            ac = b.get("acento", "codigo")
            bar_c = (
                "0.88 0.18 0.30"
                if ac == "incidente"
                else ("0.15 0.39 0.92" if ac == "contrato" else "0.52 0.26 0.88")
            )
            comandos.append(f"0.96 0.97 0.99 rg 36 {base:.1f} 523 11.2 re f")
            comandos.append(f"{bar_c} rg 36 {base:.1f} 2.5 11.2 re f")
            comandos.append(f"0.84 0.88 0.93 RG 0.4 w 559 {base:.1f} m 559 {y:.1f} l S")
            if b.get("ultima"):
                comandos.append(
                    f"0.84 0.88 0.93 RG 0.4 w 36 {base:.1f} m 559 {base:.1f} l S"
                )
            comandos.append(
                f"BT /F3 7.8 Tf 0.14 0.18 0.26 rg 45 {base + 3:.1f} Td "
                f"({_escapar_literal_pdf(b['texto'])}) Tj ET"
            )
            y = base
            continue

        asegurar_espacio(14.0, sec_b)
        comandos.append(
            f"BT /F1 8.8 Tf 0.15 0.20 0.28 rg 42 {y - 10:.1f} Td "
            f"({_escapar_literal_pdf(b.get('texto', ''))}) Tj ET"
        )
        y -= 13.0

    if comandos:
        paginas.append(comandos)
        secciones_pagina.append(seccion_actual)

    # Dibujar pie de página en cada hoja
    total_pags = len(paginas)
    for idx_pag, cmds in enumerate(paginas):
        pie_izq = _escapar_literal_pdf(
            "QAgent Autonomous Test Engine  |  Documento de Auditoria  |  Sin claves de IA (RN-07)"
        )
        pie_der = _escapar_literal_pdf(f"Página {idx_pag + 1} de {total_pags}")
        cmds.append("0.84 0.88 0.93 RG 0.6 w 36 38 m 559 38 l S")
        cmds.append(f"BT /F1 7.5 Tf 0.45 0.50 0.58 rg 36 26 Td ({pie_izq}) Tj ET")
        cmds.append(f"BT /F2 8 Tf 0.30 0.36 0.46 rg 492 26 Td ({pie_der}) Tj ET")

    # Construcción de objetos PDF-1.4 con marcadores nativos (/Outlines)
    objetos: list[bytes] = []

    def reservar_objeto(cuerpo: str) -> int:
        objetos.append(cuerpo.encode("ascii"))
        return len(objetos)

    id_catalog = reservar_objeto("")
    id_pages = reservar_objeto("")
    id_font_reg = reservar_objeto(
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    )
    id_font_bold = reservar_objeto(
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"
    )
    id_font_mono = reservar_objeto(
        "<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>"
    )

    ids_paginas: list[int] = []
    ids_contenidos: list[int] = []
    for cmds in paginas:
        stream_str = "\n".join(cmds) + "\n"
        stream_bytes = stream_str.encode("ascii")
        id_contenido = reservar_objeto(
            f"<< /Length {len(stream_bytes)} >>\nstream\n{stream_str}endstream"
        )
        id_pagina = reservar_objeto("")
        ids_contenidos.append(id_contenido)
        ids_paginas.append(id_pagina)

    for idx_p, id_pagina in enumerate(ids_paginas):
        id_contenido = ids_contenidos[idx_p]
        objetos[id_pagina - 1] = (
            f"<< /Type /Page /Parent {id_pages} 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 {id_font_reg} 0 R /F2 {id_font_bold} 0 R /F3 {id_font_mono} 0 R >> >> "
            f"/Contents {id_contenido} 0 R >>"
        ).encode("ascii")

    # Marcadores laterales nativos del lector PDF (/Outlines)
    id_outlines = reservar_objeto("")
    ids_items_outline: list[int] = [reservar_objeto("") for _ in _SECCIONES_PDF]
    for i_tab, (sec_id, etq_tab) in enumerate(_SECCIONES_PDF):
        pag_idx = max(
            0, min(len(ids_paginas) - 1, pagina_inicio_seccion.get(sec_id, 0))
        )
        id_pag_dest = ids_paginas[pag_idx]
        prev_str = f" /Prev {ids_items_outline[i_tab - 1]} 0 R" if i_tab > 0 else ""
        next_str = (
            f" /Next {ids_items_outline[i_tab + 1]} 0 R"
            if i_tab + 1 < len(ids_items_outline)
            else ""
        )
        objetos[ids_items_outline[i_tab] - 1] = (
            f"<< /Title ({_escapar_literal_pdf(etq_tab)}) /Parent {id_outlines} 0 R"
            f"{prev_str}{next_str} /Dest [{id_pag_dest} 0 R /XYZ null 842 null] >>"
        ).encode("ascii")

    objetos[id_outlines - 1] = (
        f"<< /Type /Outlines /First {ids_items_outline[0]} 0 R "
        f"/Last {ids_items_outline[-1]} 0 R /Count {len(ids_items_outline)} >>"
    ).encode("ascii")

    objetos[id_catalog - 1] = (
        f"<< /Type /Catalog /Pages {id_pages} 0 R /Outlines {id_outlines} 0 R /PageMode /UseOutlines >>"
    ).encode("ascii")

    kids = " ".join(f"{pid} 0 R" for pid in ids_paginas)
    objetos[id_pages - 1] = (
        f"<< /Type /Pages /Kids [{kids}] /Count {len(ids_paginas)} >>".encode("ascii")
    )

    salida = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = [0]
    for indice, contenido_obj in enumerate(objetos, start=1):
        offsets.append(len(salida))
        salida.extend(f"{indice} 0 obj\n".encode("ascii"))
        salida.extend(contenido_obj)
        salida.extend(b"\nendobj\n")

    pos_xref = len(salida)
    salida.extend(f"xref\n0 {len(objetos) + 1}\n".encode("ascii"))
    salida.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        salida.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    salida.extend(
        f"trailer\n<< /Size {len(objetos) + 1} /Root {id_catalog} 0 R >>\n"
        f"startxref\n{pos_xref}\n%%EOF\n".encode("ascii")
    )
    return bytes(salida)


def _escribir_bytes_atomico(ruta: Path, datos: bytes) -> None:
    """Escribe un archivo de forma atómica en la carpeta destino."""
    descriptor, temporal = tempfile.mkstemp(
        prefix=f".{ruta.name}.", suffix=".tmp", dir=ruta.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as archivo:
            archivo.write(datos)
        os.replace(temporal, ruta)
    except BaseException:
        Path(temporal).unlink(missing_ok=True)
        raise
