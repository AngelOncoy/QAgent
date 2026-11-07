"""Interpretación del informe JSON de Stryker para funciones críticas de JS/TS (#179).

Convierte el reporte `mutation.json` de Stryker en `ResultadoMutacion` común,
identificando mutantes detectados, sobrevivientes (con línea y cambio antes → después)
y calculando el Mutation Score con la fórmula de `puntuacion`.
"""

from __future__ import annotations

import json
from typing import Any

from qagent.sandbox.mutacion import (
    ERROR,
    OK,
    MutacionFuncion,
    ResultadoMutacion,
    Sobreviviente,
    puntuacion,
)

LIMITE_JSON_STRYKER = 5_000_000
DETECTADOS = frozenset({"Killed", "Timeout", "TimedOut"})
SOBREVIVIENTES = frozenset({"Survived", "NoCoverage"})
ERRORES = frozenset({"CompileError", "RuntimeError"})


def _extraer_original(fuente: str, location: dict[str, Any]) -> str:
    """Extrae el texto original mutado a partir de las coordenadas de `location`."""
    if not fuente or not location:
        return ""
    start = location.get("start") or {}
    end = location.get("end") or {}
    l1, c1 = start.get("line", 1) - 1, start.get("column", 1) - 1
    l2, c2 = end.get("line", 1) - 1, end.get("column", 1) - 1

    lineas = fuente.splitlines(keepends=True)
    if not (0 <= l1 < len(lineas) and 0 <= l2 < len(lineas)):
        return ""

    if l1 == l2:
        return lineas[l1][c1:c2].strip()

    trozo = lineas[l1][c1:] + "".join(lineas[l1 + 1 : l2]) + lineas[l2][:c2]
    return trozo.strip()


def interpretar_stryker(
    informe: dict[str, Any] | str,
    modulo: str,
    funciones: list[str],
    rangos: dict[str, tuple[int, int]] | None = None,
) -> ResultadoMutacion:
    """Convierte el informe de Stryker en ResultadoMutacion por función crítica.

    Args:
        informe: diccionario o cadena JSON del reporte de Stryker.
        modulo: ruta relativa del archivo en el proyecto.
        funciones: nombres de las funciones críticas analizadas.
        rangos: mapeo `{nombre: (inicio, fin)}` de líneas de cada función.

    Returns:
        ResultadoMutacion con el Mutation Score y sobrevivientes por función.
    """
    por_funcion = {nombre: MutacionFuncion(nombre, OK) for nombre in funciones}
    resultado = ResultadoMutacion(modulo=modulo, funciones=por_funcion)

    if not funciones:
        return resultado

    if isinstance(informe, str):
        if not informe.strip() or len(informe.encode("utf-8")) > LIMITE_JSON_STRYKER:
            resultado.funciones = {
                f: MutacionFuncion(
                    f,
                    ERROR,
                    mensaje="El informe de Stryker está vacío o supera el límite.",
                )
                for f in funciones
            }
            return resultado
        try:
            datos = json.loads(informe)
        except json.JSONDecodeError as error:
            resultado.funciones = {
                f: MutacionFuncion(
                    f, ERROR, mensaje=f"Error parseando JSON de Stryker: {error}"
                )
                for f in funciones
            }
            return resultado
    else:
        datos = informe or {}

    archivos: dict[str, Any] = datos.get("files") or {}
    modulo_posix = modulo.replace("\\", "/").removeprefix("./")

    # Localizar la entrada del archivo normalizando posibles prefijos
    archivo_entry: dict[str, Any] | None = None
    for ruta, entry in archivos.items():
        normalizada = ruta.replace("\\", "/").removeprefix("./")
        if normalizada == modulo_posix or normalizada.endswith("/" + modulo_posix):
            archivo_entry = entry
            break

    if archivo_entry is None:
        # Si no hubo archivo de reporte para este módulo, dejamos sin score
        for funcion in por_funcion.values():
            funcion.puntuacion = None
            funcion.mensaje = "Stryker no generó mutantes evaluables para esta función."
        return resultado

    fuente: str = archivo_entry.get("source") or ""
    mutantes: list[dict[str, Any]] = archivo_entry.get("mutants") or []

    for m in mutantes:
        status = m.get("status")
        location = m.get("location") or {}
        linea = location.get("start", {}).get("line")
        mutator = m.get("mutatorName") or "Mutant"
        mutant_id = str(m.get("id", ""))
        nombre_mutante = f"{mutator}_{mutant_id}" if mutant_id else mutator

        # Encontrar a qué función pertenece este mutante
        funcion_destino: MutacionFuncion | None = None
        if rangos and linea is not None:
            for nom, (ini, fin) in rangos.items():
                if ini <= linea <= fin:
                    funcion_destino = por_funcion.get(nom)
                    break
        elif len(funciones) == 1:
            funcion_destino = por_funcion.get(funciones[0])

        if funcion_destino is None:
            continue

        if status in ERRORES:
            funcion_destino.estado = ERROR
            funcion_destino.mensaje = (
                f"Stryker no pudo evaluar todos los mutantes de la función ({status})."
            )
        elif status in DETECTADOS:
            funcion_destino.detectados += 1
        elif status in SOBREVIVIENTES:
            original = _extraer_original(fuente, location)
            replacement = m.get("replacement")
            if original and replacement is not None:
                cambio = f"{original} → {replacement}"
            elif replacement is not None:
                cambio = f"→ {replacement}"
            else:
                cambio = f"{status}: {mutator}"

            funcion_destino.sobrevivientes.append(
                Sobreviviente(
                    mutante=nombre_mutante,
                    linea=linea,
                    cambio=cambio,
                )
            )

    # Calcular Mutation Score por función
    for funcion in por_funcion.values():
        if funcion.estado == OK:
            funcion.puntuacion = puntuacion(
                funcion.detectados, len(funcion.sobrevivientes)
            )
            if funcion.puntuacion is None:
                funcion.mensaje = (
                    "Stryker no generó mutantes evaluables para esta función."
                )

    return resultado
