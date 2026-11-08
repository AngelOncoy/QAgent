"""Candidatas y cadenas de las pruebas de integración interna (#245, ADR-014)."""

from __future__ import annotations

from pathlib import Path

from qagent.analysis.analyzer import analizar_proyecto
from qagent.analysis.integracion import (
    candidatas,
    construir_cadena,
    efectos_de,
    lector_de_proyecto,
)
from qagent.config import Integracion, cargar_configuracion


def _proyecto(tmp_path: Path, archivos: dict[str, str]) -> Path:
    for nombre, contenido in archivos.items():
        (tmp_path / nombre).write_text(contenido, encoding="utf-8")
    return tmp_path


APP = (
    "import requests\n"
    "from precios import precio, descuento, remoto\n\n"
    "def total(p, q):\n"
    '    """Total del pedido."""\n'
    "    return precio(p) * q - descuento(p)\n\n"
    "def pedir(x):\n"
    "    return remoto(x)\n\n"
    "def sola(x):\n"
    "    return x\n"
)
PRECIOS = (
    "import requests\nimport time\n\n"
    "def precio(p):\n    return p\n\n"
    "def descuento(p):\n    return p * 0.1\n\n"
    "def remoto(x):\n    return requests.get(x)\n"
)


def test_la_funcion_que_llama_a_internas_puras_es_candidata(tmp_path: Path) -> None:
    raiz = _proyecto(tmp_path, {"app.py": APP, "precios.py": PRECIOS})
    modulos = analizar_proyecto(raiz)["modulos"]
    cadenas = candidatas(modulos, lector_de_proyecto(raiz))
    assert [c.raiz for c in cadenas] == ["total"]
    cadena = cadenas[0]
    assert cadena.funciones[0] == "total"
    assert set(cadena.funciones) == {"total", "precio", "descuento"}
    assert cadena.modulos["precio"] == "precios.py"
    assert cadena.a_simular == ()


def test_si_todas_las_internas_son_de_efecto_no_es_candidata(tmp_path: Path) -> None:
    raiz = _proyecto(tmp_path, {"app.py": APP, "precios.py": PRECIOS})
    modulos = analizar_proyecto(raiz)["modulos"]
    assert construir_cadena(modulos, "app.py", "pedir", lector_de_proyecto(raiz)) is None


def test_una_interna_de_efecto_se_simula_y_no_entra_en_la_cadena(
    tmp_path: Path,
) -> None:
    app = (
        "from precios import precio, remoto\n\n"
        "def total(p):\n    return precio(p) + remoto(p)\n"
    )
    raiz = _proyecto(tmp_path, {"app.py": app, "precios.py": PRECIOS})
    modulos = analizar_proyecto(raiz)["modulos"]
    cadena = construir_cadena(modulos, "app.py", "total", lector_de_proyecto(raiz))
    assert cadena is not None
    assert cadena.funciones == ("total", "precio")
    assert cadena.a_simular == ("precios.py::remoto",)


def test_el_limite_de_funciones_recorta_la_cadena(tmp_path: Path) -> None:
    raiz = _proyecto(tmp_path, {"app.py": APP, "precios.py": PRECIOS})
    modulos = analizar_proyecto(raiz)["modulos"]
    cadena = construir_cadena(
        modulos, "app.py", "total", lector_de_proyecto(raiz), max_funciones=2
    )
    assert cadena is not None
    assert len(cadena.funciones) == 2
    assert cadena.recortada


def test_sin_poder_leer_el_modulo_se_trata_como_de_efecto(tmp_path: Path) -> None:
    raiz = _proyecto(tmp_path, {"app.py": APP, "precios.py": PRECIOS})
    modulos = analizar_proyecto(raiz)["modulos"]
    assert construir_cadena(modulos, "app.py", "total", lambda ruta: None) is None


def test_efectos_de_una_funcion() -> None:
    fuente = (
        "import os\nfrom datetime import datetime as dt\n\n"
        "def hoy():\n    return dt.now()\n\n"
        "def leer():\n    return open('x').read()\n\n"
        "def pura(a):\n    return a + 1\n\n"
        "def ruta():\n    return os.getcwd()\n"
    )
    assert efectos_de(fuente, "hoy") == ("datetime",)
    assert efectos_de(fuente, "leer") == ("builtins",)
    assert efectos_de(fuente, "ruta") == ("os",)
    assert efectos_de(fuente, "pura") == ()


def test_la_configuracion_trae_los_limites_de_la_cadena(tmp_path: Path) -> None:
    resultado = cargar_configuracion(
        ruta_env=tmp_path / ".env",
        simulado=True,
        ruta_local=tmp_path / "config.local.toml",
    )
    assert resultado.config is not None
    assert resultado.config.integracion == Integracion(
        profundidad_max=2, max_funciones=4
    )
