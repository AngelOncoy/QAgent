"""Validaciones deterministas que JSON Schema no puede resolver por sí solo.

Los schemas comprueban forma, tipos y vocabulario. Este módulo contrasta las
referencias declaradas con registros que el llamador obtuvo de una fuente confiable;
no ejecuta código del usuario ni consulta un LLM.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import PurePath
from typing import Any

from qagent.contracts import (
    EXPLANATION_V1,
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


def validar_explicacion(
    dato: dict[str, Any],
    *,
    hallazgos_confiables: Mapping[str, Mapping[str, Any]],
    evidencias_confiables: Mapping[str, Any],
    verificaciones_confiables: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Valida ``explanation.v1`` contra hallazgos y ejecuciones confiables.

    ``hallazgos_confiables`` conserva para cada id su ``run_id``, ``objetivo``,
    ``tipo`` y los ids de ``evidencias`` asociados. Una recomendación solo queda
    ``verificada`` cuando su referencia existe en ``verificaciones_confiables`` y
    esa ejecución procede del sandbox, terminó en ``ok`` y fue aceptada.
    """
    validar(EXPLANATION_V1, dato)
    hallazgo_id = dato["hallazgo_id"]
    registrado = hallazgos_confiables.get(hallazgo_id)
    errores: list[str] = []
    if registrado is None:
        errores.append(
            f"hallazgo_id: {hallazgo_id!r} no existe en el registro confiable"
        )
    else:
        referencia = dato["referencia_resultado"]
        for campo in ("run_id", "objetivo"):
            if referencia[campo] != registrado.get(campo):
                errores.append(
                    f"referencia_resultado/{campo}: no coincide con el hallazgo"
                )
        if dato["hallazgo"]["tipo"] != registrado.get("tipo"):
            errores.append("hallazgo/tipo: no coincide con el hallazgo original")

        permitidas = set(registrado.get("evidencias", ()))
        usadas = {
            *dato["hallazgo"]["evidencia_ids"],
            *dato["recomendacion"]["evidencia_ids"],
        }
        for evidencia_id in sorted(usadas):
            if evidencia_id not in evidencias_confiables:
                errores.append(
                    f"evidencia_ids: {evidencia_id!r} no existe en el registro confiable"
                )
            elif evidencia_id not in permitidas:
                errores.append(
                    f"evidencia_ids: {evidencia_id!r} no pertenece al hallazgo"
                )

        ubicacion = dato.get("ubicacion")
        registrada_ubicacion = registrado.get("ubicacion")
        if ubicacion is not None and registrada_ubicacion is not None:
            for campo, valor in ubicacion.items():
                if registrada_ubicacion.get(campo) != valor:
                    errores.append(f"ubicacion/{campo}: no coincide con el hallazgo")

    ubicacion = dato.get("ubicacion")
    if ubicacion is not None:
        if not _es_ruta_relativa(ubicacion["archivo"]):
            errores.append("ubicacion/archivo: debe ser una ruta relativa segura")
        if ubicacion.get("linea_fin", ubicacion.get("linea_inicio", 1)) < ubicacion.get(
            "linea_inicio", 1
        ):
            errores.append("ubicacion/linea_fin: debe ser >= linea_inicio")

    verificacion = dato["verificacion"]
    if verificacion["estado"] == "verificada":
        registro = (verificaciones_confiables or {}).get(verificacion["ejecucion_id"])
        if registro is None:
            errores.append(
                "verificacion/ejecucion_id: no existe una ejecución confiable"
            )
        else:
            if registro.get("origen") != "sandbox":
                errores.append(
                    "verificacion: una afirmación del LLM no prueba la corrección"
                )
            if (
                registro.get("estado_sandbox") != "ok"
                or registro.get("decision") != "accept"
            ):
                errores.append(
                    "verificacion: la ejecución independiente no terminó aceptada"
                )
            referencia = dato["referencia_resultado"]
            if registro.get("run_id") != verificacion["run_id"]:
                errores.append("verificacion/run_id: no coincide con la ejecución")
            if registro.get("objetivo") != referencia["objetivo"]:
                errores.append("verificacion/ejecucion_id: corresponde a otro objetivo")

    if errores:
        raise ContratoInvalido(EXPLANATION_V1, errores)
    return dato


def _json_igual(izquierda: Any, derecha: Any) -> bool:
    """Igualdad JSON estricta: distingue, por ejemplo, ``0`` de ``False``."""
    return json.dumps(izquierda, sort_keys=True, ensure_ascii=False) == json.dumps(
        derecha, sort_keys=True, ensure_ascii=False
    )


def _es_ruta_relativa(valor: str) -> bool:
    ruta = PurePath(valor)
    return not ruta.is_absolute() and ":" not in valor and ".." not in ruta.parts
