"""QAgent: sistema multiagente que genera y valida pruebas pytest para código Python."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

#: Nombre del paquete en PyPI (`pip install qagent-pytest`). El producto y el `import`
#: siguen siendo QAgent / `qagent`; «qagent» en PyPI es de otro proyecto (TA-06).
DISTRIBUCION = "qagent-pytest"

try:
    #: Versión instalada; la única fuente es `version` en pyproject.toml.
    __version__ = _version(DISTRIBUCION)
except PackageNotFoundError:  # ejecutado desde src/ sin instalar el paquete
    __version__ = "0.0.0+desarrollo"
