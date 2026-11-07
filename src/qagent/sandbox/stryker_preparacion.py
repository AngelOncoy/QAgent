"""Preparación estática de Stryker sobre la copia del sandbox (#179).

Copia las pruebas aprobadas dentro del proyecto, configura Stryker para
mutar exclusivamente las líneas de las funciones críticas y verifica que el
proyecto no tenga su propia configuración de Stryker.
"""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

from qagent.lenguajes.javascript_estructura import exportadas, gramatica_de
from qagent.lenguajes.treesitter import obtener_parser
from qagent.sandbox.stryker_comando import CONFIG_STRYKER_TEMPORAL

CARPETA_PRUEBAS_STRYKER = "_qagent_mutacion"
REPORTES_DIR_STRYKER = "reports/mutation"
ARCHIVO_INFORME_STRYKER = "reports/mutation/mutation.json"

CONFIGURACIONES_PROPIAS = frozenset(
    {
        "stryker.config.json",
        "stryker.config.js",
        "stryker.config.mjs",
        "stryker.config.cjs",
        "stryker.conf.json",
        "stryker.conf.js",
    }
)


class ConfiguracionStrykerPropia(ValueError):
    """El proyecto ya declara Stryker; QAgent no debe sobrescribir su configuración."""


def detectar_configuracion_propia(copia: Path) -> None:
    """Verifica si el proyecto original ya trae configuración de Stryker.

    Raises:
        ConfiguracionStrykerPropia: si se detecta un archivo o clave de Stryker.
    """
    for nombre in CONFIGURACIONES_PROPIAS:
        if (copia / nombre).exists():
            raise ConfiguracionStrykerPropia(
                f"El proyecto tiene su propia configuración de Stryker ({nombre}); "
                "QAgent no la sobrescribe."
            )

    package_json = copia / "package.json"
    if package_json.is_file():
        try:
            datos = json.loads(package_json.read_text(encoding="utf-8"))
            if isinstance(datos, dict) and "stryker" in datos:
                raise ConfiguracionStrykerPropia(
                    "El proyecto tiene su propia configuración de Stryker en package.json; "
                    "QAgent no la sobrescribe."
                )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            pass


def extraer_rangos_funciones(
    raiz: Path, modulo: str, funciones: list[str]
) -> dict[str, tuple[int, int]]:
    """Obtiene los rangos `(linea_inicio, linea_fin)` de las funciones con tree-sitter.

    Args:
        raiz: carpeta raíz del proyecto o copia.
        modulo: ruta relativa del archivo.
        funciones: nombres de las funciones a ubicar.

    Returns:
        Diccionario `{nombre: (inicio, fin)}` con líneas 1-based inclusivas.
    """
    archivo = raiz / modulo
    if not archivo.is_file():
        return {}

    try:
        fuente = archivo.read_text(encoding="utf-8-sig")
        arbol = obtener_parser(gramatica_de(modulo)).parse(fuente.encode("utf-8"))
        if arbol.root_node.has_error:
            return {}

        buscadas = set(funciones)
        rangos: dict[str, tuple[int, int]] = {}
        for exp in exportadas(arbol.root_node):
            if exp.nombre in buscadas:
                inicio = exp.nodo.start_point.row + 1
                fin = exp.nodo.end_point.row + 1
                rangos[exp.nombre] = (inicio, fin)

        return rangos
    except (OSError, UnicodeError, ValueError):
        return {}


def preparar_pruebas_stryker(copia: Path, pruebas: Path, modulo: str) -> None:
    """Copia las pruebas aprobadas dentro de `copia / _qagent_mutacion`.

    Ajusta las rutas de importación `../proyecto/` para que apunten a `../`
    respecto a la carpeta interna de pruebas, evitando un 100 % falso.
    """
    destino_carpeta = copia / CARPETA_PRUEBAS_STRYKER
    destino_carpeta.mkdir(parents=True, exist_ok=True)

    ruta_mod = PurePosixPath(modulo.replace("\\", "/"))
    sufijo = ruta_mod.suffix.lower()
    if sufijo in {".ts", ".tsx"}:
        ext = ".test.ts"
    elif sufijo == ".mjs":
        ext = ".test.mjs"
    elif sufijo == ".cjs":
        ext = ".test.cjs"
    else:
        ext = ".test.js"

    for archivo in sorted(pruebas.rglob("*")):
        if not archivo.is_file():
            continue
        try:
            contenido = archivo.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        # En Vitest regular las pruebas corren desde /work/tests y usan "../proyecto/..."
        # Al copiarlas a _qagent_mutacion/ dentro de /work/proyecto, la ruta pasa a "../..."
        contenido_ajustado = contenido.replace("../proyecto/", "../")

        nombre_destino = f"{archivo.stem}{ext}"
        (destino_carpeta / nombre_destino).write_text(
            contenido_ajustado, encoding="utf-8"
        )


def escribir_config_stryker(
    copia: Path, modulo: str, rangos: dict[str, tuple[int, int]]
) -> Path:
    """Escribe `.qagent-stryker.json` delimitado a los rangos de las funciones."""
    ruta_posix = modulo.replace("\\", "/")
    patrones_mutate = [
        f"{ruta_posix}:{inicio}-{fin}"
        for nombre, (inicio, fin) in sorted(rangos.items())
    ]

    configuracion = {
        "$schema": "./node_modules/@stryker-mutator/core/schema/stryker-schema.json",
        "testRunner": "vitest",
        "plugins": ["@stryker-mutator/vitest-runner"],
        "reporters": ["json", "clear-text"],
        "jsonReporter": {
            "fileName": ARCHIVO_INFORME_STRYKER,
        },
        "mutate": patrones_mutate,
        "vitest": {
            "dir": CARPETA_PRUEBAS_STRYKER,
        },
        "concurrency": 1,
        "coverageAnalysis": "perTest",
    }

    archivo_config = copia / CONFIG_STRYKER_TEMPORAL
    archivo_config.write_text(json.dumps(configuracion, indent=2), encoding="utf-8")
    return archivo_config


def preparar_stryker(
    copia: Path, pruebas: Path, modulo: str, funciones: list[str]
) -> dict[str, tuple[int, int]]:
    """Prepara la copia del proyecto para ejecutar Stryker en el sandbox.

    Args:
        copia: directorio de la copia desechable del proyecto.
        pruebas: directorio temporal con las pruebas aprobadas.
        modulo: ruta relativa del módulo a mutar.
        funciones: nombres de las funciones críticas a mutar.

    Returns:
        Mapeo de `{nombre: (inicio, fin)}` con los rangos acotados.

    Raises:
        ConfiguracionStrykerPropia: si el proyecto ya tiene configuración de Stryker.
        ValueError: si no se pueden determinar los rangos de las funciones.
    """
    detectar_configuracion_propia(copia)

    rangos = extraer_rangos_funciones(copia, modulo, funciones)
    faltantes = [f for f in funciones if f not in rangos]
    if faltantes:
        raise ValueError(
            f"No se pudieron ubicar las líneas de las funciones críticas: {faltantes} en {modulo}."
        )

    preparar_pruebas_stryker(copia, pruebas, modulo)
    escribir_config_stryker(copia, modulo, rangos)

    return rangos
