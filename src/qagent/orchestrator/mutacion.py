"""Mutation testing de las funciones críticas aprobadas (EN-09, #70).

Corre después de que las pruebas de un módulo quedaron aprobadas: en el perfil Profundo,
al terminar el Reviewer; en «Repetir pruebas guardadas + profundizar» (`reg_deep`), al
volver a ejecutar las pruebas guardadas. mutmut solo se aplica a las funciones con
`critical: true` (HU-06) cuya prueba pasó, nunca al repositorio completo (RN-04). Usa
como pruebas las aprobadas de las funciones del módulo y no llama a ningún agente de IA
(0 tokens). Un fallo de mutmut nunca detiene la corrida: queda registrado en la función
con su motivo.

En el perfil Profundo también se mutan los endpoints FastAPI marcados como prioritarios
(#74): solo el código de su manejador, con las pruebas de endpoint (`TestClient`) y de
función aprobadas del módulo. Al repetir pruebas guardadas no (fuera del alcance de #74).

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
from qagent.sandbox import LIMITES_POR_DEFECTO, LimitesSandbox, ejecutar_mutacion
from qagent.sandbox.mutacion import ERROR, OK, MutacionFuncion, ResultadoMutacion
from qagent.storage.registro import PERFIL_PROFUNDO

__all__ = ["PERFIL_PROFUNDO", "Mutador", "criticas_aprobadas", "mutar_modulo"]

Mutador = Callable[..., ResultadoMutacion]
Avisar = Callable[[str], None]

_registro = logging.getLogger("qagent.mutacion")


def criticas_aprobadas(
    resultado: ResultadoCorrida, con_endpoints: bool = False
) -> list[ResultadoObjetivo]:
    """Funciones críticas (y, si se pide, endpoints prioritarios) aprobados del módulo."""
    return [
        o
        for o in _aprobadas(resultado)
        if o.critical and (con_endpoints or _tipo(o) == "funcion")
    ]


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
    con_endpoints: bool = True,
    limites: LimitesSandbox = LIMITES_POR_DEFECTO,
) -> None:
    """Ejecuta mutmut sobre las funciones críticas aprobadas y anota el resultado.

    Deja en `objetivo.mutacion` de cada función crítica aprobada (y de cada endpoint
    prioritario aprobado, #74) el estado, el Mutation Score, los detectados y los
    sobrevivientes. El tiempo máximo del contenedor es `tiempo_por_funcion_s` por cada
    función o manejador mutado.

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
        huellas: huella AST de cada `(modulo, objetivo)` (`huellas_de_objetivos`).
        con_endpoints: si también se mutan los manejadores de los endpoints
            prioritarios (#74). La regresión (`reg_deep`) no los muta.
        limites: CPU y memoria de `[sandbox]` en config.toml; el tiempo máximo se
            reemplaza por el de la mutación.
    """
    objetivos = criticas_aprobadas(resultado, con_endpoints)
    if not objetivos:
        return
    avisar = avisar or (lambda _mensaje: None)
    aprobadas = _aprobadas(resultado)
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

    nombres = [o.objetivo for o in pendientes if _tipo(o) == "funcion"]
    # Un manejador puede atender varias rutas: se muta una sola vez (#74).
    manejadores = list(
        dict.fromkeys(_manejador(o) for o in pendientes if _tipo(o) == "endpoint")
    )
    inicios = {
        f["nombre"]: f["linea"]
        for f in [*(modulo.get("funciones") or []), *_manejadores_de(modulo)]
        if isinstance(f.get("linea"), int)
    }
    limites = replace(
        limites,
        timeout_s=tiempo_por_funcion_s * (len(nombres) + len(manejadores)),
    )
    avisar(_texto_inicio(pendientes, len(nombres)))
    opciones: dict[str, Any] = {"inicios": inicios}
    if manejadores:
        opciones["manejadores"] = manejadores

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
                **opciones,
            ).funciones
        except Exception as error:  # noqa: BLE001 — mutmut nunca detiene la corrida
            _registro.warning("mutmut falló en %s: %s", resultado.modulo, error)
            por_funcion = {
                nombre: MutacionFuncion(
                    nombre, ERROR, mensaje=f"mutmut no pudo ejecutarse: {error}"
                )
                for nombre in [*nombres, *manejadores]
            }

    for objetivo in pendientes:
        clave = (
            _manejador(objetivo) if _tipo(objetivo) == "endpoint" else objetivo.objetivo
        )
        encontrada = por_funcion.get(clave)
        mutacion = (
            replace(encontrada, funcion=objetivo.objetivo)
            if encontrada is not None
            else MutacionFuncion(
                objetivo.objetivo,
                ERROR,
                mensaje="mutmut no devolvió resultado para este objetivo.",
            )
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


def _aprobadas(resultado: ResultadoCorrida) -> list[ResultadoObjetivo]:
    """Objetivos aprobados con prueba: sus pruebas se usan contra los mutantes."""
    return [o for o in resultado.objetivos if o.decision == "accept" and o.codigo]


def _tipo(objetivo: ResultadoObjetivo) -> str:
    return (objetivo.contrato or {}).get("tipo", "funcion")


def _manejador(objetivo: ResultadoObjetivo) -> str:
    """Función que atiende el endpoint (del contrato del Planner)."""
    return (objetivo.contrato or {}).get("manejador") or objetivo.objetivo


def _manejadores_de(modulo: dict[str, Any]) -> list[dict[str, Any]]:
    """Línea del `def` de cada manejador, con la forma de una función del análisis."""
    return [
        {"nombre": e.get("manejador"), "linea": e.get("linea")}
        for e in modulo.get("endpoints") or []
        if e.get("manejador")
    ]


def _texto_inicio(pendientes: list[ResultadoObjetivo], funciones: int) -> str:
    endpoints = len(pendientes) - funciones
    partes = []
    if funciones:
        partes.append(f"{funciones} función(es) crítica(s)")
    if endpoints:
        partes.append(f"{endpoints} endpoint(s) prioritario(s)")
    return (
        f"Mutation testing (mutmut) sobre {' y '.join(partes)}: "
        f"{', '.join(o.objetivo for o in pendientes)} · 0 tokens"
    )


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
