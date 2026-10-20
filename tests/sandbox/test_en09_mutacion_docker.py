"""EN-09: mutmut real dentro del sandbox, sobre un proyecto pequeño.

Se omiten si Docker no está disponible.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from qagent.sandbox import LimitesSandbox, ejecutar_mutacion
from qagent.sandbox.mutacion import CONFIG_PROPIA, OK

pytestmark = pytest.mark.docker

LIMITES = LimitesSandbox(cpus=1.0, memoria="256m", timeout_s=180)

CALC = '''from ayuda import tasa


def descuento(precio: float, vip: bool) -> float:
    """Aplica 10 % si es VIP y el precio supera 100."""
    if vip and precio > 100:
        return precio * tasa()
    return precio


def doble(x: int) -> int:
    """Devuelve el doble."""
    return x * 2
'''


def _escribir(raiz: Path, archivos: dict[str, str]) -> Path:
    for relativa, contenido in archivos.items():
        ruta = raiz / relativa
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(contenido, encoding="utf-8")
    return raiz


@pytest.fixture
def proyecto(tmp_path: Path) -> Path:
    """Módulo con dos funciones que importa otro archivo del proyecto."""
    return _escribir(
        tmp_path / "proyecto",
        {
            "pkg/__init__.py": "",
            "pkg/calc.py": CALC,
            "ayuda.py": "def tasa():\n    return 0.9\n",
        },
    )


def _pruebas(tmp_path: Path, codigo: str) -> Path:
    return _escribir(tmp_path / "tests", {"test_calc.py": codigo})


def test_una_prueba_debil_deja_sobrevivientes_reales(imagen_base, proyecto, tmp_path):
    """Si las pruebas quedaran fuera del proyecto, mutmut daría 100 % falso."""
    pruebas = _pruebas(
        tmp_path,
        "from pkg.calc import descuento\n\n"
        "def test_vip():\n    assert descuento(200, True) == 180\n",
    )

    resultado = ejecutar_mutacion(
        imagen_base,
        proyecto,
        pruebas,
        "pkg/calc.py",
        ["descuento"],
        LIMITES,
        inicios={"descuento": 4},
    )

    descuento = resultado.funciones["descuento"]
    assert descuento.estado == OK, resultado.salida
    assert descuento.detectados >= 1
    assert descuento.sobrevivientes, "una prueba débil debe dejar mutantes vivos"
    assert descuento.puntuacion is not None and descuento.puntuacion < 100
    cambios = " ".join(s.cambio for s in descuento.sobrevivientes)
    assert "101" in cambios or ">=" in cambios or " or " in cambios
    assert all(s.linea == 6 for s in descuento.sobrevivientes)


def test_solo_muta_las_funciones_pedidas(imagen_base, proyecto, tmp_path):
    pruebas = _pruebas(
        tmp_path,
        "from pkg.calc import descuento, doble\n\n"
        "def test_vip():\n    assert descuento(200, True) == 180\n\n"
        "def test_doble():\n    assert doble(2) == 4\n",
    )

    resultado = ejecutar_mutacion(
        imagen_base, proyecto, pruebas, "pkg/calc.py", ["doble"], LIMITES
    )

    assert set(resultado.funciones) == {"doble"}
    doble = resultado.funciones["doble"]
    assert doble.estado == OK, resultado.salida
    assert doble.puntuacion == 100.0
    assert all("doble" in s.mutante for s in doble.sobrevivientes)


def test_respeta_la_configuracion_propia_de_mutmut(imagen_base, proyecto, tmp_path):
    (proyecto / "pyproject.toml").write_text(
        '[tool.mutmut]\nsource_paths = ["pkg"]\n', encoding="utf-8"
    )
    pruebas = _pruebas(tmp_path, "def test_nada():\n    assert True\n")

    resultado = ejecutar_mutacion(
        imagen_base, proyecto, pruebas, "pkg/calc.py", ["doble"], LIMITES
    )

    assert resultado.funciones["doble"].estado == CONFIG_PROPIA
    assert resultado.funciones["doble"].puntuacion is None
