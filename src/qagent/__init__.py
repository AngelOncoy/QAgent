"""QAgent: sistema multiagente que genera y valida pruebas pytest para código Python."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

try:
    #: Versión instalada; la única fuente es `version` en pyproject.toml.
    __version__ = _version("qagent")
except PackageNotFoundError:  # ejecutado desde src/ sin instalar el paquete
    __version__ = "0.0.0+desarrollo"
