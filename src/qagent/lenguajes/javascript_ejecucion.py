"""Comando y entorno de ejecución para pruebas JavaScript y TypeScript con Vitest (EP-11a).

Arma el comando de Vitest con reporter JUnit y cobertura coverage-v8,
asegurando ejecución sin red en el sandbox y respetando la estructura de carpetas.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from qagent.analysis.analyzer import calcular_huella
from qagent.lenguajes.javascript_estructura import extraer_funciones, gramatica_de
from qagent.lenguajes.treesitter import obtener_parser
from qagent.sandbox import LimitesSandbox
from qagent.sandbox.ejecucion import ARCHIVO_JUNIT, DIR_PROYECTO, DIR_SALIDA, DIR_TESTS

#: Límites medidos de recursos para el contenedor de pruebas Node (CA2).
LIMITES_NODE = LimitesSandbox(cpus=4.0, memoria="2g", timeout_s=120)


def comando_vitest(modulo: str) -> list[str]:
    """Devuelve el comando de Vitest con reporte JUnit y cobertura coverage-v8.

    Ejecuta en modo no interactivo (`run`) sobre la carpeta de pruebas montada,
    con reporte JUnit en `/out/junit.xml` y cobertura en `/out/coverage-final.json`.

    La raíz de Vitest es `/work`, que contiene la copia del proyecto y las pruebas:
    con la raíz en el proyecto, Vite no sirve `/work/tests` en jsdom (#171) y no
    encuentra las pruebas. Por eso la cobertura se filtra con `proyecto/<módulo>`.
    El sistema de archivos del contenedor es de solo lectura: sin caché de módulos
    en disco y sin borrar `/out`, que es un montaje.
    """
    ruta_modulo = PurePosixPath(str(modulo).replace("\\", "/")).as_posix()
    proyecto = PurePosixPath(DIR_PROYECTO)
    return [
        "vitest",
        "run",
        f"--root={proyecto.parent}",
        DIR_TESTS,
        "--fsModuleCache=false",
        "--reporter=default",
        "--reporter=junit",
        f"--outputFile.junit={DIR_SALIDA}/{ARCHIVO_JUNIT}",
        f"--outputFile={DIR_SALIDA}/{ARCHIVO_JUNIT}",
        "--coverage.enabled=true",
        "--coverage.provider=v8",
        f"--coverage.include={proyecto.name}/{ruta_modulo}",
        "--coverage.reporter=json",
        "--coverage.reporter=json-summary",
        f"--coverage.reportsDirectory={DIR_SALIDA}",
        # /out es un montaje: Vitest no puede borrarlo antes de escribir (EROFS).
        "--coverage.clean=false",
        # Un bug detectado también necesita su cobertura (Vitest la omite si falla).
        "--coverage.reportOnFailure=true",
        "--no-color",
    ]


def variables_node() -> dict[str, str]:
    """Variables de entorno del contenedor al ejecutar pruebas Node en el sandbox."""
    return {
        "NODE_ENV": "test",
        "NO_COLOR": "1",
        # Vitest guarda un token en $HOME; el resto del contenedor es de solo lectura.
        "HOME": "/tmp",
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


def funciones_de_modulo_js(raiz: Path, modulo: str) -> list[dict[str, Any]]:
    """Devuelve nombre y línea de las funciones exportadas de un archivo JS/TS."""
    archivo = raiz / modulo
    if archivo.is_symlink() or not archivo.resolve().is_relative_to(raiz.resolve()):
        return []
    try:
        fuente = archivo.read_text(encoding="utf-8-sig")
        arbol = obtener_parser(gramatica_de(modulo)).parse(fuente.encode("utf-8"))
        if arbol.root_node.has_error:
            return []
        funciones = extraer_funciones(arbol.root_node)
        return [{"nombre": f["nombre"], "linea": f["linea"]} for f in funciones]
    except (OSError, UnicodeError, ValueError):
        return []
