"""Construye QAgent para Windows: `QAgent.exe` (PyInstaller) y su instalador (Inno Setup).

Pasos que automatiza (TA-06):
  1. PyInstaller con `packaging/windows/qagent.spec` → `dist/windows/QAgent/QAgent.exe`
  2. Inno Setup con `packaging/windows/qagent.iss` → `dist/windows/QAgent-<versión>-instalador.exe`

Requisitos, una sola vez por PC:
  pip install -e .[dev,empaquetar]           (instala PyInstaller)
  Inno Setup 6: https://jrsoftware.org/isdl.php  (o winget install JRSoftware.InnoSetup)

Uso, desde la raíz del repositorio:
  python scripts/construir_windows.py                  # ejecutable + instalador
  python scripts/construir_windows.py --sin-instalador # solo la carpeta con QAgent.exe
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # Python 3.10
    import tomli as tomllib

RAIZ = Path(__file__).resolve().parents[1]
WINDOWS = RAIZ / "packaging" / "windows"
SALIDA = RAIZ / "dist" / "windows"
TRABAJO = RAIZ / "build" / "pyinstaller"

#: Dónde suele quedar el compilador de Inno Setup si no está en el PATH.
RUTAS_ISCC = (
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    / "Inno Setup 6"
    / "ISCC.exe",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    / "Inno Setup 6"
    / "ISCC.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
)


def version() -> str:
    """Versión de `pyproject.toml`, la misma que muestra `qagent --version`."""
    with open(RAIZ / "pyproject.toml", "rb") as archivo:
        return tomllib.load(archivo)["project"]["version"]


def buscar_iscc() -> Path | None:
    """Compilador de Inno Setup: variable ISCC, el PATH o la carpeta de instalación."""
    candidatos = [os.environ.get("ISCC"), shutil.which("iscc"), *RUTAS_ISCC]
    return next((Path(c) for c in candidatos if c and Path(c).is_file()), None)


def _correr(comando: list[str]) -> None:
    print("$", " ".join(str(c) for c in comando), flush=True)
    subprocess.run(comando, check=True, cwd=RAIZ)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--sin-instalador",
        action="store_true",
        help="solo genera la carpeta con QAgent.exe",
    )
    args = parser.parse_args(argv)

    if os.name != "nt":
        print(
            "Aviso: el ejecutable que se genere servirá solo para este sistema, no para Windows."
        )
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("Falta PyInstaller: pip install -e .[dev,empaquetar]")
        return 1

    numero = version()
    print(f"== QAgent {numero}: ejecutable (PyInstaller) ==")
    _correr(
        [
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
            "--distpath", str(SALIDA), "--workpath", str(TRABAJO),
            str(WINDOWS / "qagent.spec"),
        ]
    )  # fmt: skip
    ejecutable = SALIDA / "QAgent" / ("QAgent.exe" if os.name == "nt" else "QAgent")
    print(f"Listo: {ejecutable}")

    if args.sin_instalador or os.name != "nt":
        return 0
    iscc = buscar_iscc()
    if iscc is None:
        print(
            "No se encontró Inno Setup 6 (ISCC.exe). Instálalo desde "
            "https://jrsoftware.org/isdl.php o con: winget install JRSoftware.InnoSetup\n"
            "La carpeta con QAgent.exe ya está lista; vuelve a correr este script después."
        )
        return 1
    print(f"== QAgent {numero}: instalador (Inno Setup) ==")
    _correr([str(iscc), f"/DVersion={numero}", str(WINDOWS / "qagent.iss")])
    print(f"Listo: {SALIDA / f'QAgent-{numero}-instalador.exe'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
