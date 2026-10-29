"""Adaptadores de JavaScript y TypeScript (EN-17).

Análisis estático y validación de sintaxis con tree-sitter (SPK-04, ADR-009).
El entorno del sandbox es la imagen ``qagent-sandbox:node`` (#169). El comando de Jest
o Vitest y la lectura de resultados lanzan ``NoImplementado`` hasta que se implementen
(ver ``README.md`` de este paquete).
"""

from __future__ import annotations

from qagent.lenguajes.base import AdaptadorEnDesarrollo, EntornoSandbox
from qagent.lenguajes.treesitter import validar_sintaxis_js, validar_sintaxis_ts
from qagent.sandbox.ejecucion import ARCHIVO_JUNIT, DIR_SALIDA, DIR_TESTS
from qagent.sandbox.modelos import IMAGEN_NODE

#: Herramientas que trae ``qagent-sandbox:node`` (``sandbox/Dockerfile.node``).
PAQUETES_NODE = (
    "vitest",
    "@vitest/coverage-v8",
    "@stryker-mutator/core",
    "@stryker-mutator/vitest-runner",
    "typescript",
)


def entorno_node() -> EntornoSandbox:
    """Entorno del sandbox de JavaScript y TypeScript: la misma imagen de Node."""
    return EntornoSandbox(
        imagen=IMAGEN_NODE,
        paquetes_base=PAQUETES_NODE,
        dir_tests=DIR_TESTS,
        dir_salida=DIR_SALIDA,
        informe=ARCHIVO_JUNIT,
    )


class JavaScriptAdapter(AdaptadorEnDesarrollo):
    """JavaScript (Node) con Jest o Vitest; endpoints Express."""

    lenguaje = "javascript"
    extensiones = (".js", ".mjs", ".cjs", ".jsx")
    marcadores = ("package.json",)
    frameworks_pruebas = ("jest", "vitest")
    frameworks_app = ("express",)

    def entorno_sandbox(self) -> EntornoSandbox:
        return entorno_node()

    def validar_sintaxis(self, codigo: str) -> list[str]:
        """Errores de sintaxis del código JavaScript parseado con tree-sitter.

        Devuelve una lista vacía si el código es válido, o la lista de errores
        con su número de línea si encuentra nodos ERROR o MISSING.
        """
        return validar_sintaxis_js(codigo)


class TypeScriptAdapter(AdaptadorEnDesarrollo):
    """TypeScript con Jest o Vitest; endpoints Express."""

    lenguaje = "typescript"
    extensiones = (".ts", ".tsx", ".mts", ".cts")
    marcadores = ("tsconfig.json",)
    frameworks_pruebas = ("vitest", "jest")
    frameworks_app = ("express",)

    def es_fuente(self, archivo: str) -> bool:
        """Los ``.d.ts`` solo declaran tipos: no tienen código que probar."""
        return super().es_fuente(archivo) and not archivo.lower().endswith(".d.ts")

    def entorno_sandbox(self) -> EntornoSandbox:
        return entorno_node()

    def validar_sintaxis(self, codigo: str) -> list[str]:
        """Errores de sintaxis del código TypeScript parseado con tree-sitter.

        Devuelve una lista vacía si el código es válido, o la lista de errores
        con su número de línea si encuentra nodos ERROR o MISSING.
        """
        return validar_sintaxis_ts(codigo)
