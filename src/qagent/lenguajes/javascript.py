"""Adaptadores de JavaScript y TypeScript (EN-17).

Análisis estático y validación de sintaxis con tree-sitter (SPK-04, ADR-009): las
funciones exportadas, su JSDoc, sus tipos, sus ramas y ``llama_a`` (#176).
El Generator escribe pruebas Vitest y el guardrail detecta Assertion Laundering en
``expect`` sin IA y antes de ejecutar (EP-11a, parte 2). El entorno del sandbox es la
imagen ``qagent-sandbox:node`` (#169). El comando de Vitest y la lectura de resultados
lanzan ``NoImplementado`` hasta la parte 3 (ver ``README.md`` de este paquete).
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
    ComandoSandbox,
    ComparacionAserciones,
    EntornoSandbox,
    Estructura,
    PlanArquitectura,
    ReglasPlanificacion,
    ReglasRevision,
)
from qagent.lenguajes.javascript_cobertura import leer_cobertura_v8
from qagent.lenguajes.javascript_componentes import (
    AVISO_NO_SOPORTADOS,
    FRAMEWORK_REACT,
    detectar_framework_ui,
    separar_componentes,
)
from qagent.lenguajes.javascript_ejecucion import (
    comando_vitest,
    funciones_de_modulo_js,
    huellas_de_archivo_js,
    variables_node,
)
from qagent.lenguajes.javascript_estructura import (
    describir,
    exportadas,
    gramatica_de,
)
from qagent.lenguajes.javascript_junit import interpretar_resultados_vitest
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
    "dependency-cruiser",
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

    e2e_humo_disponible = True
    huellas_disponibles = True
    motor_mutacion = "Stryker"

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
                logica, componentes = separar_componentes(
                    arbol.root_node, exportadas(arbol.root_node)
                )
                funciones = [describir(e) for e in logica]
                for funcion in funciones:
                    funcion["modulo"] = relativa
                    funcion["evidencias"] = registro_de_evidencias(funcion, relativa)
            except (OSError, UnicodeError, SyntaxError, RecursionError) as error:
                errores.append(_error(relativa, error))
                continue
            modulo: dict[str, Any] = {
                "ruta": relativa,
                "huella": calcular_huella(fuente),
                "funciones": funciones,
                "endpoints": [],
            }
            if componentes:  # #171: solo aparece si el archivo exporta componentes
                for componente in componentes:
                    componente["modulo"] = relativa
                modulo["componentes"] = componentes
            modulos.append(modulo)
            arboles[relativa] = arbol.root_node
        agregar_llamadas(modulos, arboles)
        estructura: Estructura = {
            "lenguaje": self.lenguaje,
            "modulos": modulos,
            "errores": errores,
            "resumen": _resumen(modulos, errores),
        }
        framework_ui = _framework_ui(carpeta, modulos)
        if framework_ui is not None:
            estructura["framework_ui"] = framework_ui
        return estructura

    def objetivos(self, estructura: Estructura) -> list[dict[str, Any]]:
        """Funciones exportadas con ``critical`` (al menos una decisión, como en Java)
        y, si el proyecto usa React, sus componentes (#171), que nunca se mutan."""
        objetivos = [
            {
                "modulo": m["ruta"],
                "tipo": "funcion",
                "objetivo": f["nombre"],
                "critical": f["ramas"] > 0,
            }
            for m in estructura.get("modulos", [])
            for f in m.get("funciones", [])
        ]
        if (estructura.get("framework_ui") or {}).get("soportado"):
            objetivos.extend(
                {
                    "modulo": m["ruta"],
                    "tipo": "componente",
                    "objetivo": c["nombre"],
                    "critical": False,
                }
                for m in estructura.get("modulos", [])
                for c in m.get("componentes", [])
            )
        return objetivos

    def reglas_planificacion(self) -> ReglasPlanificacion:
        """Prompt Vitest y oráculo estricto desde JSDoc y tipos para el Planner (#176)."""
        from qagent.lenguajes import javascript_planificacion as reglas

        if self.lenguaje == "typescript":
            return reglas.REGLAS_PLANIFICACION_TYPESCRIPT
        return reglas.REGLAS_PLANIFICACION_JAVASCRIPT

    def entorno_sandbox(
        self, raiz: str | os.PathLike[str] | None = None
    ) -> EntornoSandbox:
        return entorno_node()

    def comando_pruebas(self, modulo: str, framework: str | None = None) -> list[str]:
        """Comando de Vitest con reporte JUnit y cobertura coverage-v8."""
        self.elegir_framework(framework)
        return comando_vitest(modulo)

    def variables_pruebas(self) -> dict[str, str]:
        """Variables de entorno para el contenedor Node."""
        return variables_node()

    def interpretar_resultados(self, informe: str) -> dict[str, Any]:
        """Convierte el informe de Vitest (JUnit XML o JSON) a resultados comunes."""
        return interpretar_resultados_vitest(informe)

    def leer_cobertura(
        self, dir_salida: str | os.PathLike[str]
    ) -> dict[str, Any] | None:
        """Lee la cobertura v8/Istanbul de dir_salida y la pasa a files/totals comunes."""
        return leer_cobertura_v8(dir_salida)

    # --- Generación y guardrail Vitest (EP-11a, parte 2) -----------------------------

    def prompt_generator(
        self,
        contrato: dict[str, Any],
        intento: int,
        feedback: str | None,
        ruta_proyecto: Path | None,
    ) -> str:
        """Prompt Vitest con el oráculo del contrato y el import del módulo."""
        from qagent.lenguajes.javascript_generacion import prompt_vitest

        return prompt_vitest(contrato, intento, feedback, ruta_proyecto)

    def reglas_revision(self) -> ReglasRevision:
        """Sintaxis y oráculo de la prueba Vitest para el Generator y el Reviewer."""
        from qagent.lenguajes.javascript_generacion import ReglasRevisionVitest

        return ReglasRevisionVitest(self.lenguaje)

    def archivo_de_prueba(self, objetivo: str) -> str:
        """``generado.test.ts`` o ``generado.test.js``: cada prueba corre aislada."""
        from qagent.lenguajes.javascript_generacion import archivo_vitest

        return archivo_vitest(self.lenguaje)

    def archivo_para_contrato(
        self, contrato: dict[str, Any], ruta_proyecto: Path | None
    ) -> str:
        """El archivo de la prueba queda en ``generated_test.v2``."""
        return self.archivo_de_prueba(contrato["objetivo"])

    def comparar_aserciones(
        self, original: str, reparado: str
    ) -> ComparacionAserciones:
        """Assertion Laundering en ``expect`` entre intentos, con tree-sitter y sin IA."""
        from qagent.lenguajes.javascript_laundering import comparar_vitest

        return comparar_vitest(original, reparado, self.lenguaje)

    def rutas_web(self, raiz: Path) -> tuple[list[Any], list[str], str]:
        """Delega la detección web estática compartida por JavaScript y TypeScript."""
        from qagent.lenguajes.javascript_rutas import detectar_rutas_web

        return detectar_rutas_web(raiz, self.extensiones)

    def huellas_de_archivo(self, fuente: str, relativa: str) -> dict[str, str] | None:
        """Huella tree-sitter de cada función exportada (HU-24, HU-25, #179)."""
        return huellas_de_archivo_js(fuente, relativa, self.lenguaje)

    def funciones_de_modulo(self, raiz: Path, modulo: str) -> list[dict[str, Any]]:
        """Nombre y línea de las funciones exportadas del módulo (#179)."""
        return funciones_de_modulo_js(raiz, modulo)

    def comando_mutacion(
        self,
        modulo: str,
        funciones: list[str],
        rangos: dict[str, tuple[int, int]] | None = None,
    ) -> ComandoSandbox:
        """Comando de Stryker acotado a los rangos de líneas de funciones críticas (#179)."""
        from qagent.sandbox.stryker_comando import comando_stryker

        return comando_stryker(modulo, funciones, rangos=rangos)

    def ejecutar_mutacion(self, *args: Any, **opciones: Any) -> Any:
        """Muta las funciones críticas con Stryker en el sandbox Docker (#179)."""
        from qagent.sandbox.stryker_ejecucion import ejecutar_stryker

        return ejecutar_stryker(*args, **opciones)


def _framework_ui(
    carpeta: Path, modulos: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Framework de interfaz del proyecto y cuántos componentes tiene (#171).

    Con React los componentes se prueban. Con otro framework, o con componentes JSX
    sin React en ``package.json``, solo se prueban los archivos de lógica y el
    informe dice «componentes no soportados» (ADR-010, sección 10.6).
    """
    total = sum(len(m.get("componentes", [])) for m in modulos)
    framework = detectar_framework_ui(carpeta)
    if framework is None and total:
        framework = {
            "framework": None,
            "nombre": "JSX sin React en package.json",
            "soportado": False,
            "aviso": AVISO_NO_SOPORTADOS,
        }
    if framework is None:
        return None
    framework["componentes"] = total
    framework["verificables"] = sum(
        1
        for m in modulos
        for c in m.get("componentes", [])
        if c["verificable"] and framework["framework"] == FRAMEWORK_REACT
    )
    return framework


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
    # Vitest (EP-11a) y mutación con Stryker (EP-11c), ADR-010.
    tipos_prueba_previstos = ("funcion", "mutacion")

    def validar_sintaxis(self, codigo: str) -> list[str]:
        """Errores de sintaxis del código JavaScript parseado con tree-sitter.

        Devuelve una lista vacía si el código es válido, o la lista de errores
        con su número de línea si encuentra nodos ERROR o MISSING.
        """
        return validar_sintaxis_js(codigo)

    def traducir_reglas_arquitectura(
        self, reglas: list[dict[str, Any]], raiz: Path
    ) -> list[PlanArquitectura]:
        from qagent.arquitectura.traduccion import traducir_node

        return traducir_node(reglas, raiz, self.lenguaje)


class TypeScriptAdapter(_AdaptadorNode):
    """TypeScript con Jest o Vitest; endpoints Express."""

    lenguaje = "typescript"
    nombre = "TypeScript"
    extensiones = (".ts", ".tsx", ".mts", ".cts")
    marcadores = ("tsconfig.json",)
    frameworks_pruebas = ("vitest", "jest")
    frameworks_app = ("express",)
    # Vitest (EP-11a) y mutación con Stryker (EP-11c), ADR-010.
    tipos_prueba_previstos = ("funcion", "mutacion")

    def es_fuente(self, archivo: str) -> bool:
        """Los ``.d.ts`` solo declaran tipos: no tienen código que probar."""
        return super().es_fuente(archivo) and not archivo.lower().endswith(".d.ts")

    def validar_sintaxis(self, codigo: str) -> list[str]:
        """Errores de sintaxis del código TypeScript parseado con tree-sitter.

        Devuelve una lista vacía si el código es válido, o la lista de errores
        con su número de línea si encuentra nodos ERROR o MISSING.
        """
        return validar_sintaxis_ts(codigo)

    def traducir_reglas_arquitectura(
        self, reglas: list[dict[str, Any]], raiz: Path
    ) -> list[PlanArquitectura]:
        from qagent.arquitectura.traduccion import traducir_node

        return traducir_node(reglas, raiz, self.lenguaje)
