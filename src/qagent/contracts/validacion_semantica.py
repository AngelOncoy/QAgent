"""Validaciones deterministas que JSON Schema no puede resolver por sí solo.

Los schemas comprueban forma, tipos y vocabulario. Este módulo contrasta las
referencias declaradas con registros que el llamador obtuvo de una fuente confiable;
no ejecuta código del usuario ni consulta un LLM.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import PurePath
from typing import Any

from qagent.contracts import (
    EXPLANATION_V1,
    EXPLICACIONES,
    ORACLE_V1,
    ContratoInvalido,
    validar,
)


def validar_oraculo_js_ts(
    dato: dict[str, Any],
    evidencias_confiables: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Valida un ``oracle.v1`` contra documentación registrada.

    El registro usa el id de la evidencia como clave. Cada valor contiene
    ``evidencia`` (una copia exacta de la evidencia documentada) y, cuando esa
    fuente determina una expectativa, ``valor_documentado`` o
    ``excepcion_documentada``. La presencia de la clave importa: ``None``, ``0``,
    ``False`` y ``""`` son expectativas válidas.
    """
    validar(ORACLE_V1, dato)
    estado = dato["estado_evidencia"]
    evidencia = dato.get("evidencia")
    if estado == "sin_procedencia":
        return dato

    evidencia_id = evidencia["id"]
    registrada = evidencias_confiables.get(evidencia_id)
    errores: list[str] = []
    if registrada is None:
        errores.append(
            f"evidencia/id: {evidencia_id!r} no existe en el registro confiable"
        )
    elif not _json_igual(registrada.get("evidencia"), evidencia):
        errores.append("evidencia: no coincide con la fuente confiable registrada")

    ubicacion = evidencia["ubicacion"]
    if (
        ubicacion.get("linea_fin", ubicacion["linea_inicio"])
        < ubicacion["linea_inicio"]
    ):
        errores.append("evidencia/ubicacion/linea_fin: debe ser >= linea_inicio")
    if not _es_ruta_relativa(ubicacion["archivo"]):
        errores.append("evidencia/ubicacion/archivo: debe ser una ruta relativa segura")

    if estado == "verificable" and registrada is not None:
        if evidencia["caracter"] in {
            "tipo_general",
            "descripcion_generica",
            "contradictoria",
        }:
            errores.append(
                "estado_evidencia: esa fuente no justifica un valor concreto"
            )
        if "valor_esperado" in dato:
            if "valor_documentado" not in registrada:
                errores.append(
                    "valor_esperado: la evidencia no documenta un valor concreto"
                )
            elif not _json_igual(
                dato["valor_esperado"], registrada["valor_documentado"]
            ):
                errores.append("valor_esperado: no coincide con el valor documentado")
        else:
            esperada = registrada.get("excepcion_documentada")
            if esperada is None:
                errores.append(
                    "excepcion_esperada: la evidencia no documenta una excepción"
                )
            elif dato["excepcion_esperada"] != esperada:
                errores.append(
                    "excepcion_esperada: no coincide con la excepción documentada"
                )

    if estado == "contradictoria" and evidencia["caracter"] != "contradictoria":
        errores.append(
            "estado_evidencia: una contradicción debe identificar evidencia contradictoria"
        )

    if errores:
        raise ContratoInvalido(ORACLE_V1, errores)
    return dato


_PATRONES_RELAJAR_ASERCION = (
    r"\brelajar\s+(?:la|las|el)?\s*(?:aserci[oó]n|aserciones|assert)",
    r"\bdebilitar\s+(?:la|las|el)?\s*(?:aserci[oó]n|aserciones|assert)",
    r"\b(?:cambiar|modificar|ajustar|actualizar)\s+(?:el\s+)?valor\s+esperado",
    r"\b(?:cambiar|modificar|ajustar|actualizar)\s+el\s+esperado\b",
    r"\b(?:eliminar|borrar|quitar|suprimir)\s+(?:la|las|el)?\s*(?:aserci[oó]n|aserciones|assert)",
    r"\b(?:cambiar|modificar|ajustar|relajar)\s+(?:la|las|el)?\s*(?:aserci[oó]n|assert)\b.*?\b(?:para\s+que\s+pase|evitar\s+el\s+fallo)",
    r"\b(?:bajar|reducir)\s+el\s+rigor\s+de\s+(?:la|las)?\s*aserci",
    r"\b(?:ignorar|suprimir)\s+(?:el\s+)?(?:fallo|error)\s+de\s+(?:la|el)?\s*(?:prueba|test|aserci[oó]n)",
)
_RE_RELAJAR_ASERCION = re.compile("|".join(_PATRONES_RELAJAR_ASERCION), re.IGNORECASE)


def _propone_relajar_o_cambiar_esperado(texto: str) -> bool:
    if not texto:
        return False
    return bool(_RE_RELAJAR_ASERCION.search(texto))


def validar_explicacion(
    dato: dict[str, Any],
    *,
    resultado_confiable: Mapping[str, Any] | None = None,
    results_confiables: Mapping[str, Any] | None = None,
    hallazgos_confiables: Mapping[str, Mapping[str, Any]] | None = None,
    evidencias_confiables: Mapping[str, Any] | None = None,
    verificaciones_confiables: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Valida ``explanation.v1`` según ADR-008.

    Comprueba que el schema sea válido, que la `decision` coincida exactamente con
    la registrada en `results.json` (no se admiten explicaciones para `accept`),
    que no se proponga relajar aserciones ni cambiar valores esperados, y que no se
    declare el estado `verificada` sin el ADR de parches.
    """
    validar(EXPLANATION_V1, dato)
    errores: list[str] = []

    # 1. Verificación no puede estar en estado "verificada" mientras no haya ADR de parches
    verificacion = dato.get("verificacion")
    if verificacion is not None and verificacion.get("estado") == "verificada":
        errores.append(
            "verificacion/estado: el estado 'verificada' no está permitido mientras no exista el ADR de parches"
        )

    # 2. Guardrail anti-laundering / anti-relajación en la recomendación
    textos_a_inspeccionar = [
        dato.get("que_hacer", ""),
        dato.get("resumen", ""),
        dato.get("que_paso", ""),
        dato.get("que_se_esperaba", ""),
    ]
    if "recomendacion" in dato and isinstance(dato["recomendacion"], dict):
        textos_a_inspeccionar.append(dato["recomendacion"].get("accion", ""))
        textos_a_inspeccionar.append(dato["recomendacion"].get("justificacion", ""))

    for texto in textos_a_inspeccionar:
        if _propone_relajar_o_cambiar_esperado(texto):
            errores.append(
                "que_hacer: no se permite proponer relajar una aserción ni cambiar el valor esperado"
            )
            break

    # 3. Ubicación segura si está presente
    ubicacion = dato.get("ubicacion")
    if ubicacion is not None:
        if not _es_ruta_relativa(ubicacion.get("archivo", "")):
            errores.append("ubicacion/archivo: debe ser una ruta relativa segura")
        if ubicacion.get("linea_fin", ubicacion.get("linea_inicio", 1)) < ubicacion.get(
            "linea_inicio", 1
        ):
            errores.append("ubicacion/linea_fin: debe ser >= linea_inicio")

    # 4. Eco de decision contra resultados confiables
    objetivo_nombre = dato.get("objetivo")
    res_encontrado: Mapping[str, Any] | None = resultado_confiable

    if res_encontrado is None and results_confiables is not None:
        for obj in results_confiables.get("objetivos", []):
            if (
                obj.get("funcion") == objetivo_nombre
                or obj.get("objetivo") == objetivo_nombre
            ):
                res_encontrado = obj
                break
        if res_encontrado is None:
            errores.append(f"objetivo: {objetivo_nombre!r} no existe en results.json")

    if res_encontrado is None and hallazgos_confiables is not None:
        hallazgo_id = dato.get("hallazgo_id")
        if hallazgo_id and hallazgo_id in hallazgos_confiables:
            res_encontrado = hallazgos_confiables[hallazgo_id]
        else:
            for reg in hallazgos_confiables.values():
                if reg.get("objetivo") == objetivo_nombre:
                    res_encontrado = reg
                    break
        if res_encontrado is None:
            errores.append(
                f"objetivo: {objetivo_nombre!r} no existe en el registro confiable"
            )

    if res_encontrado is not None:
        decision_registrada = res_encontrado.get("decision")
        if decision_registrada == "accept":
            errores.append(
                "decision: no se admiten explicaciones para objetivos con decision 'accept'"
            )
        elif decision_registrada is None:
            if dato.get("decision") not in (None, "sin_veredicto"):
                errores.append(
                    f"decision: {dato.get('decision')!r} no coincide con decision sin veredicto (None) de results.json"
                )
        else:
            if dato.get("decision") != decision_registrada:
                errores.append(
                    f"decision: {dato.get('decision')!r} no coincide con {decision_registrada!r} de results.json"
                )

    if errores:
        raise ContratoInvalido(EXPLANATION_V1, errores)
    return dato


def validar_explicaciones(
    dato: Any,
    *,
    results_confiables: Mapping[str, Any] | None = None,
) -> Any:
    """Valida el archivo ``explicaciones.json`` y cada una de sus explicaciones.

    Comprueba la conformidad con ``explicaciones.schema.json`` y valida semánticamente
    cada explicación frente a ``results_confiables`` si se provee.
    """
    validar(EXPLICACIONES, dato)
    lista = dato if isinstance(dato, list) else dato.get("explicaciones", [])
    errores: list[str] = []
    for i, exp in enumerate(lista):
        try:
            validar_explicacion(exp, results_confiables=results_confiables)
        except ContratoInvalido as error:
            prefix = f"explicaciones[{i}]"
            errores.extend(f"{prefix}/{e}" for e in error.errores)
    if errores:
        raise ContratoInvalido(EXPLICACIONES, errores)
    return dato


def _json_igual(izquierda: Any, derecha: Any) -> bool:
    """Igualdad JSON estricta: distingue, por ejemplo, ``0`` de ``False``."""
    return json.dumps(izquierda, sort_keys=True, ensure_ascii=False) == json.dumps(
        derecha, sort_keys=True, ensure_ascii=False
    )


def _es_ruta_relativa(valor: str) -> bool:
    ruta = PurePath(valor)
    return not ruta.is_absolute() and ":" not in valor and ".." not in ruta.parts
