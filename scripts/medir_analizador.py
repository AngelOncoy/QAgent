"""Mide cuánto tarda el analizador estático de Python sobre una o varias carpetas (TA-16).

Corre ``analizar_proyecto`` varias veces por carpeta y muestra la mediana, el mínimo y el
tiempo por archivo. Sirve para comparar el analizador antes y después de un cambio
(por ejemplo, ``ast`` frente a tree-sitter): se corre igual en las dos versiones.

Uso: ``python scripts/medir_analizador.py [--repeticiones N] carpeta [carpeta...]``
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from qagent.analysis.analyzer import analizar_proyecto, listar_archivos_py


def medir(carpeta: Path, repeticiones: int) -> dict[str, float]:
    """Tiempos en milisegundos de ``analizar_proyecto(carpeta)``."""
    archivos = len(listar_archivos_py(carpeta))
    analizar_proyecto(carpeta)  # calentamiento: carga de módulos y gramática
    tiempos = []
    for _ in range(repeticiones):
        inicio = time.perf_counter()
        analizar_proyecto(carpeta)
        tiempos.append((time.perf_counter() - inicio) * 1000)
    mediana = statistics.median(tiempos)
    return {
        "archivos": archivos,
        "mediana_ms": mediana,
        "minimo_ms": min(tiempos),
        "por_archivo_ms": mediana / archivos if archivos else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("carpetas", nargs="+", type=Path)
    parser.add_argument("--repeticiones", type=int, default=15)
    argumentos = parser.parse_args()
    print(
        f"{'carpeta':40} {'archivos':>8} {'mediana':>10} {'mínimo':>10} {'por archivo':>12}"
    )
    for carpeta in argumentos.carpetas:
        r = medir(carpeta, argumentos.repeticiones)
        print(
            f"{carpeta!s:40} {r['archivos']:>8} {r['mediana_ms']:>8.1f}ms "
            f"{r['minimo_ms']:>8.1f}ms {r['por_archivo_ms']:>10.2f}ms"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
