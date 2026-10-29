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

from qagent.contracts import (
    EXPLICACIONES,
    ContratoInvalido,
    categoria_de,
    contar_categorias,
    validar,
    validar_explicacion,
)
from qagent.storage.registro import (
    ARCHIVO_DETALLE,
    ARCHIVO_EXPLICACIONES,
    CARPETA_RUNS,
    MUTATION_SCORE_MIN,
    PERFIL_HUMO,
    PERFILES_CON_MUTACION,
    nombre_perfil,
)
from qagent.storage.vista_ejecucion import (
    categorias_de,
    estado_de,
    identidad_de,
    texto_categorias,
    tipo_de,
)

#: Aviso cuando un objetivo no tiene casos límite (#76). No cuenta como fallo.
AVISO_SIN_LIMITES = {
    "funcion": "Sin casos límite: el docstring no describe límites; documentarlos "
    "permite probarlos.",
    "endpoint": "Sin casos límite: ni el docstring ni las restricciones declaradas "
    "(Field, Query, Path) describen límites; documentarlos permite probarlos.",
}

#: Estado de cada control para la pantalla.
OK, FALLA, NO_APLICA, PENDIENTE, SIN_DATO = (
    "ok",
    "falla",
    "no_aplica",
    "pendiente",
    "sin_dato",
)


def _segundos(valor: Any) -> float | None:
    """Duración numérica o None (corridas anteriores a #115)."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    return round(max(0.0, float(valor)), 3)


def _primer_entero(*valores: Any) -> int:
    """Primer entero no negativo, conservando el cero como dato real."""
    for valor in valores:
        if isinstance(valor, int) and not isinstance(valor, bool) and valor >= 0:
            return valor
    return 0


def leer_detalle(raiz_proyecto: str | Path, run_id: str) -> dict[str, Any] | None:
    """detalle.json de la corrida, o None si no existe (corridas anteriores a HU-21)."""
    ruta = Path(raiz_proyecto) / CARPETA_RUNS / Path(run_id).name / ARCHIVO_DETALLE
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return datos if isinstance(datos, dict) else None


#: Campos de una explicación (HU-32) que muestran la pantalla y el informe.
CAMPOS_EXPLICACION = ("resumen", "que_se_esperaba", "que_paso", "que_hacer")


def leer_explicaciones(
    raiz_proyecto: str | Path, results: dict[str, Any]
) -> dict[tuple[str, str], dict[str, str]]:
    """Explicaciones válidas de la corrida por `(modulo, objetivo)` (HU-32).

    Sin `explicaciones.json`, con un archivo que no cumple el contrato o con una
    explicación cuya decisión no coincide con `results.json`, esa explicación no se
    usa y la pantalla y el informe siguen como antes.
    """
    ruta = (
        Path(raiz_proyecto)
        / CARPETA_RUNS
        / Path(str(results["run_id"])).name
        / ARCHIVO_EXPLICACIONES
    )
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        validar(EXPLICACIONES, datos)
    except (OSError, json.JSONDecodeError, ContratoInvalido):
        return {}
    lista = datos if isinstance(datos, list) else datos["explicaciones"]
    objetivos = {(o["modulo"], o["funcion"]): o for o in results["objetivos"]}
    validas: dict[tuple[str, str], dict[str, str]] = {}
    for explicacion in lista:
        clave = (explicacion.get("modulo"), explicacion["objetivo"])
        objetivo = objetivos.get(clave)  # type: ignore[arg-type]
        if objetivo is None:
            continue
        try:
            validar_explicacion(explicacion, resultado_confiable=objetivo)
        except ContratoInvalido:
            continue
        validas[clave] = {c: explicacion[c] for c in CAMPOS_EXPLICACION}  # type: ignore[index]
    return validas


def vista_reporte(
    results: dict[str, Any],
    detalle: dict[str, Any] | None,
    explicaciones: dict[tuple[str, str], dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Cabecera, 4 indicadores, filtros y una tarjeta por función.

    `explicaciones` son las de `leer_explicaciones()` (HU-32); sin ellas cada
    tarjeta lleva `explicacion: None`.
    """
    resumen = results["resumen"]
    metas = resumen.get("metas") or {}
    textos = {
        (f["modulo"], f["funcion"]): f
        for f in (detalle or {}).get("funciones", [])
        if isinstance(f, dict)
    }
    funciones = [
        {
            **_funcion(
                o, textos.get((o["modulo"], o["funcion"])), metas, results["perfil"]
            ),
            "explicacion": (explicaciones or {}).get((o["modulo"], o["funcion"])),
        }
        for o in results["objetivos"]
    ]
    total_categorias = resumen.get("casos_por_categoria")
    verdes = sum(1 for f in funciones if f["verde"])
    tipos = [tipo_de(o) for o in results["objetivos"]]
    pasaron = sum(1 for o in results["objetivos"] if o["metricas"]["paso"])
    por_agente = resumen.get("por_agente") or {}

    omitidos = results.get("omitidos") or []
    total_omitidos = _primer_entero(
        results.get("objetivos_omitidos"),
        resumen.get("objetivos_omitidos"),
        len(omitidos),
    )
    total_seleccionados = _primer_entero(
        results.get("total_seleccionados"),
        resumen.get("total_seleccionados"),
        len(results["objetivos"]) + total_omitidos,
    )
    total_procesados = len(results["objetivos"])
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

    return {
        "total_seleccionados": total_seleccionados,
        "total_elegibles": total_elegibles,
        "total_procesados": total_procesados,
        "total_pendientes": total_pendientes,
        "total_omitidos": total_omitidos,
        "tipo_terminacion": tipo_terminacion,
        "es_parcial": es_parcial,
        "run_id": results["run_id"],
        "fecha": results["fecha"],
        "perfil": results["perfil"],
        "perfil_nombre": nombre_perfil(results["perfil"]),
        # #75: en Humo el Pass Rate es la métrica principal.
        "es_humo": results["perfil"] == PERFIL_HUMO,
        "rama": results.get("rama"),
        "proyecto": results["proyecto"],
        "es_simulado": results["es_simulado"],
        "estado_final": results["estado_final"],
        "motivo_fallo": results["motivo_fallo"],
        "inicio": results.get("inicio"),
        "fin": results.get("fin"),
        "duracion_total_s": _segundos(
            results.get("duracion_s", resumen.get("duracion_s"))
        ),
        "duracion_etapas": results.get("duracion_etapas")
        or resumen.get("duracion_etapas"),
        "total_funciones": resumen["total_funciones"],
        "total_objetivos": len(funciones),
        # #76: casos de la corrida por categoría; None en corridas anteriores.
        "categorias": total_categorias,
        "texto_categorias": texto_categorias(total_categorias),
        "modelos": {
            agente: {"proveedor": m["proveedor"], "modelo": m["modelo"]}
            for agente, m in results["modelos"].items()
        },
        "detalle_disponible": detalle is not None,
        # EN-17: entorno de ejecución y casos de pytest; None en corridas anteriores.
        "entorno": (detalle or {}).get("entorno"),
        "totales_casos": (detalle or {}).get("totales_casos"),
        "ejecucion_disponible": any(f["ejecucion"] is not None for f in funciones),
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
                "exige_ramas": results["perfil"] != PERFIL_HUMO,  # #75
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
    objetivo: dict[str, Any],
    texto: dict[str, Any] | None,
    metas: dict[str, Any],
    perfil: str | None = None,
) -> dict[str, Any]:
    metricas = objetivo["metricas"]
    contrato = (texto or {}).get("contrato")
    controles = _controles(objetivo, metas, perfil)
    intentos = _intentos((texto or {}).get("intentos"))
    verde = objetivo["decision"] == "accept" and all(
        c["estado"] in (OK, NO_APLICA, PENDIENTE) for c in controles
    )
    casos = contrato.get("casos") if isinstance(contrato, dict) else None
    categorias = categorias_de(objetivo) or (
        contar_categorias(casos) if casos else None
    )
    return {
        "modulo": objetivo["modulo"],
        "funcion": objetivo["funcion"],
        **identidad_de(objetivo),
        "firma": contrato.get("firma") if isinstance(contrato, dict) else None,
        "manejador": contrato.get("manejador") if isinstance(contrato, dict) else None,
        "critical": objetivo["critical"],
        # #76: casos por categoría, el aviso si no hay límites (no es un fallo) y la
        # categoría de cada caso para mostrarla junto a su resultado de pytest.
        "categorias": categorias,
        "texto_categorias": texto_categorias(categorias),
        "aviso_limites": (
            AVISO_SIN_LIMITES[tipo_de(objetivo)]
            if categorias and not categorias["limite"] and perfil != PERFIL_HUMO
            else None
        ),
        "categoria_por_caso": {
            c["id"]: categoria_de(c)
            for c in casos or []
            if isinstance(c, dict) and isinstance(c.get("id"), str)
        },
        "decision": objetivo["decision"],
        "estado": estado_de(objetivo),
        "verde": verde,
        "iteraciones": metricas["iteraciones"],
        "duracion_s": _segundos(objetivo.get("duracion_s")),
        "duracion_generacion_s": _segundos(objetivo.get("duracion_generacion_s")),
        "duracion_revision_s": _segundos(objetivo.get("duracion_revision_s")),
        "duracion_sandbox_s": _segundos(objetivo.get("duracion_sandbox_s")),
        "duracion_pytest_s": _segundos(objetivo.get("duracion_pytest_s")),
        "cobertura_lineas": metricas["cobertura_lineas"],
        "cobertura_ramas": metricas["cobertura_ramas"],
        "mutation_score": metricas["mutation_score"],
        "mutacion": objetivo.get("mutacion"),  # EN-09: estado y sobrevivientes
        "contrato": contrato,
        "contrato_http": _contrato_http(contrato),
        "codigo": (texto or {}).get("codigo"),
        "traza": (texto or {}).get("traza"),
        "controles": controles,
        "intentos": intentos,
        "ejecucion": next(
            (i["ejecucion"] for i in reversed(intentos) if i["ejecucion"]), None
        ),
    }


def _intentos(crudos: Any) -> list[dict[str, Any]]:
    """Intentos de la función con lo que pasó en cada uno (EN-17).

    Las corridas anteriores no traen `feedback` ni `ejecucion`: salen como None.
    """
    intentos = []
    for crudo in crudos if isinstance(crudos, list) else []:
        if not isinstance(crudo, dict):
            continue
        ejecucion = crudo.get("ejecucion")
        intentos.append(
            {
                "intento": crudo.get("intento"),
                "decision": crudo.get("decision"),
                "estado_sandbox": crudo.get("estado_sandbox"),
                "tipo_fallo": crudo.get("tipo_fallo"),
                "laundering_detectado": bool(crudo.get("laundering_detectado")),
                "feedback": crudo.get("feedback"),
                "cobertura": crudo.get("cobertura"),
                "duracion_s": _segundos(crudo.get("duracion_s")),
                "generacion_s": _segundos(crudo.get("generacion_s")),
                "revision_s": _segundos(crudo.get("revision_s")),
                "ejecucion": ejecucion if isinstance(ejecucion, dict) else None,
            }
        )
    return intentos


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
                "categoria": categoria_de(caso),  # #76
            }
        )
    return {"casos": casos}


def _controles(
    objetivo: dict[str, Any], metas: dict[str, Any], perfil: str | None = None
) -> list[dict[str, Any]]:
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

    humo = perfil == PERFIL_HUMO
    cobertura = control(
        "cobertura",
        # #75: Humo prueba un caso normal; las ramas se muestran pero no se exigen.
        f"Cobertura de líneas ({texto_lineas}) ≥ {minimo:g} % · ramas "
        f"({texto_ramas}) no se exigen en Humo"
        if humo
        else f"Cobertura de líneas ({texto_lineas}) y ramas ({texto_ramas}) "
        f"≥ {minimo:g} %",
    )
    if cobertura["estado"] == SIN_DATO and lineas is not None:  # corridas anteriores
        cumple = lineas >= minimo and (ramas is None or humo or ramas >= minimo)
        cobertura["estado"] = OK if cumple else FALLA

    mutation = _control_mutation(objetivo, perfil)

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


def _control_mutation(objetivo: dict[str, Any], perfil: str | None) -> dict[str, Any]:
    """Control de Mutation Score (EN-09), con la razón cuando no hay puntuación."""
    etiqueta = f"Mutation Score ≥ {MUTATION_SCORE_MIN} %"
    score = objetivo["metricas"]["mutation_score"]
    mutacion = objetivo.get("mutacion")

    def con(estado: str, nota: str | None = None, texto: str = etiqueta) -> dict:
        control = {"clave": "mutation", "etiqueta": texto, "estado": estado}
        if nota:
            control["nota"] = nota
        return control

    if not objetivo["critical"]:
        sujeto = "el endpoint" if tipo_de(objetivo) == "endpoint" else "la función"
        return con(NO_APLICA, f"No aplica: {sujeto} no es crítico")
    if score is not None:
        vivos = len((mutacion or {}).get("sobrevivientes") or [])
        notas = [f"{vivos} mutante(s) sobreviviente(s)" if vivos else ""]
        if (mutacion or {}).get("reutilizada"):
            notas.append(
                f"reutilizado de la corrida {mutacion.get('run_origen')}: "
                "la función y sus pruebas no cambiaron"
            )
        return con(
            OK if score >= MUTATION_SCORE_MIN else FALLA,
            " · ".join(n for n in notas if n) or None,
            f"{etiqueta} (obtenido: {score:g} %)",
        )
    if isinstance(mutacion, dict):
        return con(
            SIN_DATO, mutacion.get("mensaje") or "mutmut no dio un Mutation Score."
        )
    if perfil is not None and perfil not in PERFILES_CON_MUTACION:
        return con(NO_APLICA, "No se pidió: la corrida no usó Profundizar")
    if objetivo["decision"] == "requiere_corrida_nueva":
        return con(
            NO_APLICA,
            "Requiere corrida nueva: la función o su prueba cambiaron y mutmut solo "
            "usa pruebas guardadas vigentes",
        )
    if objetivo["decision"] != "accept":
        return con(
            NO_APLICA, "Sin prueba aprobada: mutmut necesita una prueba que pase"
        )
    return con(PENDIENTE, "Corrida anterior a EN-09: sin mutation testing")
