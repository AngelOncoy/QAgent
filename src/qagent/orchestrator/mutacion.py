"""Mutation testing de las funciones críticas aprobadas en el perfil Profundo (EN-09).

Corre después de que el Reviewer aprobó las pruebas de un módulo: mutmut solo se aplica
a las funciones con `critical: true` (HU-06) cuya prueba quedó aprobada, nunca al
repositorio completo (RN-04). Usa como pruebas las aprobadas de las funciones del módulo
y no llama a ningún agente de IA (0 tokens). Un fallo de mutmut nunca detiene la corrida:
queda registrado en la función con su motivo.
"""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Callable
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from qagent.almacenamiento import id_de_spec, nombre_prueba
from qagent.orchestrator.orquestador import ResultadoCorrida, ResultadoObjetivo
from qagent.sandbox import LIMITES_POR_DEFECTO, ejecutar_mutacion
from qagent.sandbox.mutacion import ERROR, OK, MutacionFuncion, ResultadoMutacion

PERFIL_PROFUNDO = "deep"

Mutador = Callable[..., ResultadoMutacion]
Avisar = Callable[[str], None]

_registro = logging.getLogger("qagent.mutacion")


def criticas_aprobadas(resultado: ResultadoCorrida) -> list[ResultadoObjetivo]:
    """Funciones críticas del módulo cuya prueba aprobó el Reviewer."""
    return [o for o in _funciones_aprobadas(resultado) if o.critical]


def mutar_modulo(
    raiz: str | Path,
    imagen: str,
    modulo: dict[str, Any],
    resultado: ResultadoCorrida,
    tiempo_por_funcion_s: int,
    mutador: Mutador = ejecutar_mutacion,
    avisar: Avisar | None = None,
) -> None:
    """Ejecuta mutmut sobre las funciones críticas aprobadas y anota el resultado.

    Deja en `objetivo.mutacion` de cada función crítica aprobada el estado, el Mutation
    Score, los detectados y los sobrevivientes. El tiempo máximo del contenedor es
    `tiempo_por_funcion_s` por cada función mutada.

    Args:
        raiz: carpeta del proyecto (se copia al sandbox; no se modifica).
        imagen: imagen del sandbox del proyecto.
        modulo: el módulo analizado (para la línea de cada función).
        resultado: resultado del orquestador para ese módulo.
        tiempo_por_funcion_s: `[mutacion] tiempo_maximo_por_funcion_s` de config.toml.
        mutador: cómo se ejecuta mutmut (Docker; reemplazable en pruebas).
        avisar: recibe los mensajes para el Monitor.
    """
    objetivos = criticas_aprobadas(resultado)
    if not objetivos:
        return
    avisar = avisar or (lambda _mensaje: None)
    nombres = [o.objetivo for o in objetivos]
    inicios = {
        f["nombre"]: f["linea"]
        for f in modulo.get("funciones") or []
        if isinstance(f.get("linea"), int)
    }
    limites = replace(
        LIMITES_POR_DEFECTO, timeout_s=tiempo_por_funcion_s * len(nombres)
    )
    avisar(
        f"Mutation testing (mutmut) sobre {len(nombres)} función(es) crítica(s): "
        f"{', '.join(nombres)} · 0 tokens"
    )

    with tempfile.TemporaryDirectory(prefix="qagent-mutacion-") as carpeta:
        for aprobada in _funciones_aprobadas(resultado):
            archivo = nombre_prueba(id_de_spec(resultado.modulo, aprobada.objetivo))
            (Path(carpeta) / archivo).write_text(
                aprobada.codigo or "", encoding="utf-8"
            )
        try:
            por_funcion = mutador(
                imagen,
                raiz,
                carpeta,
                resultado.modulo,
                nombres,
                limites,
                inicios=inicios,
            ).funciones
        except Exception as error:  # noqa: BLE001 — mutmut nunca detiene la corrida
            _registro.warning("mutmut falló en %s: %s", resultado.modulo, error)
            por_funcion = {
                nombre: MutacionFuncion(
                    nombre, ERROR, mensaje=f"mutmut no pudo ejecutarse: {error}"
                )
                for nombre in nombres
            }

    for objetivo in objetivos:
        mutacion = por_funcion.get(objetivo.objetivo) or MutacionFuncion(
            objetivo.objetivo,
            ERROR,
            mensaje="mutmut no devolvió resultado para esta función.",
        )
        objetivo.mutacion = a_dict(mutacion)
        avisar(texto_para_monitor(mutacion))


def a_dict(mutacion: MutacionFuncion) -> dict[str, Any]:
    """Forma de `mutacion` en `results.json` (`run_log.schema.json`, EN-09)."""
    return {
        "estado": mutacion.estado,
        "puntuacion": mutacion.puntuacion,
        "detectados": mutacion.detectados,
        "sobrevivientes": [asdict(s) for s in mutacion.sobrevivientes],
        "mensaje": mutacion.mensaje,
    }


def texto_para_monitor(mutacion: MutacionFuncion) -> str:
    """Mensaje de una línea con el resultado de una función."""
    if mutacion.estado == OK and mutacion.puntuacion is not None:
        return (
            f"{mutacion.funcion}: Mutation Score {mutacion.puntuacion:g} % "
            f"({mutacion.detectados} de {mutacion.evaluados} mutantes detectados)"
        )
    return f"{mutacion.funcion}: sin Mutation Score · {mutacion.mensaje}"


def _funciones_aprobadas(resultado: ResultadoCorrida) -> list[ResultadoObjetivo]:
    return [
        o
        for o in resultado.objetivos
        if o.decision == "accept"
        and o.codigo
        and (o.contrato or {}).get("tipo", "funcion") == "funcion"
    ]
