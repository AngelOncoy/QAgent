"""Pruebas de integración del sandbox con Docker real.

Se omiten si Docker no está disponible. Construyen la imagen base una vez si falta
(la primera corrida tarda unos minutos y necesita internet).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyagent.sandbox import (
    ejecutar_en_sandbox,
    ejecutar_pruebas,
    preparar_imagen,
)

pytestmark = pytest.mark.docker


def _escribir(raiz: Path, archivos: dict[str, str]) -> Path:
    """Crea los archivos indicados (ruta relativa → contenido) bajo `raiz`."""
    for relativa, contenido in archivos.items():
        ruta = raiz / relativa
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(contenido, encoding="utf-8")
    return raiz


@pytest.fixture
def proyecto_calc(tmp_path: Path) -> Path:
    """Proyecto mínimo con una función de dos ramas."""
    return _escribir(
        tmp_path / "proyecto",
        {
            "calc.py": (
                "def signo(x: int) -> str:\n"
                "    if x >= 0:\n"
                "        return 'positivo'\n"
                "    return 'negativo'\n"
            ),
        },
    )


def _tests(tmp_path: Path, codigo: str) -> Path:
    """Crea una carpeta de tests con un único archivo."""
    return _escribir(tmp_path / "tests", {"test_generado.py": codigo})


def test_prueba_que_pasa_devuelve_coverage_con_ramas(
    imagen_base, proyecto_calc, tmp_path
):
    tests = _tests(
        tmp_path,
        "from calc import signo\n\ndef test_positivo():\n    assert signo(1) == 'positivo'\n",
    )

    resultado = ejecutar_pruebas(imagen_base, proyecto_calc, tests, "calc")

    assert resultado.exit_code == 0, resultado.stdout
    assert resultado.coverage is not None
    assert resultado.coverage["meta"]["branch_coverage"] is True
    totales = resultado.coverage["totals"]
    assert totales["num_branches"] == 2
    assert totales["covered_branches"] == 1


def test_prueba_que_falla_devuelve_exit_code_y_stdout(
    imagen_base, proyecto_calc, tmp_path
):
    tests = _tests(
        tmp_path,
        "from calc import signo\n\ndef test_negativo():\n    assert signo(-1) == 'cero'\n",
    )

    resultado = ejecutar_pruebas(imagen_base, proyecto_calc, tests, "calc")

    assert resultado.exit_code != 0
    assert "test_negativo" in resultado.stdout
    assert (
        "AssertionError" in resultado.stdout
        or "assert 'negativo' == 'cero'" in resultado.stdout
    )


def test_sin_acceso_a_red(imagen_base, proyecto_calc, tmp_path):
    tests = _tests(
        tmp_path,
        "import socket\n\n"
        "def test_conectar():\n"
        "    socket.create_connection(('1.1.1.1', 53), timeout=3)\n",
    )

    resultado = ejecutar_pruebas(imagen_base, proyecto_calc, tests, "calc")

    assert resultado.exit_code != 0
    assert "OSError" in resultado.stdout or "unreachable" in resultado.stdout


def test_reservar_512mb_termina_por_memoria(imagen_base, proyecto_calc, tmp_path):
    # bytes * n escribe cada página; bytearray(n) no la tocaría y no superaría el límite.
    tests = _tests(
        tmp_path,
        "def test_memoria():\n    bloque = b'x' * (512 * 1024 * 1024)\n    assert bloque\n",
    )

    resultado = ejecutar_pruebas(imagen_base, proyecto_calc, tests, "calc")

    assert resultado.oom_killed is True
    assert resultado.exit_code != 0
    assert resultado.timed_out is False


def test_dependencia_del_requirements_disponible_sin_red(
    imagen_base, proyecto_calc, tmp_path
):
    (proyecto_calc / "requirements.txt").write_text("six==1.17.0\n", encoding="utf-8")
    tests = _tests(
        tmp_path,
        "import six\n\ndef test_six():\n    assert six.__version__ == '1.17.0'\n",
    )

    imagen = preparar_imagen(proyecto_calc)
    resultado = ejecutar_pruebas(imagen, proyecto_calc, tests, "calc")

    assert imagen.startswith("pyagent-sandbox:req-")
    assert resultado.exit_code == 0, resultado.stdout
    assert preparar_imagen(proyecto_calc) == imagen


def test_endpoint_fastapi_con_testclient(imagen_base, tmp_path):
    proyecto = _escribir(
        tmp_path / "api",
        {
            "requirements.txt": "fastapi==0.142.2\n",
            "app/__init__.py": "",
            "app/main.py": (
                "from fastapi import FastAPI\n\n"
                "app = FastAPI()\n\n"
                "@app.get('/salud', status_code=200)\n"
                "def salud() -> dict[str, str]:\n"
                "    return {'estado': 'ok'}\n"
            ),
        },
    )
    tests = _tests(
        tmp_path,
        "from fastapi.testclient import TestClient\n"
        "from app.main import app\n\n"
        "def test_salud():\n"
        "    respuesta = TestClient(app).get('/salud')\n"
        "    assert respuesta.status_code == 200\n"
        "    assert respuesta.json() == {'estado': 'ok'}\n",
    )

    imagen = preparar_imagen(proyecto)
    resultado = ejecutar_pruebas(imagen, proyecto, tests, "app")

    assert resultado.exit_code == 0, resultado.stdout
    assert resultado.coverage["totals"]["percent_covered"] == 100


def test_mutmut_disponible_en_la_imagen(imagen_base, tmp_path):
    # mutmut 3 necesita encontrar el código a mutar incluso para --version.
    proyecto = _escribir(tmp_path / "proyecto", {"src/modulo.py": "X = 1\n"})
    tests = _tests(tmp_path, "")

    resultado = ejecutar_en_sandbox(
        imagen_base, ["mutmut", "--version"], proyecto, tests
    )

    assert resultado.exit_code == 0, resultado.stderr
    assert "mutmut" in resultado.stdout


def test_proyecto_original_intacto(imagen_base, proyecto_calc, tmp_path):
    (proyecto_calc / ".env").write_text("CLAVE=secreta\n", encoding="utf-8")
    antes = {p: p.read_bytes() for p in proyecto_calc.rglob("*") if p.is_file()}
    tests = _tests(
        tmp_path,
        "import os\nfrom pathlib import Path\n\n"
        "def test_modifica_la_copia():\n"
        "    assert not os.path.exists('/work/proyecto/.env')\n"
        "    Path('/work/proyecto/calc.py').write_text('roto')\n"
        "    Path('/work/proyecto/nuevo.py').write_text('x')\n",
    )

    resultado = ejecutar_pruebas(imagen_base, proyecto_calc, tests, "calc")

    assert resultado.exit_code == 0, resultado.stdout
    despues = {p: p.read_bytes() for p in proyecto_calc.rglob("*") if p.is_file()}
    assert despues == antes
