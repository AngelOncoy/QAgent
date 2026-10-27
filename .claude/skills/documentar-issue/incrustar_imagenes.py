"""Incrusta en un informe .md las imágenes que apuntan a archivos locales.

Uso:
    python .claude/skills/documentar-issue/incrustar_imagenes.py "docs/evidencias/<informe>.md" [...]

Cada `![texto](ruta-local)` se reemplaza por la imagen dentro del propio .md (data URI en
base64), así el informe queda en un solo archivo. Las rutas web (http/https) y las que ya
están incrustadas no se tocan. Las rutas que no existen se informan y quedan como estaban.
Solo usa la biblioteca estándar.
"""

from __future__ import annotations

import base64
import mimetypes
import re
import sys
from pathlib import Path

_IMAGEN = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")


def incrustar(informe: Path) -> tuple[int, list[str]]:
    """Incrusta las imágenes locales del informe. Devuelve (incrustadas, no encontradas)."""
    texto = informe.read_text(encoding="utf-8")
    incrustadas = 0
    faltantes: list[str] = []

    def reemplazar(coincidencia: re.Match[str]) -> str:
        nonlocal incrustadas
        alt, ruta = coincidencia.group(1), coincidencia.group(2)
        if ruta.startswith(("data:", "http://", "https://")):
            return coincidencia.group(0)
        archivo = Path(ruta)
        if not archivo.is_absolute():
            archivo = informe.parent / archivo
        if not archivo.is_file():
            faltantes.append(ruta)
            return coincidencia.group(0)
        tipo = mimetypes.guess_type(archivo.name)[0] or "image/png"
        datos = base64.b64encode(archivo.read_bytes()).decode("ascii")
        incrustadas += 1
        return f"![{alt}](data:{tipo};base64,{datos})"

    informe.write_text(_IMAGEN.sub(reemplazar, texto), encoding="utf-8")
    return incrustadas, faltantes


def main(argumentos: list[str]) -> int:
    if not argumentos:
        print(__doc__)
        return 2
    codigo = 0
    for ruta in argumentos:
        informe = Path(ruta)
        if not informe.is_file():
            print(f"No existe {informe}")
            codigo = 1
            continue
        incrustadas, faltantes = incrustar(informe)
        print(f"{informe.name}: {incrustadas} imagen(es) incrustada(s)")
        for faltante in faltantes:
            print(f"  No se encontró: {faltante}")
            codigo = 1
    return codigo


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
