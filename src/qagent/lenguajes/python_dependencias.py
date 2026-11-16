"""Dependencias que declara un proyecto Python, leídas sin ejecutar nada (#287).

El Reviewer las usa para decidir si un `ModuleNotFoundError` es del entorno (el
proyecto declara esa dependencia y no está instalada en el sandbox) o de la prueba
(importó algo inventado). Para eso hacen falta dos cosas que antes faltaban:

- **Leer bien cada formato**: `requirements*.txt`, `pyproject.toml` (PEP 621, extras,
  *dependency groups* PEP 735, Poetry y los miembros de un workspace de uv),
  `setup.cfg`, `setup.py` y `Pipfile`. Los TOML se leen con `tomllib`, no por líneas, y
  `setup.py` con tree-sitter (ADR-009): nunca se ejecuta.
- **Traducir distribución a módulo**: `PyYAML` se importa como `yaml` y
  `python-dotenv` como `dotenv`. Sin una tabla de los casos conocidos, el Reviewer
  creía que el módulo no estaba declarado y reintentaba con la IA.
"""

from __future__ import annotations

import configparser
import re
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

from qagent.analysis import arbol_ts

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

#: Distribuciones cuyo módulo no se llama como ellas (nombre canónico PEP 503 → módulos).
#: Para las demás basta el nombre canónico con `-` cambiado por `_`.
MODULOS_CONOCIDOS: dict[str, tuple[str, ...]] = {
    "attrs": ("attr", "attrs"),
    "beautifulsoup4": ("bs4",),
    "discord-py": ("discord",),
    "dnspython": ("dns",),
    "faiss-cpu": ("faiss",),
    "faiss-gpu": ("faiss",),
    "gitpython": ("git",),
    "google-api-python-client": ("googleapiclient",),
    "msgpack-python": ("msgpack",),
    "mysql-connector-python": ("mysql",),
    "mysqlclient": ("MySQLdb",),
    "opencv-contrib-python": ("cv2",),
    "opencv-contrib-python-headless": ("cv2",),
    "opencv-python": ("cv2",),
    "opencv-python-headless": ("cv2",),
    "pillow": ("PIL",),
    "protobuf": ("google",),
    "psycopg2-binary": ("psycopg2",),
    "pycryptodome": ("Crypto",),
    "pycryptodomex": ("Cryptodome",),
    "pygithub": ("github",),
    "pyjwt": ("jwt",),
    "pymongo": ("pymongo", "bson", "gridfs"),
    "pyopenssl": ("OpenSSL",),
    "pyserial": ("serial",),
    "python-dateutil": ("dateutil",),
    "python-dotenv": ("dotenv",),
    "python-jose": ("jose",),
    "python-magic": ("magic",),
    "python-multipart": ("multipart", "python_multipart"),
    "python-socketio": ("socketio",),
    "python-telegram-bot": ("telegram",),
    "pyyaml": ("yaml",),
    "pyzmq": ("zmq",),
    "ruamel-yaml": ("ruamel",),
    "scikit-image": ("skimage",),
    "scikit-learn": ("sklearn",),
    "setuptools": ("setuptools", "pkg_resources"),
    "tensorflow-cpu": ("tensorflow",),
    "websocket-client": ("websocket",),
}

#: Opciones de pip que pueden ir al final de una línea de requirements (`--hash=...`).
_OPCION_AL_FINAL = re.compile(r"\s+-{1,2}[A-Za-z]")
_CLAVES_SETUP = ("install_requires", "extras_require", "tests_require")


def modulos_de(distribucion: str) -> tuple[str, ...]:
    """Módulos de primer nivel con que se importa una distribución."""
    canonico = canonicalize_name(distribucion)
    return MODULOS_CONOCIDOS.get(canonico, (canonico.replace("-", "_"),))


def dependencias_declaradas(raiz: Path) -> dict[str, str]:
    """Módulo de primer nivel → distribución que lo declara, para todo el proyecto.

    Junta las dependencias de ejecución, de desarrollo y opcionales: cualquiera de
    ellas puede faltar en el sandbox. Un archivo ilegible o mal formado se ignora.
    """
    modulos: dict[str, str] = {}
    for distribucion in _distribuciones(raiz):
        for modulo in modulos_de(distribucion):
            modulos.setdefault(modulo, distribucion)
    return modulos


def _distribuciones(raiz: Path) -> Iterator[str]:
    for archivo in sorted(raiz.glob("requirements*.txt")):
        yield from _nombres(_lineas_requirements(_leer(archivo)))
    pyproject = _toml(raiz / "pyproject.toml")
    yield from _de_pyproject(pyproject)
    for miembro in _miembros_workspace(raiz, pyproject):
        yield from _de_pyproject(_toml(miembro / "pyproject.toml"))
    yield from _nombres(_de_setup_cfg(_leer(raiz / "setup.cfg")))
    yield from _nombres(_de_setup_py(_leer(raiz / "setup.py")))
    pipfile = _toml(raiz / "Pipfile")
    for seccion in ("packages", "dev-packages"):
        yield from _claves(pipfile.get(seccion))


# --- Lectura de cada formato ---------------------------------------------------------


def _leer(archivo: Path) -> str:
    try:
        return archivo.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _toml(archivo: Path) -> dict[str, Any]:
    texto = _leer(archivo)
    if not texto:
        return {}
    try:
        return tomllib.loads(texto)
    except tomllib.TOMLDecodeError:
        return {}


def _nombres(requisitos: Iterable[str]) -> Iterator[str]:
    """Nombre de distribución de cada requisito PEP 508; los inválidos se saltan."""
    for requisito in requisitos:
        try:
            yield Requirement(requisito.strip()).name
        except InvalidRequirement:
            continue


def _lineas_requirements(texto: str) -> Iterator[str]:
    """Requisitos de un requirements.txt, sin comentarios, opciones ni rutas."""
    for linea in texto.replace("\\\n", " ").splitlines():
        linea = linea.split(" #", 1)[0].strip()
        if not linea or linea.startswith(("#", "-", ".", "/")):
            continue
        yield _OPCION_AL_FINAL.split(linea, 1)[0]


def _de_pyproject(datos: dict[str, Any]) -> Iterator[str]:
    proyecto = _tabla(datos.get("project"))
    yield from _nombres(_cadenas(proyecto.get("dependencies")))
    for extra in _tabla(proyecto.get("optional-dependencies")).values():
        yield from _nombres(_cadenas(extra))
    # PEP 735: las entradas que no son cadenas ({include-group = ...}) se saltan.
    for grupo in _tabla(datos.get("dependency-groups")).values():
        yield from _nombres(_cadenas(grupo))
    herramientas = _tabla(datos.get("tool"))
    yield from _nombres(
        _cadenas(_tabla(herramientas.get("uv")).get("dev-dependencies"))
    )
    poetry = _tabla(herramientas.get("poetry"))
    for seccion in ("dependencies", "dev-dependencies"):
        yield from _claves(poetry.get(seccion))
    for grupo in _tabla(poetry.get("group")).values():
        yield from _claves(_tabla(grupo).get("dependencies"))


def _miembros_workspace(raiz: Path, pyproject: dict[str, Any]) -> list[Path]:
    """Carpetas de los miembros de un workspace de uv, sin salir de la raíz."""
    workspace = _tabla(_tabla(_tabla(pyproject.get("tool")).get("uv")).get("workspace"))
    base = raiz.resolve()
    excluidos = {
        carpeta.resolve()
        for patron in _cadenas(workspace.get("exclude"))
        for carpeta in _expandir(raiz, patron)
    }
    miembros = []
    for patron in _cadenas(workspace.get("members")):
        for carpeta in _expandir(raiz, patron):
            real = carpeta.resolve()
            if (
                real.is_relative_to(base)
                and real != base
                and real not in excluidos
                and (carpeta / "pyproject.toml").is_file()
            ):
                miembros.append(carpeta)
    return miembros


def _expandir(raiz: Path, patron: str) -> list[Path]:
    try:
        return sorted(raiz.glob(patron))
    except (NotImplementedError, ValueError):  # patrón absoluto o inválido
        return []


def _de_setup_cfg(texto: str) -> Iterator[str]:
    if not texto:
        return
    lector = configparser.ConfigParser(interpolation=None)
    try:
        lector.read_string(texto)
    except configparser.Error:
        return
    if lector.has_option("options", "install_requires"):
        yield from lector.get("options", "install_requires").splitlines()
    if lector.has_section("options.extras_require"):
        for _, valor in lector.items("options.extras_require"):
            yield from valor.splitlines()


def _de_setup_py(texto: str) -> Iterator[str]:
    """Cadenas literales de `install_requires`/`extras_require` (tree-sitter, sin ejecutar)."""
    if not texto:
        return
    for nodo in arbol_ts.recorrer(arbol_ts.parsear(texto).root_node):
        if nodo.type != "keyword_argument":
            continue
        nombre = arbol_ts.campo(nodo, "name")
        if nombre is None or arbol_ts.texto(nombre) not in _CLAVES_SETUP:
            continue
        valor = arbol_ts.campo(nodo, "value")
        if valor is None:
            continue
        # En extras_require ({"extra": [...]}) cuentan los valores, no las claves.
        listas = (
            [arbol_ts.campo(par, "value") for par in arbol_ts.nombrados(valor)]
            if valor.type == "dictionary"
            else [valor]
        )
        for lista in listas:
            for cadena in arbol_ts.recorrer(lista) if lista is not None else ():
                if cadena.type == "string" and (texto := _literal(cadena)) is not None:
                    yield texto


def _literal(cadena: Any) -> str | None:
    """Contenido de una cadena literal; None si tiene interpolaciones (f-string)."""
    partes = arbol_ts.hijos(cadena)
    if any(parte.type == "interpolation" for parte in partes):
        return None
    return "".join(
        arbol_ts.texto(parte) for parte in partes if parte.type == "string_content"
    )


# --- Ayudas para datos TOML ----------------------------------------------------------


def _tabla(valor: Any) -> dict[str, Any]:
    return valor if isinstance(valor, dict) else {}


def _cadenas(valor: Any) -> list[str]:
    return [x for x in valor if isinstance(x, str)] if isinstance(valor, list) else []


def _claves(valor: Any) -> Iterator[str]:
    """Nombres de las tablas de Poetry y Pipfile (`requests = "*"`), sin `python`."""
    for clave in _tabla(valor):
        if clave.lower() != "python":
            yield clave
