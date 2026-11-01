"""Adaptadores de JavaScript y TypeScript (EN-17).

Análisis estático y validación de sintaxis con tree-sitter (SPK-04, ADR-009): las
funciones exportadas, su JSDoc, sus tipos, sus ramas y ``llama_a`` (#176).
El entorno del sandbox es la imagen ``qagent-sandbox:node`` (#169). El comando de Jest
o Vitest y la lectura de resultados lanzan ``NoImplementado`` hasta que se implementen
(ver ``README.md`` de este paquete).
"""

from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath
from typing import Any

from tree_sitter import Node

from qagent.analysis.analyzer import _resumen, calcular_huella
from qagent.lenguajes.base import (
    AdaptadorEnDesarrollo,
    EntornoSandbox,
    Estructura,
    ReglasPlanificacion,
)
from qagent.lenguajes.javascript_estructura import extraer_funciones, gramatica_de
from qagent.lenguajes.javascript_llamadas import agregar_llamadas
from qagent.lenguajes.javascript_oraculo import registro_de_evidencias
from qagent.lenguajes.registro import listar_archivos
from qagent.lenguajes.treesitter import (
    extraer_errores_sintaxis,
    obtener_parser,
    validar_sintaxis_js,
    validar_sintaxis_ts,
)
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


#: Carpetas de pruebas existentes del proyecto (``tests`` ya la ignora el registro).
CARPETAS_DE_PRUEBA = frozenset({"__tests__", "__mocks__", "test", "tests"})
#: ``precios.test.ts``, ``precios.spec.mjs``…
_ARCHIVO_DE_PRUEBA = re.compile(r"\.(test|spec)\.[cm]?[jt]sx?$", re.IGNORECASE)


def es_prueba(relativa: str) -> bool:
    """Si el archivo es una prueba que ya escribió el usuario (no se analiza)."""
    ruta = PurePosixPath(relativa)
    return bool(_ARCHIVO_DE_PRUEBA.search(ruta.name)) or any(
        parte in CARPETAS_DE_PRUEBA for parte in ruta.parts[:-1]
    )


class _AdaptadorNode(AdaptadorEnDesarrollo):
    """Análisis compartido de JavaScript y TypeScript; cada uno con sus extensiones."""

    def analizar(self, raiz: str | os.PathLike[str]) -> Estructura:
        """Lee las fuentes del lenguaje y devuelve lenguaje, módulos, errores y resumen.

        Misma forma que :func:`qagent.analysis.analizar_proyecto`: cada módulo trae
        ``ruta``, ``huella``, ``funciones`` exportadas (con ``llama_a`` y el
        registro de ``evidencias`` de ``oracle.v1``) y ``endpoints`` (vacío hasta
        que se analice Express). Omite ``node_modules``,
        ``dist``, carpetas ocultas, enlaces simbólicos y pruebas existentes. Los
        archivos ilegibles o con errores de sintaxis van a ``errores`` sin detener el
        resto. Nunca ejecuta ni transpila el código.

        Raises:
            NotADirectoryError: si ``raiz`` no es una carpeta existente.
        """
        carpeta = Path(raiz)
        modulos: list[dict[str, Any]] = []
        errores: list[dict[str, Any]] = []
        arboles: dict[str, Node] = {}
        for relativa in listar_archivos(carpeta):
            if not self.es_fuente(relativa) or es_prueba(relativa):
                continue
            archivo = carpeta / relativa
            if archivo.is_symlink() or any(
                p.is_symlink() for p in archivo.parents if p != carpeta.parent
            ):
                continue
            try:
                fuente = archivo.read_text(encoding="utf-8-sig")
                arbol = obtener_parser(gramatica_de(relativa)).parse(
                    fuente.encode("utf-8")
                )
                if arbol.root_node.has_error:
                    raise SyntaxError(
                        "; ".join(extraer_errores_sintaxis(arbol.root_node))
                        or "error de sintaxis"
                    )
                funciones = extraer_funciones(arbol.root_node)
                for funcion in funciones:
                    funcion["modulo"] = relativa
                    funcion["evidencias"] = registro_de_evidencias(funcion, relativa)
            except (OSError, UnicodeError, SyntaxError, RecursionError) as error:
                errores.append(_error(relativa, error))
                continue
            modulos.append(
                {
                    "ruta": relativa,
                    "huella": calcular_huella(fuente),
                    "funciones": funciones,
                    "endpoints": [],
                }
            )
            arboles[relativa] = arbol.root_node
        agregar_llamadas(modulos, arboles)
        return {
            "lenguaje": self.lenguaje,
            "modulos": modulos,
            "errores": errores,
            "resumen": _resumen(modulos, errores),
        }

    def objetivos(self, estructura: Estructura) -> list[dict[str, Any]]:
        """Funciones exportadas con ``critical``: al menos una decisión, como en Java."""
        return [
            {
                "modulo": m["ruta"],
                "tipo": "funcion",
                "objetivo": f["nombre"],
                "critical": f["ramas"] > 0,
            }
            for m in estructura.get("modulos", [])
            for f in m.get("funciones", [])
        ]

    def reglas_planificacion(self) -> ReglasPlanificacion:
        """Prompt Vitest y oráculo estricto desde JSDoc y tipos para el Planner (#176)."""
        from qagent.lenguajes import javascript_planificacion as reglas

        if self.lenguaje == "typescript":
            return reglas.REGLAS_PLANIFICACION_TYPESCRIPT
        return reglas.REGLAS_PLANIFICACION_JAVASCRIPT

    def entorno_sandbox(self) -> EntornoSandbox:
        return entorno_node()


def _error(relativa: str, causa: Exception) -> dict[str, Any]:
    """Describe por qué un archivo no se pudo analizar, con la primera línea citada."""
    mensaje = str(causa) if not isinstance(causa, SyntaxError) else causa.msg
    linea = re.search(r"línea (\d+)", mensaje or "")
    return {
        "ruta": relativa,
        "tipo": type(causa).__name__,
        "linea": int(linea[1]) if linea else None,
        "mensaje": mensaje,
    }


class JavaScriptAdapter(_AdaptadorNode):
    """JavaScript (Node) con Jest o Vitest; endpoints Express."""

    lenguaje = "javascript"
    nombre = "JavaScript"
    extensiones = (".js", ".mjs", ".cjs", ".jsx")
    marcadores = ("package.json",)
    frameworks_pruebas = ("vitest", "jest")
    frameworks_app = ("express",)

    def validar_sintaxis(self, codigo: str) -> list[str]:
        """Errores de sintaxis del código JavaScript parseado con tree-sitter.

        Devuelve una lista vacía si el código es válido, o la lista de errores
        con su número de línea si encuentra nodos ERROR o MISSING.
        """
        return validar_sintaxis_js(codigo)


class TypeScriptAdapter(_AdaptadorNode):
    """TypeScript con Jest o Vitest; endpoints Express."""

    lenguaje = "typescript"
    nombre = "TypeScript"
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
