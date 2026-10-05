"""Clonado de repositorios Git públicos por HTTPS (HU-02).

Funciones puras para validar la URL y la rama, calcular el destino y armar el
comando, más ``clonar``, que ejecuta ``git clone`` con ``subprocess`` (nunca con
``shell=True``) y garantiza que un clonado fallido no deje carpetas creadas.
No se vinculan cuentas ni se usan credenciales: solo repositorios públicos.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

FORMATO_URL = "https://<sitio>/<usuario>/<repositorio>(.git)"

# Sitio: etiquetas DNS separadas por puntos (al menos un punto). Usuario y
# repositorio empiezan con letra, dígito o '_' para que nunca parezcan una opción.
_ETIQUETA = r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
_SEGMENTO = r"[A-Za-z0-9_][A-Za-z0-9._-]*"
_RE_URL = re.compile(
    rf"https://{_ETIQUETA}(?:\.{_ETIQUETA})+/{_SEGMENTO}/{_SEGMENTO}",
    re.ASCII,
)
# Rama: caracteres seguros, sin '-' inicial (no se confunde con una opción de git).
_RE_RAMA = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._/-]*", re.ASCII)

# Fases que reporta `git clone --progress` y el tramo del avance total que ocupan.
_FASES = {
    "Counting objects": (0, 5),
    "Compressing objects": (5, 10),
    "Receiving objects": (10, 80),
    "Resolving deltas": (80, 95),
    "Updating files": (95, 100),
}
_RE_FASE = re.compile(r"(?P<fase>[A-Z][a-z]+ [a-z]+):\s+(?P<pct>\d{1,3})%")

AlAvanzar = Callable[[int | None, str], None]


@dataclass
class ResultadoClonado:
    """Resultado de un clonado: ``ok``, ``destino`` y, si falló, ``tipo_error`` y ``error``."""

    ok: bool
    destino: str
    tipo_error: str | None = None
    error: str | None = None


def validar_url(url: str) -> bool:
    """Indica si ``url`` tiene el formato ``https://<sitio>/<usuario>/<repositorio>(.git)``.

    Solo HTTPS: rechaza ``http://``, ``git@``, ``ssh://``, espacios, credenciales
    (``usuario@``), puertos, consultas y cualquier carácter fuera del patrón.
    """
    return isinstance(url, str) and _RE_URL.fullmatch(url) is not None


def validar_rama(rama: str) -> bool:
    """Indica si ``rama`` es un nombre de rama seguro para pasar a ``git clone --branch``."""
    if not isinstance(rama, str) or not _RE_RAMA.fullmatch(rama):
        return False
    return not (
        ".." in rama
        or "//" in rama
        or rama.endswith(("/", ".", ".lock"))
        or "/." in rama
    )


def nombre_repositorio(url: str) -> str:
    """Devuelve el último segmento de la URL sin la extensión ``.git``.

    Raises:
        ValueError: Si la URL no es válida.
    """
    if not validar_url(url):
        raise ValueError(f"URL no válida. Formato esperado: {FORMATO_URL}")
    nombre = url.rsplit("/", 1)[-1]
    return nombre.removesuffix(".git")


def carpeta_proyectos_por_defecto() -> Path:
    """Carpeta donde se clonan los proyectos si el usuario no elige otra."""
    return Path.home() / "Proyectos"


def destino_por_defecto(url: str, carpeta_proyectos: str | Path | None = None) -> Path:
    """Devuelve ``<carpeta de proyectos>/<repositorio>`` para la URL dada."""
    base = (
        Path(carpeta_proyectos)
        if carpeta_proyectos
        else carpeta_proyectos_por_defecto()
    )
    return base / nombre_repositorio(url)


def armar_comando(
    url: str, rama: str, destino: str | Path, superficial: bool = True
) -> list[str]:
    """Arma la lista de argumentos de ``git clone``.

    ``--`` separa las opciones de los argumentos posicionales para que la URL o el
    destino nunca se interpreten como opción.

    Raises:
        ValueError: Si la URL o la rama no son válidas.
    """
    if not validar_url(url):
        raise ValueError(f"URL no válida. Formato esperado: {FORMATO_URL}")
    if not validar_rama(rama):
        raise ValueError(f"Nombre de rama no válido: {rama!r}")
    comando = ["git", "clone", "--progress"]
    if superficial:
        comando += ["--depth", "1"]
    comando += ["--branch", rama, "--", url, str(destino)]
    return comando


def entorno_git() -> dict[str, str]:
    """Entorno del proceso git: sin pedir credenciales y con mensajes en inglés."""
    entorno = dict(os.environ)
    # Repo privado → falla en vez de pedir credenciales (terminal o ventana de GCM)
    entorno["GIT_TERMINAL_PROMPT"] = "0"
    entorno["GCM_INTERACTIVE"] = "never"
    # stderr en inglés para poder interpretarlo
    entorno["LC_ALL"] = "C"
    entorno["LANG"] = "C"
    return entorno


def porcentaje_total(linea: str) -> int | None:
    """Convierte una línea de progreso de git en el avance total (0-100), o None."""
    coincidencia = _RE_FASE.search(linea)
    if not coincidencia or coincidencia["fase"] not in _FASES:
        return None
    inicio, fin = _FASES[coincidencia["fase"]]
    pct = min(int(coincidencia["pct"]), 100)
    return inicio + (fin - inicio) * pct // 100


def interpretar_error(stderr: str, rama: str) -> tuple[str, str]:
    """Clasifica el stderr de un ``git clone`` fallido en ``(tipo_error, mensaje)``."""
    texto = stderr.lower()
    if "remote branch" in texto and "not found" in texto:
        return "rama_inexistente", f"La rama '{rama}' no existe en el repositorio."
    if "could not resolve host" in texto or "failed to connect" in texto:
        return (
            "sin_red",
            "No se pudo conectar con el sitio. Revisa tu conexión a internet.",
        )
    if any(
        marca in texto
        for marca in (
            "repository not found",
            "not found",
            "authentication failed",
            "could not read username",
            "terminal prompts disabled",
            "403",
            "401",
        )
    ):
        return (
            "privado_o_inexistente",
            (
                "El repositorio no existe o es privado. Solo se pueden clonar "
                "repositorios públicos por HTTPS."
            ),
        )
    ultima = next((ln for ln in reversed(stderr.splitlines()) if ln.strip()), "")
    return "git", f"Git no pudo clonar el repositorio. {ultima}".strip()


def _primer_ancestro_inexistente(ruta: Path) -> Path | None:
    """Devuelve la carpeta más alta de ``ruta`` que aún no existe (la que crearía git)."""
    if ruta.exists():
        return None
    actual = ruta
    while not actual.parent.exists() and actual.parent != actual:
        actual = actual.parent
    return actual


def _leer_progreso(flujo, al_avanzar: AlAvanzar | None) -> str:
    """Lee stderr de git (líneas separadas por ``\\r`` o ``\\n``) y reporta el avance."""
    lineas: list[str] = []
    actual = ""
    while True:
        caracter = flujo.read(1)
        if not caracter:
            break
        if caracter in "\r\n":
            if actual.strip():
                lineas.append(actual)
                if al_avanzar:
                    al_avanzar(porcentaje_total(actual), actual.strip())
            actual = ""
        else:
            actual += caracter
    if actual.strip():
        lineas.append(actual)
        if al_avanzar:
            al_avanzar(porcentaje_total(actual), actual.strip())
    return "\n".join(lineas)


def clonar(
    url: str,
    rama: str,
    destino: str | Path,
    superficial: bool = True,
    al_avanzar: AlAvanzar | None = None,
    popen: Callable[..., subprocess.Popen] = subprocess.Popen,
) -> ResultadoClonado:
    """Ejecuta ``git clone`` y devuelve el resultado; nunca lanza excepciones de git.

    Si el clonado falla, borra solo las carpetas que este proceso creó; una carpeta
    destino que ya existía (vacía) nunca se borra.

    Args:
        url: URL HTTPS del repositorio público.
        rama: Rama a clonar.
        destino: Carpeta donde se clona.
        superficial: Si es True usa ``--depth 1``.
        al_avanzar: Recibe ``(porcentaje_total | None, línea de git)`` por cada línea.
        popen: Inyectable para las pruebas.
    """
    destino = Path(destino).expanduser()
    if not validar_url(url):
        return ResultadoClonado(
            False,
            str(destino),
            "url_invalida",
            f"URL no válida. Formato esperado: {FORMATO_URL}",
        )
    if not validar_rama(rama):
        return ResultadoClonado(
            False, str(destino), "rama_invalida", f"Nombre de rama no válido: '{rama}'."
        )
    if destino.exists() and (not destino.is_dir() or any(destino.iterdir())):
        return ResultadoClonado(
            False,
            str(destino),
            "destino_ocupado",
            f"La carpeta destino ya existe y no está vacía: {destino}",
        )

    creada = _primer_ancestro_inexistente(destino)
    comando = armar_comando(url, rama, destino, superficial)
    try:
        proceso = popen(
            comando,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            env=entorno_git(),
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        return ResultadoClonado(
            False,
            str(destino),
            "git_no_instalado",
            "Git no está instalado o no está en el PATH. Instálalo desde https://git-scm.com.",
        )

    stderr = _leer_progreso(proceso.stderr, al_avanzar)
    codigo = proceso.wait()
    if codigo == 0:
        return ResultadoClonado(True, str(destino))

    if creada is not None and creada.exists():
        shutil.rmtree(creada, ignore_errors=True)
    tipo, mensaje = interpretar_error(stderr, rama)
    return ResultadoClonado(False, str(destino), tipo, mensaje)
