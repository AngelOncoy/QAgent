"""Ejecuta todas las pruebas de QAgent con un solo comando.

    python test.py                 lint + formato + todas las pruebas
    python test.py --rapido        sin lint y sin las pruebas de Docker ni de red
    python test.py --sin-lint      solo pytest
    python test.py -k clonador     cualquier otro argumento se pasa a pytest
    python test.py tests/proyectos -x

Siempre usa la IA simulada (PYAGENT_FAKE_LLM=1): ninguna prueba llama a una API real.
Las pruebas que necesitan Docker se omiten solas si Docker Desktop no está iniciado.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
RUTAS_LINT = [
    "src",
    "tests",
    "test.py",
]  # bench/ queda fuera: tiene bugs sembrados a propósito


def _paso(nombre: str, comando: list[str], entorno: dict[str, str]) -> bool:
    """Ejecuta un paso, muestra su salida y devuelve True si terminó bien."""
    print(f"\n=== {nombre} ===\n$ {' '.join(comando)}", flush=True)
    inicio = time.perf_counter()
    resultado = subprocess.run(comando, cwd=RAIZ, env=entorno, check=False)
    segundos = time.perf_counter() - inicio
    estado = (
        "OK" if resultado.returncode == 0 else f"FALLÓ (código {resultado.returncode})"
    )
    print(f"--- {nombre}: {estado} ({segundos:.1f} s)", flush=True)
    return resultado.returncode == 0


def main(argv: list[str] | None = None) -> int:
    """Corre lint, formato y pruebas; devuelve 0 solo si todo pasó."""
    parser = argparse.ArgumentParser(
        description="Ejecuta todas las pruebas del sistema.",
        epilog="Los demás argumentos van a pytest.",
    )
    parser.add_argument(
        "--sin-lint", action="store_true", help="omite ruff (lint y formato)"
    )
    parser.add_argument(
        "--rapido",
        action="store_true",
        help="sin lint y sin las pruebas marcadas docker ni red",
    )
    args, extra_pytest = parser.parse_known_args(argv)

    entorno = {**os.environ, "PYAGENT_FAKE_LLM": "1"}
    python = sys.executable
    pasos: list[tuple[str, list[str]]] = []

    if not (args.sin_lint or args.rapido):
        pasos.append(
            ("Lint (ruff check)", [python, "-m", "ruff", "check", *RUTAS_LINT])
        )
        pasos.append(
            (
                "Formato (ruff format --check)",
                [python, "-m", "ruff", "format", "--check", *RUTAS_LINT],
            )
        )

    comando_pytest = [python, "-m", "pytest", "-q"]
    if args.rapido:
        comando_pytest += ["-m", "not docker and not red"]
    pasos.append(("Pruebas (pytest)", comando_pytest + extra_pytest))

    resultados = [
        (nombre, _paso(nombre, comando, entorno)) for nombre, comando in pasos
    ]

    print("\n=== Resumen ===")
    for nombre, ok in resultados:
        print(f"  {'OK    ' if ok else 'FALLÓ '} {nombre}")
    return 0 if all(ok for _, ok in resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
