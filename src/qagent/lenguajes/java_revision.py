"""Decisiones de ejecución Java basadas en etapas Maven e informes JUnit (#182).

No sustituye la validación del oráculo ni el guardrail de generación de #184.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from qagent.lenguajes.base import Clasificacion, NoImplementado
from qagent.lenguajes.java_ejecucion import MARCA
from qagent.lenguajes.java_junit import interpretar_junit_java
from qagent.lenguajes.treesitter import extraer_errores_sintaxis, obtener_parser
from qagent.sandbox.informe_pytest import JUnitInvalido
from qagent.sandbox.modelos import ResultadoSandbox


def clasificar_java(resultado: ResultadoSandbox) -> Clasificacion | None:
    """Distingue errores técnicos y aserciones; nunca acepta suites vacías u omitidas.

    La etapa proyecto impide regenerar una prueba para corregir código ajeno.
    Un fallo de compilación en la etapa prueba consume un intento del Generator.
    Un timeout, OOM o XML ausente/incoherente no demuestra un bug.
    """

    def sin(motivo: str, detalle: str) -> Clasificacion:
        return Clasificacion("entorno", detalle, motivo)

    if resultado.timed_out:
        return sin("timeout_sandbox", "Java excedió el tiempo máximo del sandbox.")
    if resultado.oom_killed:
        return sin("memoria_sandbox", "Java excedió la memoria del sandbox.")
    salida = resultado.stdout + "\n" + resultado.stderr
    etapas = re.findall(
        re.escape(MARCA) + r"(proyecto|prueba|ejecucion|cobertura)\b", salida
    )
    etapa = etapas[-1] if etapas else None
    if etapa == "proyecto":
        return sin(
            "error_compilacion_proyecto",
            "El proyecto Java no pudo compilarse o prepararse. " + salida[-4000:],
        )
    if etapa == "prueba":
        return Clasificacion(
            "error_test", "La prueba Java no compila: " + salida[-4000:]
        )
    if etapa == "cobertura":
        return sin(
            "error_cobertura",
            "No se pudo producir el informe JaCoCo. " + salida[-4000:],
        )
    try:
        informe = interpretar_junit_java(resultado.junit_xml or "")
    except JUnitInvalido:
        return sin(
            "informe_pruebas_invalido",
            "No hay un informe JUnit válido para juzgar el método. " + salida[-4000:],
        )
    if informe["total"] == informe["omitidos"]:
        return sin(
            "pruebas_no_ejecutadas", "JUnit omitió todas las pruebas del objetivo."
        )
    if informe["errores"]:
        return sin(
            "error_ejecucion_pruebas",
            "JUnit informó errores técnicos; no prueban un incumplimiento del contrato.",
        )
    if not informe["fallaron"]:
        if resultado.exit_code != 0:
            return sin(
                "salida_runner_incoherente", "JUnit pasó, pero Maven terminó con error."
            )
        return None
    if resultado.exit_code != 1:
        return sin(
            "salida_runner_incoherente",
            "JUnit informó fallos con un código de salida inesperado.",
        )
    tipos = {c.get("tipo_error") for c in informe["casos"] if c["resultado"] == "fallo"}
    if tipos <= {
        "org.opentest4j.AssertionFailedError",
        "org.opentest4j.MultipleFailuresError",
        "java.lang.AssertionError",
    }:
        return Clasificacion(
            "fallo_asercion", "La aserción JUnit del contrato no se cumplió."
        )
    return sin(
        "fallo_junit_no_clasificado",
        "JUnit informó un fallo que no se reconoce como aserción del contrato.",
    )


class ReglasRevisionJava:
    """Sintaxis y ubicación estáticas; el oráculo de #184 continúa obligatorio."""

    def error_de_sintaxis(self, codigo: str) -> str | None:
        """Devuelve errores del parser Java sin compilar ni ejecutar el test."""
        raiz = obtener_parser("java").parse(codigo.encode("utf-8")).root_node
        return "; ".join(extraer_errores_sintaxis(raiz)) if raiz.has_error else None

    def validar_oraculo(self, contrato: dict[str, Any], codigo: str) -> str | None:
        """Exige la implementación del guardrail en #184, sin aprobar por defecto."""
        raise NoImplementado("java", "validar_oraculo (#184)")

    def clasificar_salida(
        self, salida: str, contrato: dict[str, Any], raiz: Path
    ) -> Clasificacion | None:
        """La clasificación Java requiere ResultadoSandbox y su XML, no solo texto."""
        return None

    def rango_de_objetivo(
        self, raiz: Path, modulo: str, nombre: str
    ) -> tuple[int, int] | None:
        """Ubica un método por clase y nombre; una sobrecarga no elige al azar."""
        from qagent.lenguajes.java import JavaAdapter

        estructura = JavaAdapter().analizar(raiz)
        funcion = next(
            (
                f
                for m in estructura["modulos"]
                if m["ruta"] == modulo
                for f in m["funciones"]
                if f["nombre"] == nombre
            ),
            None,
        )
        if funcion is None:
            return None
        # El rango se usa para mostrar líneas no cubiertas; las métricas se leen
        # directamente de los contadores exactos JaCoCo del método.
        arbol = obtener_parser("java").parse((raiz / modulo).read_bytes()).root_node
        pendientes = [arbol]
        while pendientes:
            nodo = pendientes.pop()
            if (
                nodo.type == "method_declaration"
                and nodo.start_point.row + 1 == funcion["linea"]
            ):
                return nodo.start_point.row + 1, nodo.end_point.row + 1
            pendientes.extend(nodo.named_children)
        return None
