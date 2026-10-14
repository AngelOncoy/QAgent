"""TA-06: el nombre en PyPI (`qagent-pytest`) es uno solo en todo el repositorio.

Si `pyproject.toml`, `qagent.DISTRIBUCION` y la receta del ejecutable no coinciden,
`qagent --version` leería la versión de otro paquete (o ninguna).
"""

from __future__ import annotations

import sys
from pathlib import Path

import qagent

if sys.version_info >= (3, 11):
    import tomllib
else:  # Python 3.10
    import tomli as tomllib

RAIZ = Path(__file__).resolve().parents[1]


def _pyproject() -> dict:
    with open(RAIZ / "pyproject.toml", "rb") as archivo:
        return tomllib.load(archivo)


def test_el_nombre_en_pypi_es_el_mismo_en_el_codigo():
    assert _pyproject()["project"]["name"] == qagent.DISTRIBUCION == "qagent-pytest"


def test_el_comando_y_el_paquete_siguen_llamandose_qagent():
    proyecto = _pyproject()
    assert proyecto["project"]["scripts"] == {"qagent": "qagent.app.desktop:ejecutar"}
    assert Path(qagent.__file__).parent.name == "qagent"


def test_el_ejecutable_lleva_la_metadata_del_nombre_en_pypi():
    receta = (RAIZ / "packaging" / "windows" / "qagent.spec").read_text(
        encoding="utf-8"
    )
    assert f'copy_metadata("{qagent.DISTRIBUCION}")' in receta
