"""Mutation testing de las funciones críticas aprobadas (EN-09, #70).

Corre después de que las pruebas de un módulo quedaron aprobadas: en el perfil Profundo,
al terminar el Reviewer; en «Repetir pruebas guardadas + profundizar» (`reg_deep`), al
volver a ejecutar las pruebas guardadas. mutmut solo se aplica a las funciones con
`critical: true` (HU-06) cuya prueba pasó, nunca al repositorio completo (RN-04). Usa
como pruebas las aprobadas de las funciones del módulo y no llama a ningún agente de IA
(0 tokens). Un fallo de mutmut nunca detiene la corrida: queda registrado en la función
con su motivo.

Si se le da el almacén del proyecto, reutiliza el último resultado de una función cuando
ni ella ni las pruebas usadas cambiaron (`.qagent/mutacion/`, #70) y guarda los nuevos.
"""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Callable
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from qagent.almacenamiento import (
    AlmacenProyecto,
    ErrorAlmacen,
    huella_de_prueba,
    id_de_spec,
    nombre_prueba,
)
from qagent.orchestrator.orquestador import ResultadoCorrida, ResultadoObjetivo
from qagent.sandbox import LIMITES_POR_DEFECTO, ejecutar_mutacion
from qagent.sandbox.mutacion import ERROR, OK, MutacionFuncion, ResultadoMutacion
from qagent.storage.registro import PERFIL_PROFUNDO

__all__ = ["PERFIL_PROFUNDO", "Mutador", "criticas_aprobadas", "mutar_modulo"]

Mutador = Callable[..., ResultadoMutacion]
Avisar = Callable[[str], None]

_registro = logging.getLogger("qagent.mutacion")


def criticas_aprobadas(resultado: ResultadoCorrida) -> list[ResultadoObjetivo]:
    """Funciones críticas del módulo cuya prueba aprobó el Reviewer."""
    return [o for o in _funciones_aprobadas(resultado) if o.critical]


def mutar_modulo(
    raiz: str | Path,
    imagen: str | None,
    modulo: dict[str, Any],
    resultado: ResultadoCorrida,
    tiempo_por_funcion_s: int,
    mutador: Mutador | None = None,
    avisar: Avisar | None = None,
    *,
    almacen: AlmacenProyecto | None = None,
    run_id: str | None = None,
    huellas: dict[tuple[str, str], str] | None = None,
) -> None:
    """Ejecuta mutmut sobre las funciones críticas aprobadas y anota el resultado.

    Deja en `objetivo.mutacion` de cada función crítica aprobada el estado, el Mutation
    Score, los detectados y los sobrevivientes. El tiempo máximo del contenedor es
    `tiempo_por_funcion_s` por cada función mutada.

    Args:
        raiz: carpeta del proyecto (se copia al sandbox; no se modifica).
        imagen: imagen del sandbox del proyecto.
        modulo: el módulo analizado (para la línea de cada función).
        resultado: resultado de las pruebas de ese módulo.
        tiempo_por_funcion_s: `[mutacion] tiempo_maximo_por_funcion_s` de config.toml.
        mutador: cómo se ejecuta mutmut (Docker; reemplazable en pruebas).
        avisar: recibe los mensajes para el Monitor.
        almacen: si se da junto con `huellas`, reutiliza y guarda resultados (#70).
        run_id: corrida actual, para guardar de dónde salió cada resultado.
        huellas: huella AST de cada `(modulo, funcion)` (`huellas_de_objetivos`).
    """
    objetivos = criticas_aprobadas(resultado)
    if not objetivos:
        return
    avisar = avisar or (lambda _mensaje: None)
    aprobadas = _funciones_aprobadas(resultado)
    # Las pruebas que se usan contra los mutantes son todas las aprobadas del módulo:
    # si cualquiera cambia, el resultado guardado deja de valer.
    huella_pruebas = huella_de_prueba(
        "\n".join(sorted(o.codigo or "" for o in aprobadas))
    )

    pendientes: list[ResultadoObjetivo] = []
    for objetivo in objetivos:
        guardado = _guardado(
            almacen, huellas, resultado.modulo, objetivo, huella_pruebas
        )
        if guardado is None:
            pendientes.append(objetivo)
            continue
        objetivo.mutacion = {
            **guardado["mutacion"],
            "reutilizada": True,
            "run_origen": guardado["run_id"],
        }
        avisar(
            f"{objetivo.objetivo}: Mutation Score {guardado['mutacion']['puntuacion']:g} % "
            f"reutilizado de la corrida {guardado['run_id']} (la función y sus pruebas "
            "no cambiaron)"
        )
    if not pendientes:
        return

    nombres = [o.objetivo for o in pendientes]
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
        for aprobada in aprobadas:
            archivo = nombre_prueba(id_de_spec(resultado.modulo, aprobada.objetivo))
            (Path(carpeta) / archivo).write_text(
                aprobada.codigo or "", encoding="utf-8"
            )
        try:
            por_funcion = (mutador or ejecutar_mutacion)(
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

    for objetivo in pendientes:
        mutacion = por_funcion.get(objetivo.objetivo) or MutacionFuncion(
            objetivo.objetivo,
            ERROR,
            mensaje="mutmut no devolvió resultado para esta función.",
        )
        objetivo.mutacion = a_dict(mutacion)
        avisar(texto_para_monitor(mutacion))
        _guardar(almacen, huellas, run_id, resultado.modulo, objetivo, huella_pruebas)


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


def _guardado(
    almacen: AlmacenProyecto | None,
    huellas: dict[tuple[str, str], str] | None,
    modulo: str,
    objetivo: ResultadoObjetivo,
    huella_pruebas: str,
) -> dict[str, Any] | None:
    """Resultado guardado de la función si sigue valiendo (#70)."""
    if almacen is None or huellas is None:
        return None
    return almacen.mutacion_vigente(
        id_de_spec(modulo, objetivo.objetivo),
        huellas.get((modulo, objetivo.objetivo)),
        huella_pruebas,
    )


def _guardar(
    almacen: AlmacenProyecto | None,
    huellas: dict[tuple[str, str], str] | None,
    run_id: str | None,
    modulo: str,
    objetivo: ResultadoObjetivo,
    huella_pruebas: str,
) -> None:
    """Guarda un resultado con puntuación para la próxima corrida (#70)."""
    mutacion = objetivo.mutacion or {}
    huella = (huellas or {}).get((modulo, objetivo.objetivo))
    if (
        almacen is None
        or run_id is None
        or huella is None
        or mutacion.get("estado") != OK
        or mutacion.get("puntuacion") is None
    ):
        return
    try:
        almacen.guardar_mutacion(
            id_de_spec(modulo, objetivo.objetivo),
            huella,
            huella_pruebas,
            mutacion,
            run_id,
        )
    except (ErrorAlmacen, OSError) as error:
        _registro.warning(
            "No se guardó la mutación de %s: %s", objetivo.objetivo, error
        )
