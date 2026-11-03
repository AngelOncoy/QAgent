"""Interpretación de resultados PIT para métodos críticos de Java (#180).

Solo procesa XML: no ejecuta Java ni altera configuraciones del proyecto.
La ejecución acotada y su integración con Docker se implementan por separado.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

from qagent.sandbox.mutacion import (
    ERROR,
    OK,
    MutacionFuncion,
    ResultadoMutacion,
    Sobreviviente,
    puntuacion,
)

LIMITE_XML_PIT = 2_000_000
DETECTADOS = frozenset({"KILLED", "TIMED_OUT"})
SOBREVIVIENTES = frozenset({"SURVIVED", "NO_COVERAGE"})
INCOMPLETOS = frozenset(
    {"NON_VIABLE", "RUN_ERROR", "MEMORY_ERROR", "NOT_STARTED", "STARTED"}
)


def interpretar_pit(
    xml: str,
    modulo: str,
    objetivos: dict[str, tuple[str, str]],
) -> ResultadoMutacion:
    """Convierte mutations.xml en ResultadoMutacion sin deducir éxitos técnicos.

    Args:
        xml: contenido del informe PIT, no una ruta.
        modulo: ruta relativa de la fuente Java.
        objetivos: objetivo QAgent -> (clase binaria completa, nombre del método).
            Ejemplo: Banco.sumar -> (org.ejemplo.Banco, sumar). Debe proceder de
            los métodos críticos aprobados seleccionados, nunca de todo el proyecto.

    Returns:
        Resultados por objetivo con la fórmula común de puntuacion. KILLED y
        TIMED_OUT cuentan como detectados; SURVIVED y NO_COVERAGE, sobrevivientes.
        Un método sin mutantes evaluables queda sin score. Los estados técnicos
        incompletos producen error sin score para ese método. XML inválido,
        entidades, duplicados u objetivos fuera de alcance invalidan el informe.
        No se ejecuta código ni se convierten errores técnicos en mutantes muertos.
    """
    funciones = {nombre: MutacionFuncion(nombre, OK) for nombre in objetivos}
    resultado = ResultadoMutacion(modulo, funciones)
    try:
        if not objetivos or len(set(objetivos.values())) != len(objetivos):
            raise ValueError("La selección de métodos está vacía o es ambigua.")
        if not xml.strip() or len(xml.encode("utf-8")) > LIMITE_XML_PIT:
            raise ValueError("El XML de PIT está vacío o supera el tamaño permitido.")
        if "<!DOCTYPE" in xml or "<!ENTITY" in xml:
            raise ValueError("El XML de PIT declara entidades no permitidas.")
        raiz = ET.fromstring(xml)
        if raiz.tag != "mutations":
            raise ValueError("Se esperaba la raíz mutations de PIT.")
        seleccion = {par: nombre for nombre, par in objetivos.items()}
        vistos: set[tuple[Any, ...]] = set()
        for nodo in raiz:
            if nodo.tag != "mutation":
                raise ValueError("El informe contiene elementos ajenos a PIT.")
            clase = _campo(nodo, "mutatedClass")
            metodo = _campo(nodo, "mutatedMethod")
            nombre = seleccion.get((clase, metodo))
            if nombre is None:
                raise ValueError(
                    "PIT informó una mutación fuera de los métodos seleccionados."
                )
            estado = nodo.get("status")
            if estado not in DETECTADOS | SOBREVIVIENTES | INCOMPLETOS:
                raise ValueError("El informe contiene un estado PIT desconocido.")
            linea = int(_campo(nodo, "lineNumber"))
            if linea < 1:
                raise ValueError("PIT informó una línea inválida.")
            mutador = _campo(nodo, "mutator")
            descriptor = _campo(nodo, "methodDescription")
            indices = tuple(_campo(i, ".") for i in nodo.findall("indexes/index"))
            if not indices or any(not i.isdecimal() for i in indices):
                raise ValueError("PIT no proporcionó índices de mutación válidos.")
            identidad = (clase, metodo, descriptor, mutador, indices)
            if identidad in vistos:
                raise ValueError("El XML contiene mutantes duplicados.")
            vistos.add(identidad)
            funcion = funciones[nombre]
            if estado in INCOMPLETOS:
                funcion.estado = ERROR
                funcion.mensaje = (
                    f"PIT no pudo evaluar todos los mutantes del método ({estado})."
                )
            elif estado in DETECTADOS:
                funcion.detectados += 1
            else:
                funcion.sobrevivientes.append(
                    Sobreviviente(
                        mutante=f"{clase}.{metodo}{descriptor}:{mutador}:{','.join(indices)}",
                        linea=linea,
                        cambio=f"{estado}: {_campo(nodo, 'description')}",
                    )
                )
    except (ET.ParseError, ValueError) as error:
        resultado.funciones = {
            nombre: MutacionFuncion(nombre, ERROR, mensaje=str(error))
            for nombre in objetivos
        }
        return resultado
    for funcion in funciones.values():
        if funcion.estado == OK:
            funcion.puntuacion = puntuacion(
                funcion.detectados, len(funcion.sobrevivientes)
            )
            if funcion.puntuacion is None:
                funcion.mensaje = "PIT no generó mutantes evaluables para este método."
    return resultado


def _campo(nodo: ET.Element, nombre: str) -> str:
    """Lee un campo requerido y no vacío del XML; lanza ValueError si falta."""
    texto = nodo.findtext(nombre)
    if texto is None or not texto.strip():
        raise ValueError(f"Falta el campo requerido de PIT: {nombre}.")
    return texto.strip()
