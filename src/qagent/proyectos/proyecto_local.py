"""Validación de una carpeta local antes de abrirla como proyecto — HU-01.

Solo lee el sistema de archivos: nunca importa ni ejecuta código del usuario.
Obtiene el adaptador del registro y cuenta sus fuentes con el mismo criterio
que el análisis de la corrida, sin compilar ni ejecutar el proyecto.
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from qagent.lenguajes import (
    MAX_ARCHIVOS_DETECCION,
    LenguajeNoSoportado,
    ResultadoExploracion,
    adaptador_del_proyecto,
    adaptador_e2e_del_proyecto,
    explorar_archivos,
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


def _aviso_exploracion(exploracion: ResultadoExploracion | None) -> str | None:
    if not exploracion:
        return None
    if exploracion.estado == "truncado":
        limite_fmt = f"{exploracion.limite:,}".replace(",", ".")
        pendientes = exploracion.carpetas_pendientes
        ejemplo = f" ({', '.join(pendientes[:3])}...)" if pendientes else ""
        return (
            f"Exploración parcial: se alcanzó el límite de {limite_fmt} archivos. "
            f"Existen carpetas pendientes{ejemplo}. "
            "La detección del lenguaje se basa en la muestra analizada y puede ser incompleta."
        )
    if exploracion.estado == "parcial_error":
        return f"Exploración con incidencias: {len(exploracion.errores)} rutas no pudieron analizarse."
    if exploracion.estado == "cancelado":
        return "Exploración cancelada por el usuario."
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
    exploracion: ResultadoExploracion | None = None,
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
        "estado_exploracion": exploracion.estado if exploracion else "completo",
        "exploracion_incompleta": exploracion.incompleto if exploracion else False,
        "total_procesados": exploracion.total_procesados
        if exploracion
        else cantidad_fuentes,
        "limite_archivos": exploracion.limite
        if exploracion
        else MAX_ARCHIVOS_DETECCION,
        "carpetas_pendientes": list(exploracion.carpetas_pendientes)
        if exploracion
        else [],
        "aviso_exploracion": _aviso_exploracion(exploracion),
    }
    if solo_e2e:
        resultado["solo_e2e"] = True
    return resultado


def inspeccionar_carpeta(
    ruta: str | os.PathLike[str],
    *,
    subcarpetas: Sequence[str] | None = None,
    archivos_previos: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Indica si una carpeta tiene fuentes de un adaptador operativo del registro.

    Args:
        ruta: Carpeta elegida por el usuario.
        subcarpetas: Subcarpetas relativas específicas a analizar.
        archivos_previos: Archivos de una exploración previa a consolidar.

    Returns:
        Diccionario con ``ok`` (hay fuentes analizables), ``lenguaje``,
        ``nombre_lenguaje``, ``cantidad_fuentes``, ``extensiones`` y metadatos
        de exploración (``estado_exploracion``, ``exploracion_incompleta``,
        ``carpetas_pendientes``, ``aviso_exploracion``). Conserva
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
        exploracion = explorar_archivos(
            carpeta,
            subcarpetas=subcarpetas,
            archivos_previos=archivos_previos,
        )
        solo_e2e = False
        try:
            adaptador = adaptador_del_proyecto(carpeta, archivos=exploracion.archivos)
        except LenguajeNoSoportado:
            adaptador = adaptador_e2e_del_proyecto(carpeta)
            solo_e2e = True
        if subcarpetas or archivos_previos:
            if adaptador.lenguaje == "java":
                cantidad = sum(
                    1
                    for a in exploracion.archivos
                    if adaptador.es_fuente(a) and "test" not in Path(a).parts
                )
            else:
                cantidad = sum(
                    1 for a in exploracion.archivos if adaptador.es_fuente(a)
                )
        else:
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
        return _resultado(
            texto,
            nombre,
            error=SIN_ARCHIVOS_PY,
            rama=rama,
            exploracion=exploracion,
        )
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
        exploracion=exploracion,
    )
