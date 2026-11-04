"""Prueba de integración en Docker para Python 3.12 (ADR-013).

Verifica que un proyecto que declara Python 3.12 y utiliza sintaxis exclusiva de 3.12
(PEP 695: type parameter syntax `type MiTipo = ...` y funciones genéricas `def f[T](x: T)`)
se ejecuta y aprueba sus pruebas dentro del sandbox Docker etiquetado `qagent-sandbox:base-py3.12`.

Se omite automáticamente si Docker no está disponible.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from qagent.lenguajes import adaptador_para
from qagent.sandbox import (
    asegurar_imagen,
    construir_imagen_base,
    ejecutar_pruebas,
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


def test_proyecto_sintaxis_python312_en_sandbox_docker(
    cliente_docker, imagen_base_py312, tmp_path: Path
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
