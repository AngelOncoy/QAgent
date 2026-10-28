"""Exporta el análisis estático Java y su tiempo observado (EN-19).

Uso: python -m qagent.lenguajes.prototipo_java bench_java --salida analisis.json
No compila, ejecuta pruebas, llama a una IA ni modifica el proyecto analizado.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from importlib.metadata import version
from pathlib import Path
from time import perf_counter

from qagent.lenguajes.java import JavaAdapter


def main(argumentos: list[str] | None = None) -> int:
    """Analiza una carpeta y exporta JSON UTF-8 con metadatos de la medición.

    Args:
        argumentos: opciones de línea de comandos; None usa las del proceso.

    Returns:
        0 si se analizaron fuentes sin errores; 1 ante errores de análisis,
        carpeta vacía o problemas de lectura/escritura. argparse usa código 2
        para opciones inválidas. Los errores parciales se conservan en el JSON.
    """
    opciones = argparse.ArgumentParser(
        description="Prototipo de análisis Java con tree-sitter (EN-19)"
    )
    opciones.add_argument("raiz", type=Path, help="Carpeta del proyecto Java")
    opciones.add_argument(
        "--salida", type=Path, help="Archivo .json que se creará o actualizará en UTF-8"
    )
    args = opciones.parse_args(argumentos)
    if args.salida is not None and args.salida.suffix.lower() != ".json":
        opciones.error("--salida debe ser un archivo .json")
    try:
        inicio = perf_counter()
        estructura = JavaAdapter().analizar(args.raiz)
        duracion = perf_counter() - inicio
        estructura["medicion"] = {
            "duracion_analisis_s": round(duracion, 6),
            "alcance": "Una ejecución: lectura y análisis; excluye arranque de Python y escritura del JSON.",
            "python": platform.python_version(),
            "sistema": platform.system(),
            "arquitectura": platform.machine(),
            "tree_sitter": version("tree-sitter"),
            "tree_sitter_java": version("tree-sitter-java"),
        }
        texto = json.dumps(estructura, ensure_ascii=False, indent=2) + "\n"
        if args.salida is None:
            print(texto, end="")
        else:
            args.salida.parent.mkdir(parents=True, exist_ok=True)
            args.salida.write_text(texto, encoding="utf-8")
            print(f"JSON guardado: {args.salida}")
            print(json.dumps(estructura["resumen"], ensure_ascii=False, indent=2))
            print(f"Tiempo de análisis: {duracion:.6f} s")
    except (OSError, ValueError) as error:
        print(f"No se pudo exportar el análisis Java: {error}", file=sys.stderr)
        return 1
    if estructura["errores"] or not estructura["modulos"]:
        print(
            "El análisis contiene errores o no encontró módulos Java; revise el JSON.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
