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


# --- La versión que se muestra es siempre la real -----------------------------------


def test_la_interfaz_y_los_informes_no_tienen_una_version_fija():
    """Antes decían «v2.4» con QAgent en 0.1.0: la versión sale de pyproject.toml."""
    import re

    paquete = Path(qagent.__file__).parent
    archivos = [
        *(paquete / "frontend").rglob("*.js"),
        *(paquete / "frontend").rglob("*.html"),
    ]
    archivos.append(paquete / "storage" / "exportar_informe.py")
    fija = re.compile(
        r"(QAgent|Engine|Planner)[^\n]{0,12}\bv\d+\.\d+|class=\"ver\">v?\d"
    )
    con_version_fija = [
        p.relative_to(paquete).as_posix()
        for p in archivos
        if fija.search(p.read_text(encoding="utf-8"))
    ]
    assert con_version_fija == []


def test_la_app_le_entrega_su_version_a_la_interfaz():
    from qagent.app.desktop import DesktopAPI

    assert DesktopAPI().obtener_version() == qagent.__version__
