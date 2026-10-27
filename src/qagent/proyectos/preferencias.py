"""Preferencias persistentes de la vista Explorar para cada proyecto."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from qagent.almacenamiento.disco import (
    DatoCorrupto,
    DatoNoEncontrado,
    escribir_json_atomico,
    leer_json_objeto,
)

ARCHIVO_SELECCION = "seleccion_objetivos.json"
VERSION_SELECCION = 1


def guardar_seleccion_objetivos(
    ruta_proyecto: str | Path, seleccion: dict[str, Any]
) -> None:
    """Guarda la selección completa de Explorar dentro de ``.qagent``.

    Se conservan también los objetivos desmarcados para distinguir una selección
    vacía de la ausencia de preferencias. La escritura es atómica.
    """
    datos = _validar_seleccion(seleccion)
    ruta = Path(ruta_proyecto).resolve() / ".qagent" / ARCHIVO_SELECCION
    escribir_json_atomico(ruta, datos)


def cargar_seleccion_objetivos(
    ruta_proyecto: str | Path,
) -> dict[str, Any] | None:
    """Devuelve la selección del proyecto o ``None`` si aún no existe.

    Un archivo incompatible o corrupto se ignora de forma segura: Explorar puede
    usar sus valores iniciales y volver a guardarlos cuando la persona los cambie.
    """
    ruta = Path(ruta_proyecto).resolve() / ".qagent" / ARCHIVO_SELECCION
    try:
        return _validar_seleccion(leer_json_objeto(ruta))
    except (DatoNoEncontrado, DatoCorrupto, TypeError, ValueError):
        return None


def _validar_seleccion(seleccion: Any) -> dict[str, Any]:
    if not isinstance(seleccion, dict) or seleccion.get("version") != VERSION_SELECCION:
        raise ValueError("Versión de selección no compatible.")
    modulos = seleccion.get("modulos")
    if not isinstance(modulos, list):
        raise TypeError("La selección no contiene una lista de módulos.")

    normalizados: list[dict[str, Any]] = []
    rutas: set[str] = set()
    for modulo in modulos:
        if not isinstance(modulo, dict):
            raise TypeError("Módulo de selección inválido.")
        ruta = modulo.get("ruta")
        if not isinstance(ruta, str) or not ruta or ruta in rutas:
            raise ValueError("Ruta de módulo inválida o repetida.")
        rutas.add(ruta)
        normalizados.append(
            {
                "ruta": ruta,
                "incluido": _booleano(modulo.get("incluido")),
                "funciones": _objetivos(modulo.get("funciones"), "nombre"),
                "endpoints": _objetivos(modulo.get("endpoints"), "objetivo"),
            }
        )
    return {"version": VERSION_SELECCION, "modulos": normalizados}


def _objetivos(valor: Any, clave: str) -> list[dict[str, Any]]:
    if not isinstance(valor, list):
        raise TypeError("Lista de objetivos inválida.")
    vistos: set[str] = set()
    resultado: list[dict[str, Any]] = []
    for objetivo in valor:
        if not isinstance(objetivo, dict):
            raise TypeError("Objetivo inválido.")
        identidad = objetivo.get(clave)
        if not isinstance(identidad, str) or not identidad or identidad in vistos:
            raise ValueError("Identidad de objetivo inválida o repetida.")
        vistos.add(identidad)
        resultado.append(
            {
                clave: identidad,
                "incluido": _booleano(objetivo.get("incluido")),
                "critico": _booleano(objetivo.get("critico")),
            }
        )
    return resultado


def _booleano(valor: Any) -> bool:
    if not isinstance(valor, bool):
        raise TypeError("Estado de selección inválido.")
    return valor
