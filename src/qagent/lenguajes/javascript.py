"""Adaptadores de JavaScript y TypeScript (EN-17): por ahora solo detectan.

Punto de partida del responsable de JS/TS. El análisis, el comando de Jest o
Vitest, el entorno del sandbox y la lectura de resultados lanzan
``NoImplementado`` hasta que se implementen (ver ``README.md`` de este paquete).
El análisis estático usa tree-sitter (decisión de SPK-04, ADR-007).
"""

from __future__ import annotations

from qagent.lenguajes.base import AdaptadorEnDesarrollo


class JavaScriptAdapter(AdaptadorEnDesarrollo):
    """JavaScript (Node) con Jest o Vitest; endpoints Express."""

    lenguaje = "javascript"
    extensiones = (".js", ".mjs", ".cjs", ".jsx")
    marcadores = ("package.json",)
    frameworks_pruebas = ("jest", "vitest")
    frameworks_app = ("express",)


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
