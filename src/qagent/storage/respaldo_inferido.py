"""Presentación de regresiones inferidas, conservando intacta la evidencia original."""

from __future__ import annotations

import copy
from typing import Any

from qagent.contracts import es_contrato_inferido

AVISO = "Regresión sin contrato documentado. Un fallo es un hallazgo a revisar, no un bug confirmado."


def es_inferida(funcion: dict[str, Any]) -> bool:
    """Detecta la procedencia tanto en vistas actuales como en contratos guardados."""
    return funcion.get("respaldo") == "inferido" or es_contrato_inferido(
        funcion.get("contrato")
    )


def datos_para_informe(datos: dict[str, Any]) -> dict[str, Any]:
    """Proyecta etiquetas para exportar; nunca cambia decisiones ni archivos guardados."""
    if not any(es_inferida(f) for f in datos.get("funciones", [])):
        return datos
    salida = copy.deepcopy(datos)
    for funcion in salida.get("funciones", []):
        if not es_inferida(funcion):
            continue
        funcion["respaldo"] = "inferido"
        funcion["resumen_ejecucion"] = (
            AVISO + " " + (funcion.get("resumen_ejecucion") or "")
        )
        evidencia = funcion.get("evidencia_inferida") or [
            e
            for c in (funcion.get("contrato") or {}).get("casos", [])
            for e in c.get("evidencia", [])
        ]
        if evidencia:
            funcion["resumen_ejecucion"] += " Evidencia: " + "; ".join(evidencia)
        funcion["explicacion"] = None
        # Los informes no reclasifican el dato persistido: esta etiqueta solo
        # impide que las plantillas de defectos confirmados interpreten la inferencia.
        if funcion.get("estado") == "bug_detectado":
            funcion["estado"] = "hallazgo_inferido"
            funcion["motivo_fallo"] = funcion["resumen_ejecucion"]
            for intento in funcion.get("intentos", []):
                if intento.get("decision") == "bug_detectado":
                    intento["decision"] = "hallazgo_a_revisar"
    return salida


def respuesta_con_respaldo(respuesta: str, funciones: list[dict[str, Any]]) -> str:
    """Separa regresión y contrato sin afirmar que una inferencia prueba corrección."""
    inferidas = [f for f in funciones if es_inferida(f)]
    if not inferidas:
        return respuesta
    fallos = sum(f.get("estado") == "hallazgo_inferido" for f in inferidas)
    desglose = f"{len(funciones) - len(inferidas)} con contrato y {len(inferidas)} de regresión sin contrato documentado."
    if fallos:
        documentados = any(
            f.get("estado") == "bug_detectado" and not es_inferida(f) for f in funciones
        )
        prefijo = respuesta + " " if documentados else ""
        return (
            f"{prefijo}{fallos} hallazgo(s) de regresión inferida a revisar. {desglose}"
        )
    return respuesta.replace("verificado", "probado") + " " + desglose
