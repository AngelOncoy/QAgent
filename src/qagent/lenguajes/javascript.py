"""Adaptadores de JavaScript y TypeScript (EN-17).

Análisis estático y validación de sintaxis con tree-sitter (SPK-04, ADR-009).
El comando de Jest o Vitest, el entorno del sandbox y la lectura de resultados
lanzan ``NoImplementado`` hasta que se implementen (ver ``README.md`` de este paquete).
"""

from __future__ import annotations

from qagent.lenguajes.base import AdaptadorEnDesarrollo
from qagent.lenguajes.treesitter import validar_sintaxis_js, validar_sintaxis_ts


class JavaScriptAdapter(AdaptadorEnDesarrollo):
    """JavaScript (Node) con Jest o Vitest; endpoints Express."""

    lenguaje = "javascript"
    extensiones = (".js", ".mjs", ".cjs", ".jsx")
    marcadores = ("package.json",)
    frameworks_pruebas = ("jest", "vitest")
    frameworks_app = ("express",)

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

    def validar_sintaxis(self, codigo: str) -> list[str]:
        """Errores de sintaxis del código TypeScript parseado con tree-sitter.

        Devuelve una lista vacía si el código es válido, o la lista de errores
        con su número de línea si encuentra nodos ERROR o MISSING.
        """
        return validar_sintaxis_ts(codigo)
