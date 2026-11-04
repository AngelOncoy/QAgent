"""Pruebas de integración en Docker para Python 3.12 y sandbox versionado (ADR-013).

Verifica contra el daemon Docker real:
1. Construcción y etiquetado de la imagen base `qagent-sandbox:base-py3.12`.
2. Verificación de que la versión interna del contenedor es efectivamente Python 3.12.
3. Construcción y etiquetado con hash de la imagen derivada con `requirements.txt`.
4. Diferenciación de hashes entre Python 3.11 y Python 3.12 con dependencias idénticas.
5. Ejecución de pruebas pytest dentro del contenedor sobre código con sintaxis PEP 695 de Python 3.12.

Se omite automáticamente si Docker Desktop no está disponible/iniciado.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from qagent.lenguajes import adaptador_para
from qagent.sandbox import (
    IMAGEN_BASE,
    asegurar_imagen,
    construir_imagen_base,
    ejecutar_pruebas,
    preparar_imagen,
)
from qagent.sandbox.imagen import _imagen_existe

pytestmark = pytest.mark.docker


def _escribir(raiz: Path, archivos: dict[str, str]) -> Path:
    for ruta, texto in archivos.items():
        destino = raiz / ruta
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto, encoding="utf-8")
    return raiz


@pytest.fixture(scope="session")
def imagen_base_py312(cliente_docker) -> str:
    """Asegura que la imagen base de Python 3.12 existe en el Docker local."""
    etiqueta = "qagent-sandbox:base-py3.12"
    if not _imagen_existe(cliente_docker, etiqueta):
        construir_imagen_base(cliente_docker, imagen=etiqueta)
    return etiqueta


def test_imagen_base_py312_reporta_version_real_python(
    cliente_docker, imagen_base_py312: str
) -> None:
    """Verifica que el contenedor de la imagen base ejecuta realmente Python 3.12."""
    salida = cliente_docker.containers.run(
        imagen_base_py312,
        ["python", "--version"],
        remove=True,
    )
    texto = (
        salida.decode("utf-8").strip()
        if isinstance(salida, bytes)
        else str(salida).strip()
    )
    assert texto.startswith("Python 3.12")


def test_hash_y_construccion_real_de_dependencias_en_docker(
    cliente_docker, imagen_base_py312: str, tmp_path: Path
) -> None:
    """Verifica que la imagen derivada con requirements.txt se construye y etiqueta en Docker real."""
    proyecto = _escribir(
        tmp_path / "proyecto_deps",
        {
            "requirements.txt": "packaging\n",
        },
    )
    tag_derivada = preparar_imagen(
        proyecto,
        cliente=cliente_docker,
        imagen=imagen_base_py312,
    )
    assert tag_derivada.startswith("qagent-sandbox:req-")
    # La imagen existe físicamente en el Docker local
    img = cliente_docker.images.get(tag_derivada)
    assert tag_derivada in img.tags


def test_diferencia_de_hash_y_entornos_entre_versiones_en_docker(
    cliente_docker, imagen_base_py312: str, tmp_path: Path
) -> None:
    """Verifica que el mismo requirements.txt genera tags distintos para Python 3.11 y 3.12 en Docker."""
    proyecto = _escribir(
        tmp_path / "proyecto_comparacion",
        {
            "requirements.txt": "packaging\n",
        },
    )
    tag_312 = preparar_imagen(
        proyecto,
        cliente=cliente_docker,
        imagen=imagen_base_py312,
    )

    if not _imagen_existe(cliente_docker, IMAGEN_BASE):
        construir_imagen_base(cliente_docker, imagen=IMAGEN_BASE)

    tag_311 = preparar_imagen(
        proyecto,
        cliente=cliente_docker,
        imagen=IMAGEN_BASE,
    )

    assert tag_312.startswith("qagent-sandbox:req-")
    assert tag_311.startswith("qagent-sandbox:req-")
    assert tag_312 != tag_311


def test_proyecto_sintaxis_python312_en_sandbox_docker(
    cliente_docker, imagen_base_py312: str, tmp_path: Path
) -> None:
    # Proyecto con sintaxis PEP 695 (Python 3.12+)
    proyecto = _escribir(
        tmp_path / "proyecto_py312",
        {
            ".python-version": "3.12\n",
            "generico.py": (
                "type Id = int\n\ndef identidad[T](valor: T) -> T:\n    return valor\n"
            ),
        },
    )

    # Verificamos que el adaptador detecta 3.12 y pide la imagen correspondiente
    adaptador = adaptador_para("python")
    version = adaptador.resolver_version_python(proyecto)
    assert version == "3.12"

    entorno = adaptador.entorno_sandbox(proyecto)
    assert entorno.imagen == "qagent-sandbox:base-py3.12"

    imagen_preparada = asegurar_imagen(
        proyecto,
        imagen=entorno.imagen,
        cliente=cliente_docker,
    )

    # Creamos un test pytest que importa y prueba la función con sintaxis 3.12
    tests = _escribir(
        tmp_path / "tests",
        {
            "test_generico.py": (
                "from generico import identidad, Id\n"
                "\n"
                "def test_identidad():\n"
                "    val: Id = 42\n"
                "    assert identidad(val) == 42\n"
                "    assert identidad('hola') == 'hola'\n"
            ),
        },
    )

    resultado = ejecutar_pruebas(
        proyecto,
        tests,
        imagen=imagen_preparada,
        cliente=cliente_docker,
    )

    assert resultado.exitoso is True
    assert resultado.codigo_salida == 0
    assert resultado.informe is not None
    assert resultado.informe.pasaron == 1
    assert resultado.informe.fallaron == 0
