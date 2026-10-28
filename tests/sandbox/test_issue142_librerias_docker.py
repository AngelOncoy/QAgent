"""Issue 142 con Docker real: un proyecto con opencv-python importa cv2 sin simularlo.

Necesita Docker y, la primera vez, internet (descarga opencv y los paquetes del
sistema). Después reutiliza las imágenes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from qagent.sandbox import ejecutar_pruebas, preparar_imagen
from qagent.sandbox.librerias import asegurar_librerias_sistema, etiqueta_final

pytestmark = [pytest.mark.docker, pytest.mark.red]

PRUEBA = """\
from vision import alto_y_ancho


def test_una_imagen_negra_tiene_su_forma():
    assert alto_y_ancho(4, 3) == (4, 3)
"""


@pytest.fixture
def proyecto_opencv(tmp_path: Path) -> Path:
    """Proyecto que importa OpenCV, como APP-RF."""
    raiz = tmp_path / "proyecto"
    raiz.mkdir()
    (raiz / "requirements.txt").write_text("opencv-python==4.11.0.86\n", "utf-8")
    (raiz / "vision.py").write_text(
        "import cv2\n"
        "import numpy as np\n\n\n"
        "def alto_y_ancho(alto: int, ancho: int) -> tuple[int, int]:\n"
        '    """Forma (alto, ancho) de una imagen negra en escala de grises."""\n'
        "    gris = cv2.cvtColor(np.zeros((alto, ancho, 3), np.uint8), cv2.COLOR_BGR2GRAY)\n"
        "    return gris.shape\n",
        "utf-8",
    )
    return raiz


def _correr(imagen: str, proyecto: Path, tmp_path: Path):
    tests = tmp_path / "tests"
    tests.mkdir(exist_ok=True)
    (tests / "test_generado.py").write_text(PRUEBA, "utf-8")
    return ejecutar_pruebas(imagen, proyecto, tests, "vision")


def test_opencv_importa_en_la_imagen_final(
    imagen_base, cliente_docker, proyecto_opencv, tmp_path
) -> None:
    dependencias = preparar_imagen(proyecto_opencv, cliente=cliente_docker)

    # Solo con pip, cv2 no carga: falta libGL.so.1 (lo que pasaba con APP-RF).
    antes = _correr(dependencias, proyecto_opencv, tmp_path)
    assert antes.exit_code != 0
    assert "libGL.so.1" in antes.stdout + antes.stderr

    entorno = asegurar_librerias_sistema(dependencias, cliente_docker)

    assert entorno.imagen == etiqueta_final(dependencias)
    assert entorno.faltantes == []
    despues = _correr(entorno.imagen, proyecto_opencv, tmp_path)
    assert despues.exit_code == 0, despues.stdout + despues.stderr
