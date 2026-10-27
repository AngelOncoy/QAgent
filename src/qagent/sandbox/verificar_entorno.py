"""Comprobación del entorno aislado (issue 142). Se ejecuta DENTRO de la imagen.

Al construir la imagen del proyecto, importa cada módulo de nivel superior de las
distribuciones instaladas (dependencias de terceros, nunca el código del proyecto) y
anota las librerías del sistema (`lib*.so`) que no se pudieron cargar. Escribe el
resultado en JSON en la ruta que recibe como argumento.

Solo usa la biblioteca estándar: corre con el Python de la imagen, no con el de QAgent.
"""

from __future__ import annotations

import importlib
import json
import re
import signal
import sys
from importlib import metadata

#: Nombre de una librería compartida dentro de un mensaje de error.
_LIBRERIA = re.compile(r"(lib[A-Za-z0-9_.+\-]*?\.so(?:\.[0-9]+)*)")
#: Mensajes del cargador dinámico cuando falta una librería del sistema.
_SENALES = ("cannot open shared object file", "cannot load library", "error loading")
#: Módulos de nivel superior que no son código importable de la dependencia.
_IGNORADOS = {
    "tests",
    "test",
    "testing",
    "docs",
    "doc",
    "examples",
    "example",
    "benchmarks",
    "setup",
    "conftest",
}
SEGUNDOS_POR_MODULO = 60


def _modulos() -> list[tuple[str, list[str]]]:
    """(módulo, distribuciones que lo instalan), en orden alfabético."""
    pares = []
    for modulo, distribuciones in sorted(metadata.packages_distributions().items()):
        if not modulo.isidentifier() or modulo.startswith("_") or modulo in _IGNORADOS:
            continue
        pares.append((modulo, sorted(set(distribuciones))))
    return pares


def _libreria_faltante(error: BaseException) -> str | None:
    """La librería del sistema que no se pudo cargar, si ese fue el error."""
    texto = str(error)
    if not any(senal in texto for senal in _SENALES):
        return None
    coincidencia = _LIBRERIA.search(texto)
    return coincidencia.group(1) if coincidencia else None


def _tiempo_agotado(*_: object) -> None:
    raise TimeoutError("la importación tardó demasiado")


def verificar() -> dict:
    """Importa cada módulo y devuelve las librerías del sistema que faltan."""
    faltantes: dict[str, dict] = {}
    revisados = 0
    if hasattr(signal, "SIGALRM"):
        signal.signal(signal.SIGALRM, _tiempo_agotado)
    for modulo, distribuciones in _modulos():
        revisados += 1
        if hasattr(signal, "SIGALRM"):
            signal.alarm(SEGUNDOS_POR_MODULO)
        try:
            importlib.import_module(modulo)
        except BaseException as error:  # noqa: BLE001 — cualquier fallo se ignora salvo el de una .so
            libreria = _libreria_faltante(error)
            if libreria:
                entrada = faltantes.setdefault(
                    libreria,
                    {"libreria": libreria, "modulos": [], "paquetes_python": []},
                )
                entrada["modulos"].append(modulo)
                for distribucion in distribuciones:
                    if distribucion not in entrada["paquetes_python"]:
                        entrada["paquetes_python"].append(distribucion)
        finally:
            if hasattr(signal, "SIGALRM"):
                signal.alarm(0)
    return {
        "version": 1,
        "revisados": revisados,
        "faltantes": sorted(faltantes.values(), key=lambda f: f["libreria"]),
    }


def main(argv: list[str]) -> int:
    """Escribe el informe en `argv[1]` (no en stdout: una dependencia puede imprimir)."""
    informe = verificar()
    with open(argv[1], "w", encoding="utf-8") as archivo:
        json.dump(informe, archivo, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
