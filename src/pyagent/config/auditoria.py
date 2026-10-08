"""Búsqueda de patrones de clave de API en los archivos del repositorio (EN-06, RN-07).

Uso desde la raíz del repositorio::

    set PYTHONPATH=src
    python -m pyagent.config.auditoria          (sale con código 1 si encuentra algo)

Revisa los archivos versionados (`git ls-files`; si no hay Git, recorre la carpeta sin
`.git`, entornos virtuales ni `.env`). Los hallazgos indican archivo, línea y tipo de
patrón, **nunca el texto encontrado**, para no repetir una clave en la consola.
"""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from pyagent.config.carga import RAIZ

#: Nombre → expresión regular de claves reales de cada proveedor y asignaciones genéricas.
PATRONES: dict[str, re.Pattern[str]] = {
    "clave de Anthropic": re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),
    "clave tipo OpenAI/OpenRouter": re.compile(
        r"\bsk-(?:proj-|or-v1-)?[A-Za-z0-9_\-]{32,}"
    ),
    "clave de Google": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "clave de xAI": re.compile(r"\bxai-[A-Za-z0-9]{40,}"),
    "token de GitHub": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}"),
    "asignación de clave": re.compile(
        r"""(?ix)\b[A-Z0-9_]*(?:API_?KEY|SECRET|PASSWORD|(?:ACCESS|AUTH|API)_?TOKEN)\b\s*[=:]\s*["']?
        (?!os\.|environ|getenv)[A-Za-z0-9_\-/+=]{16,}"""
    ),
}

CARPETAS_OMITIDAS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
}
MAX_BYTES = 2_000_000  # archivos más grandes no son código ni configuración


@dataclass(frozen=True)
class Hallazgo:
    """Un posible secreto: dónde está y qué tipo de patrón coincidió (sin el texto)."""

    archivo: str
    linea: int
    patron: str

    def __str__(self) -> str:
        return f"{self.archivo}:{self.linea}: posible {self.patron}"


def archivos_del_repositorio(raiz: Path) -> list[Path]:
    """Archivos versionados con `git ls-files`; sin Git, todos los de la carpeta."""
    try:
        salida = subprocess.run(
            ["git", "-C", str(raiz), "ls-files", "-z"],
            capture_output=True,
            timeout=30,
            check=True,
            stdin=subprocess.DEVNULL,
        ).stdout
        nombres = [n for n in salida.decode("utf-8", "replace").split("\0") if n]
        return [raiz / n for n in nombres]
    except (OSError, subprocess.SubprocessError):
        return [
            ruta
            for ruta in raiz.rglob("*")
            if ruta.is_file()
            and not CARPETAS_OMITIDAS.intersection(ruta.relative_to(raiz).parts)
            and not ruta.name.startswith(".env")
        ]


def buscar_claves(raiz: str | Path = RAIZ) -> list[Hallazgo]:
    """Busca patrones de clave en los archivos del repositorio.

    Se omiten los archivos binarios o ilegibles y las líneas con imágenes `base64,`
    incrustadas, que producirían falsos positivos.

    Returns:
        Hallazgos ordenados por archivo y línea; lista vacía si no hay ninguno.
    """
    raiz = Path(raiz)
    hallazgos: list[Hallazgo] = []
    for ruta in sorted(archivos_del_repositorio(raiz)):
        try:
            if not ruta.is_file() or ruta.stat().st_size > MAX_BYTES:
                continue
            texto = ruta.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        relativa = ruta.relative_to(raiz).as_posix()
        for numero, linea in enumerate(texto.splitlines(), start=1):
            if "base64," in linea:
                continue
            for nombre, patron in PATRONES.items():
                if patron.search(linea):
                    hallazgos.append(Hallazgo(relativa, numero, nombre))
                    break  # un hallazgo por línea
    return hallazgos


def main(argumentos: list[str] | None = None) -> int:
    """Imprime los hallazgos y devuelve 0 si no hay ninguno, 1 si hay."""
    argumentos = sys.argv[1:] if argumentos is None else argumentos
    raiz = Path(argumentos[0]) if argumentos else RAIZ
    hallazgos = buscar_claves(raiz)
    if not hallazgos:
        print("Sin patrones de clave en el repositorio (RN-07).")
        return 0
    print(f"{len(hallazgos)} posible(s) clave(s) en el repositorio:")
    for hallazgo in hallazgos:
        print(f"  {hallazgo}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
