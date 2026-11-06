"""Vista compartida de comparaciones persistidas entre corridas (#195).

Este módulo solo lee y presenta ``run_comparison.v1``. No ejecuta pruebas, no
regenera código y no modifica las corridas de origen o verificación.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from qagent import contracts
from qagent.almacenamiento.proyecto import AlmacenProyecto, id_de_spec
from qagent.storage.registro import PERFIL_VERIFICAR_CORRECCION
from qagent.storage.vista_ejecucion import ResultadosNoDisponibles, leer_results

ETIQUETAS_RESULTADO = {
    "corregido": "Corregido",
    "sigue_fallando": "Sigue fallando",
    "regresion": "Regresión",
    "no_comparable": "No comparable",
}
CLASES_RESULTADO = {
    "corregido": "exito",
    "sigue_fallando": "bug",
    "regresion": "error",
    "no_comparable": "aviso",
}
ETIQUETAS_DECISION = {
    "accept": "Aprobó",
    "bug_detectado": "Falló con un bug reproducible",
    "stalled": "Terminó sin resultado confiable",
    "sin_veredicto": "Terminó sin veredicto",
    "requiere_corrida_nueva": "No se ejecutó",
}


def vista_comparacion(documento: dict[str, Any]) -> dict[str, Any]:
    """Convierte un contrato válido en una vista estable para todos los consumidores."""
    contracts.validar_comparacion(documento)
    detalles = [_detalle(item) for item in documento["comparaciones"]]
    conteo = {estado: 0 for estado in ETIQUETAS_RESULTADO}
    for item in detalles:
        conteo[item["resultado"]] += 1

    originales = [item["estado_anterior"]["decision"] for item in detalles]
    actuales = [item["estado_posterior"]["decision"] for item in detalles]
    ejecutadas = sum(decision != "requiere_corrida_nueva" for decision in actuales)
    resumen = {
        "total_original": len(detalles),
        "total_actual": len(detalles),
        "total_ejecutadas": ejecutadas,
        "aprobadas_original": originales.count("accept"),
        "fallidas_original": originales.count("bug_detectado"),
        "aprobadas_actual": actuales.count("accept"),
        "fallidas_actual": actuales.count("bug_detectado"),
        "corregidos": conteo["corregido"],
        "siguen_fallando": conteo["sigue_fallando"],
        "regresiones": conteo["regresion"],
        "no_comparables": conteo["no_comparable"],
        "contadores_completos": len(detalles) > 0,
    }
    return {
        "disponible": True,
        "run_origen_id": documento["run_origen_id"],
        "run_verificacion_id": documento["run_verificacion_id"],
        "creado": documento["creado"],
        "resumen": resumen,
        "comparaciones": detalles,
        "politica_agregacion": (
            "El contrato conserva una comparación por objetivo. Los estados mixtos "
            "se muestran por separado y nunca se resumen como totalmente corregidos."
        ),
    }


def cargar_vista_comparacion(
    raiz_proyecto: str | Path,
    run_verificacion_id: str,
    perfil: str | None,
) -> dict[str, Any] | None:
    """Carga la comparación de una verificación o devuelve una explicación segura.

    ``None`` significa que la corrida no es ``verify_fix``. Para una verificación
    histórica sin datos se devuelve una vista no disponible, de modo que la UI y los
    informes sigan funcionando sin inventar totales.
    """
    if perfil != PERFIL_VERIFICAR_CORRECCION:
        return None
    raiz = Path(raiz_proyecto).resolve()
    almacen = AlmacenProyecto(raiz)
    candidatas = [
        dato
        for dato in almacen.listar_comparaciones(run_verificacion_id)
        if dato.get("run_verificacion_id") == run_verificacion_id
    ]
    if len(candidatas) != 1:
        carpeta = almacen.carpeta_comparaciones / Path(run_verificacion_id).name
        motivo = (
            "La comparación almacenada no pudo validarse; la corrida de origen puede "
            "faltar o los datos pueden estar corruptos."
            if carpeta.is_dir() and any(carpeta.glob("*.json"))
            else "Esta verificación histórica no tiene una comparación almacenada."
        )
        if len(candidatas) > 1:
            motivo = "La verificación tiene más de una corrida de origen asociada."
        return _no_disponible(run_verificacion_id, motivo)

    documento = candidatas[0]
    try:
        origen = leer_results(raiz, documento["run_origen_id"])
        verificacion = leer_results(raiz, run_verificacion_id)
    except ResultadosNoDisponibles as error:
        return _no_disponible(run_verificacion_id, str(error))
    if not _pertenece_al_proyecto(origen, raiz) or not _pertenece_al_proyecto(
        verificacion, raiz
    ):
        return _no_disponible(
            run_verificacion_id,
            "La comparación referencia resultados de otro proyecto.",
        )
    inconsistencia = _validar_referencias(documento, origen, verificacion)
    if inconsistencia:
        return _no_disponible(run_verificacion_id, inconsistencia)
    vista = vista_comparacion(documento)
    vista["proyecto"] = raiz.name
    vista["origen_disponible"] = True
    return vista


def _detalle(item: dict[str, Any]) -> dict[str, Any]:
    anterior = _estado(item["estado_anterior"])
    posterior = _estado(item["estado_posterior"])
    resultado = item["resultado"]
    motivo = item.get("motivo")
    explicacion = None
    if (
        resultado == "no_comparable"
        and anterior["decision"] == posterior["decision"] == "accept"
    ):
        explicacion = (
            "La prueba aprobó en ambas corridas; el contrato actual no define un "
            "quinto estado neutro y conserva el estado técnico No comparable."
        )
    return {
        "id": item["prueba"]["id"],
        "archivo": item["prueba"]["archivo"],
        "modulo": item["objetivo"]["modulo"],
        "objetivo": item["objetivo"]["nombre"],
        "tipo": item["objetivo"]["tipo"],
        "firma_origen": item.get("firma_origen"),
        "firma_verificacion": item.get("firma_verificacion"),
        "estado_anterior": anterior,
        "estado_posterior": posterior,
        "resultado": resultado,
        "etiqueta": ETIQUETAS_RESULTADO[resultado],
        "clase": CLASES_RESULTADO[resultado],
        "motivo": motivo,
        "explicacion": explicacion,
        "ejecutada": posterior["decision"] != "requiere_corrida_nueva",
    }


def _estado(estado: dict[str, Any]) -> dict[str, Any]:
    decision = estado["decision"]
    return {
        "decision": decision,
        "etiqueta": ETIQUETAS_DECISION.get(decision, decision),
        "confiable": bool(estado["confiable"]),
        "observado": estado.get("observado"),
    }


def _pertenece_al_proyecto(results: dict[str, Any], raiz: Path) -> bool:
    proyecto = results.get("proyecto")
    if not isinstance(proyecto, str) or not proyecto:
        return False
    try:
        return Path(proyecto).resolve() == raiz
    except OSError:
        return False


def _validar_referencias(
    documento: dict[str, Any],
    origen: dict[str, Any],
    verificacion: dict[str, Any],
) -> str | None:
    """Contrasta ids y objetivos con ambos ``results.json`` confiables."""
    if origen.get("run_id") != documento["run_origen_id"]:
        return "El identificador de la corrida original no coincide con sus resultados."
    if verificacion.get("run_id") != documento["run_verificacion_id"]:
        return "El identificador de la verificación no coincide con sus resultados."

    def identidades(results: dict[str, Any]) -> set[tuple[str, str]]:
        return {
            (str(item.get("modulo")), str(item.get("funcion")))
            for item in results.get("objetivos", [])
            if isinstance(item, dict) and item.get("modulo") and item.get("funcion")
        }

    anteriores = identidades(origen)
    actuales = identidades(verificacion)
    for item in documento["comparaciones"]:
        objetivo = item["objetivo"]
        identidad = (objetivo["modulo"], objetivo["nombre"])
        if identidad not in anteriores:
            return "La comparación contiene un objetivo ajeno a la corrida original."
        if identidad not in actuales:
            return "La comparación contiene un objetivo ajeno a la verificación."
        if item["prueba"]["id"] != id_de_spec(*identidad):
            return "La prueba asociada no corresponde con el objetivo comparado."
    return None


def _no_disponible(run_id: str, motivo: str) -> dict[str, Any]:
    return {
        "disponible": False,
        "run_origen_id": None,
        "run_verificacion_id": run_id,
        "motivo": motivo,
        "resumen": None,
        "comparaciones": [],
        "origen_disponible": False,
    }
