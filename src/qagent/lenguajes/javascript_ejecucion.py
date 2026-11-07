"""Comando y entorno de ejecución para pruebas JavaScript y TypeScript con Vitest (EP-11a).

Arma el comando de Vitest con reporter JUnit y cobertura coverage-v8,
asegurando ejecución sin red en el sandbox y respetando la estructura de carpetas.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from qagent.analysis.analyzer import calcular_huella
from qagent.lenguajes.javascript_estructura import extraer_funciones, gramatica_de
from qagent.lenguajes.treesitter import obtener_parser
from qagent.sandbox import LimitesSandbox
from qagent.sandbox.ejecucion import ARCHIVO_JUNIT, DIR_SALIDA, DIR_TESTS

#: Límites medidos de recursos para el contenedor de pruebas Node (CA2).
LIMITES_NODE = LimitesSandbox(cpus=4.0, memoria="2g", timeout_s=120)


def comando_vitest(modulo: str) -> list[str]:
    """Devuelve el comando de Vitest con reporte JUnit y cobertura coverage-v8.

    Ejecuta en modo no interactivo (`run`) sobre la carpeta de pruebas montada,
    con reporte JUnit en `/out/junit.xml` y cobertura en `/out/coverage-final.json`.
    """
    ruta_modulo = PurePosixPath(str(modulo).replace("\\", "/")).as_posix()
    return [
        "vitest",
        "run",
        DIR_TESTS,
        "--reporter=default",
        "--reporter=junit",
        f"--outputFile.junit={DIR_SALIDA}/{ARCHIVO_JUNIT}",
        f"--outputFile={DIR_SALIDA}/{ARCHIVO_JUNIT}",
        "--coverage.enabled=true",
        "--coverage.provider=v8",
        f"--coverage.include={ruta_modulo}",
        "--coverage.reporter=json",
        "--coverage.reporter=json-summary",
        f"--coverage.reportsDirectory={DIR_SALIDA}",
        "--no-color",
    ]


def variables_node() -> dict[str, str]:
    """Variables de entorno del contenedor al ejecutar pruebas Node en el sandbox."""
    return {
        "NODE_ENV": "test",
        "NO_COLOR": "1",
    }


def huellas_de_archivo_js(
    fuente: str, relativa: str, lenguaje: str
) -> dict[str, str] | None:
    """Calcula la huella tree-sitter de cada función exportada del módulo (HU-24, HU-25)."""
    try:
        arbol = obtener_parser(gramatica_de(relativa)).parse(fuente.encode("utf-8"))
        if arbol.root_node.has_error:
            return None
        funciones = extraer_funciones(arbol.root_node)
        return {
            f["nombre"]: calcular_huella(
                f"{lenguaje}-v1\n{relativa}\n{f['nombre']}\n{fuente}"
            )
            for f in funciones
        }
    except (ValueError, UnicodeError):
        return None
