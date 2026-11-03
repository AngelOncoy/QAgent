"""Validación de una carpeta local antes de abrirla como proyecto — HU-01.

Solo lee el sistema de archivos: nunca importa ni ejecuta código del usuario.
Obtiene el adaptador del registro y cuenta sus fuentes con el mismo criterio
que el análisis de la corrida, sin compilar ni ejecutar el proyecto.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from qagent.lenguajes import (
    LenguajeNoSoportado,
    adaptador_del_proyecto,
    adaptador_e2e_del_proyecto,
)

SIN_ARCHIVOS_PY = (
    "La carpeta no contiene archivos fuente analizables de un lenguaje soportado."
)


_PREFIJO_RAMA = "ref: refs/heads/"
_SHA = re.compile(r"[0-9a-f]{40}([0-9a-f]{24})?")


def detectar_rama(carpeta: str | os.PathLike[str]) -> str | None:
    """Devuelve la rama Git actual de la carpeta leyendo ``.git/HEAD``.

    No ejecuta ``git``: solo lee archivos. Soporta ``.git`` como carpeta o como
    archivo ``gitdir:`` (worktrees y submódulos). Con HEAD separado devuelve
    los 7 primeros caracteres del commit. Si la carpeta no es un repositorio,
    ``.git`` es un enlace simbólico o HEAD no se puede leer, devuelve ``None``.
    """
    git = Path(carpeta) / ".git"
    try:
        if git.is_symlink():
            return None
        if git.is_file():
            enlace = git.read_text(encoding="utf-8").strip()
            if not enlace.startswith("gitdir:"):
                return None
            git = Path(carpeta) / enlace.removeprefix("gitdir:").strip()
        head = (git / "HEAD").read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return None
    if head.startswith(_PREFIJO_RAMA):
        return head.removeprefix(_PREFIJO_RAMA) or None
    if _SHA.fullmatch(head):
        return head[:7]
    return None


def _resultado(
    ruta: str,
    nombre: str,
    cantidad_py: int = 0,
    error: str | None = None,
    rama: str | None = None,
    lenguaje: str | None = None,
    nombre_lenguaje: str | None = None,
    cantidad_fuentes: int = 0,
    extensiones: tuple[str, ...] = (),
    solo_e2e: bool = False,
) -> dict[str, Any]:
    """Arma el diccionario de respuesta de ``inspeccionar_carpeta``."""
    resultado = {
        "ok": error is None,
        "nombre": nombre,
        "ruta": ruta,
        "cantidad_py": cantidad_py,
        "error": error,
        "rama": rama,
        "lenguaje": lenguaje,
        "nombre_lenguaje": nombre_lenguaje,
        "cantidad_fuentes": cantidad_fuentes,
        "extensiones": list(extensiones),
    }
    if solo_e2e:
        resultado["solo_e2e"] = True
    return resultado


def inspeccionar_carpeta(ruta: str | os.PathLike[str]) -> dict[str, Any]:
    """Indica si una carpeta tiene fuentes de un adaptador operativo del registro.

    Args:
        ruta: Carpeta elegida por el usuario.

    Returns:
        Diccionario con ``ok`` (hay fuentes analizables), ``lenguaje``,
        ``nombre_lenguaje``, ``cantidad_fuentes`` y ``extensiones``. Conserva
        ``cantidad_py`` para clientes anteriores. Incluye ``nombre``, ``ruta``,
        ``error`` (mensaje en español o ``None``) y ``rama``
        (rama Git actual o ``None`` si no es un repositorio).
        Nunca lanza excepciones.
    """
    if not str(ruta).strip():
        return _resultado("", "", error="No se indicó ninguna carpeta.")

    carpeta = Path(os.path.abspath(ruta))
    texto = str(carpeta)
    nombre = carpeta.name or texto

    try:
        if not carpeta.exists():
            return _resultado(texto, nombre, error=f"La carpeta no existe: {texto}")
        if not carpeta.is_dir():
            return _resultado(
                texto, nombre, error=f"La ruta no es una carpeta: {texto}"
            )
        # os.walk ignora en silencio los errores de lectura: se comprueba antes
        # que la raíz sea legible para no confundir "sin permisos" con "vacía".
        with os.scandir(carpeta):
            pass
        solo_e2e = False
        try:
            adaptador = adaptador_del_proyecto(carpeta)
        except LenguajeNoSoportado:
            adaptador = adaptador_e2e_del_proyecto(carpeta)
            solo_e2e = True
        cantidad = len(adaptador.archivos_fuente(carpeta))
    except LenguajeNoSoportado as error:
        return _resultado(texto, nombre, error=str(error), rama=detectar_rama(carpeta))
    except PermissionError:
        return _resultado(
            texto, nombre, error=f"No hay permisos para leer la carpeta: {texto}"
        )
    except OSError:
        return _resultado(texto, nombre, error=f"No se pudo leer la carpeta: {texto}")

    rama = detectar_rama(carpeta)
    if cantidad == 0:
        return _resultado(texto, nombre, error=SIN_ARCHIVOS_PY, rama=rama)
    return _resultado(
        texto,
        nombre,
        cantidad_py=cantidad if adaptador.lenguaje == "python" else 0,
        rama=rama,
        lenguaje=adaptador.lenguaje,
        nombre_lenguaje=adaptador.nombre_visible,
        cantidad_fuentes=cantidad,
        extensiones=adaptador.extensiones,
        solo_e2e=solo_e2e,
    )
