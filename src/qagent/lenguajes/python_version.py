"""Detección y resolución de la versión de Python del sandbox (ADR-013).

Analiza de manera puramente estática los archivos de configuración del proyecto:
1. `.python-version` (pyenv, uv, asdf, mise...)
2. `requires-python` en `pyproject.toml` (PEP 621)
3. `python_requires` en `setup.cfg`

Si no se declara ninguna, se usa la versión por defecto de QAgent (3.11).
Si se declara un rango (ej. `>=3.10`), se elige la versión más alta de la lista
permitida que lo cumpla.
Si la versión o rango requerido no es compatible con el rango soportado (3.10–3.14),
se lanza `VersionPythonNoSoportada` con un mensaje claro que informa qué pidió el
proyecto y qué soporta QAgent.
"""

from __future__ import annotations

import configparser
import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from qagent.config import SandboxPython, cargar_sandbox_python

if sys.version_info >= (3, 11):
    import tomllib
else:  # Python 3.10
    import tomli as tomllib


class VersionPythonNoSoportada(RuntimeError):
    """El proyecto pide una versión de Python fuera del rango soportado por QAgent."""

    def __init__(self, version_pedida: str, soportadas: Sequence[str]) -> None:
        self.version_pedida = version_pedida
        self.soportadas = tuple(soportadas)
        rango = (
            f"{soportadas[0]}–{soportadas[-1]}"
            if len(soportadas) > 1
            else soportadas[0]
        )
        lista = ", ".join(soportadas)
        super().__init__(
            f"El proyecto requiere Python {version_pedida}, pero QAgent soporta "
            f"Python {rango} ({lista})."
        )


def detectar_declaracion_version(
    raiz: str | os.PathLike[str],
) -> tuple[str, str] | None:
    """Busca la declaración de versión de Python en los archivos del proyecto.

    Orden de precedencia (ADR-013):
    1. `.python-version`
    2. `requires-python` de `pyproject.toml`
    3. `python_requires` de `setup.cfg`

    Returns:
        Tupla (fuente, declaracion) o None si ningún archivo declara la versión.
    """
    carpeta = Path(raiz)

    # 1. .python-version
    archivo_pv = carpeta / ".python-version"
    if archivo_pv.is_file():
        try:
            lineas = archivo_pv.read_text(encoding="utf-8").splitlines()
            for linea in lineas:
                texto = linea.strip()
                if not texto or texto.startswith("#"):
                    continue
                # Soporta prefijos como "cpython-" o "python-" (ej. cpython-3.12.0)
                limpio = re.sub(r"^(?:cpython|python)-", "", texto, flags=re.IGNORECASE)
                return (".python-version", limpio)
        except OSError:
            pass

    # 2. pyproject.toml -> [project].requires-python
    archivo_pyproject = carpeta / "pyproject.toml"
    if archivo_pyproject.is_file():
        try:
            datos = tomllib.loads(archivo_pyproject.read_text(encoding="utf-8"))
            if isinstance(datos, dict):
                req = datos.get("project", {}).get("requires-python")
                if isinstance(req, str) and req.strip():
                    return ("pyproject.toml", req.strip())
        except (OSError, tomllib.TOMLDecodeError):
            pass

    # 3. setup.cfg -> [options].python_requires
    archivo_setup = carpeta / "setup.cfg"
    if archivo_setup.is_file():
        try:
            parser = configparser.ConfigParser()
            parser.read(archivo_setup, encoding="utf-8")
            if parser.has_section("options") and parser.has_option(
                "options", "python_requires"
            ):
                req = parser.get("options", "python_requires").strip()
                if req:
                    return ("setup.cfg", req)
        except (OSError, configparser.Error):
            pass

    return None


def _normalizar_especificador(declaracion: str) -> str:
    """Traduce formatos no PEP 440 comunes (ej. caret de Poetry `^3.10`)."""
    dec = declaracion.strip()
    if dec.startswith("^"):
        v_str = dec[1:].strip()
        try:
            v = Version(v_str)
            return f">={v_str}, <{v.major + 1}.0"
        except InvalidVersion:
            return dec
    if dec.startswith("~") and not dec.startswith("~="):
        v_str = dec[1:].strip()
        try:
            v = Version(v_str)
            return f">={v_str}, <{v.major}.{v.minor + 1}"
        except InvalidVersion:
            return dec
    return dec


def elegir_version_python(
    declaracion: str | None,
    versiones_soportadas: Sequence[str],
    version_por_defecto: str = "3.11",
) -> str:
    """Elige la versión de Python del sandbox según la declaración y la lista soportada.

    Reglas (ADR-013):
    1. Si `declaracion` es None, devuelve `version_por_defecto`.
    2. Si `declaracion` es una versión exacta (ej. "3.12" o "3.12.4"):
       - Se extrae major.minor (ej. "3.12").
       - Si está en `versiones_soportadas`, se devuelve.
       - Si no, se lanza `VersionPythonNoSoportada`.
    3. Si `declaracion` es un rango o especificador PEP 440 (ej. ">=3.10", ">=3.10, <3.13"):
       - Se evalúan todas las versiones de `versiones_soportadas` ordenadas de menor a mayor.
       - Se elige la versión más alta que cumpla la especificación.
       - Si ninguna la cumple, se lanza `VersionPythonNoSoportada`.

    Raises:
        VersionPythonNoSoportada: si ninguna versión soportada cumple lo requerido.
    """
    if declaracion is None:
        return version_por_defecto

    dec_limpia = declaracion.strip()
    if not dec_limpia:
        return version_por_defecto

    # Ordenar versiones soportadas numéricamente
    try:
        ordenadas = sorted(versiones_soportadas, key=Version)
    except InvalidVersion:
        ordenadas = list(versiones_soportadas)

    # Caso 1: Versión simple sin operadores de rango (ej. "3.12", "3.12.4")
    if not any(c in dec_limpia for c in ("<", ">", "=", "!", "~", ",", "*", "^")):
        try:
            v = Version(dec_limpia)
            base = f"{v.major}.{v.minor}"
            if base in versiones_soportadas:
                return base
            raise VersionPythonNoSoportada(dec_limpia, versiones_soportadas)
        except InvalidVersion:
            raise VersionPythonNoSoportada(dec_limpia, versiones_soportadas) from None

    # Caso 2: Expresión con operadores o rangos PEP 440
    especificador_str = _normalizar_especificador(dec_limpia)
    try:
        spec = SpecifierSet(especificador_str)
    except InvalidSpecifier:
        raise VersionPythonNoSoportada(dec_limpia, versiones_soportadas) from None

    candidatas = [v for v in ordenadas if Version(v) in spec]
    if candidatas:
        # La regla de ADR-013: se elige la versión más alta de la lista que lo cumpla
        return candidatas[-1]

    raise VersionPythonNoSoportada(dec_limpia, versiones_soportadas)


def resolver_version_python_proyecto(
    raiz: str | os.PathLike[str],
    config_sandbox: SandboxPython | None = None,
) -> str:
    """Detecta y resuelve la versión de Python que debe usar el sandbox para `raiz`."""
    config = config_sandbox or cargar_sandbox_python()
    detectado = detectar_declaracion_version(raiz)
    declaracion = detectado[1] if detectado else None
    return elegir_version_python(
        declaracion,
        config.versiones_soportadas,
        version_por_defecto=config.version_por_defecto,
    )
