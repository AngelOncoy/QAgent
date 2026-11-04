"""Pruebas unitarias para la selección de versión de Python en el sandbox (sin Docker).

Cubre:
- Generación de etiquetas base según la versión (3.11 por defecto como 'base', otras como 'base-pyX.Y').
- Reconocimiento de versiones e imágenes base de Python.
- Recetas dinámicas para imágenes base de Python.
- Derivación de imágenes de dependencias con hash diferenciado por versión.
- Argumentos de construcción (buildargs) para la imagen base en Docker.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from docker.errors import ImageNotFound

from qagent.sandbox import (
    IMAGEN_BASE,
    VERSION_PYTHON_DEFECTO,
    asegurar_imagen,
    construir_imagen_base,
    es_imagen_base_python,
    etiqueta_base_python,
    preparar_imagen,
    receta_de,
    version_de_imagen_base,
)
from qagent.sandbox.imagen import (
    _dockerfile_pip,
    etiqueta_para_dependencias,
    etiqueta_para_requirements,
)
from qagent.sandbox.librerias import asegurar_librerias_sistema


class DockerSimulado:
    """Cliente Docker simulado para verificar llamadas de construcción sin Docker real."""

    def __init__(self, *existentes: str) -> None:
        self.existentes = set(existentes)
        self.construcciones: list[dict] = []
        self.cliente = MagicMock()
        self.cliente.images.get.side_effect = self._get
        self.cliente.images.build.side_effect = self._build

    def _get(self, etiqueta: str) -> MagicMock:
        if etiqueta not in self.existentes:
            raise ImageNotFound(etiqueta)
        img = MagicMock()
        img.tags = [etiqueta]
        return img

    def _build(self, path: str, tag: str, **kwargs) -> tuple:
        raiz = Path(path)
        dockerfile = (
            (raiz / "Dockerfile").read_text(encoding="utf-8")
            if (raiz / "Dockerfile").exists()
            else kwargs.get("fileobj")
        )
        self.construcciones.append(
            {
                "tag": tag,
                "path": path,
                "buildargs": kwargs.get("buildargs"),
                "dockerfile": dockerfile,
            }
        )
        self.existentes.add(tag)
        return MagicMock(), iter([])


# --- Etiquetas e identificación de versiones ------------------------------------------


@pytest.mark.parametrize(
    "version, esperada",
    [
        ("3.11", "qagent-sandbox:base"),
        ("3.10", "qagent-sandbox:base-py3.10"),
        ("3.12", "qagent-sandbox:base-py3.12"),
        ("3.13", "qagent-sandbox:base-py3.13"),
        ("3.14", "qagent-sandbox:base-py3.14"),
    ],
)
def test_etiqueta_base_python(version: str, esperada: str) -> None:
    assert etiqueta_base_python(version) == esperada


@pytest.mark.parametrize(
    "etiqueta, version_esperada",
    [
        ("qagent-sandbox:base", "3.11"),
        ("qagent-sandbox:base-py3.10", "3.10"),
        ("qagent-sandbox:base-py3.12", "3.12"),
        ("qagent-sandbox:base-py3.13", "3.13"),
        ("qagent-sandbox:base-py3.14", "3.14"),
        ("qagent-sandbox:node", None),
        ("qagent-sandbox:java", None),
        ("qagent-sandbox:req-abc123456789", None),
    ],
)
def test_version_de_imagen_base(etiqueta: str, version_esperada: str | None) -> None:
    assert version_de_imagen_base(etiqueta) == version_esperada


def test_es_imagen_base_python() -> None:
    assert es_imagen_base_python("qagent-sandbox:base") is True
    assert es_imagen_base_python("qagent-sandbox:base-py3.12") is True
    assert es_imagen_base_python("qagent-sandbox:node") is False
    assert es_imagen_base_python("qagent-sandbox:java") is False
    assert es_imagen_base_python("qagent-sandbox:req-123456789abc") is False


# --- Recetas de imágenes base ---------------------------------------------------------


def test_receta_de_base_por_defecto() -> None:
    receta = receta_de(IMAGEN_BASE)
    assert receta.imagen == IMAGEN_BASE
    assert version_de_imagen_base(receta.imagen) == VERSION_PYTHON_DEFECTO


def test_receta_de_base_version_especifica() -> None:
    receta = receta_de("qagent-sandbox:base-py3.12")
    assert receta.imagen == "qagent-sandbox:base-py3.12"
    assert version_de_imagen_base(receta.imagen) == "3.12"


def test_receta_de_desconocida_falla() -> None:
    with pytest.raises(ValueError, match="no es una imagen base del sandbox"):
        receta_de("qagent-sandbox:desconocida")


# --- Hash de dependencias según versión ----------------------------------------------


def test_hash_dependencias_difiere_por_version(tmp_path: Path) -> None:
    req = tmp_path / "requirements.txt"
    req.write_text("pytest>=7.0.0\nrequests==2.31.0\n", encoding="utf-8")
    contenido = req.read_bytes()

    tag_311 = etiqueta_para_requirements(contenido, version="3.11")
    tag_312 = etiqueta_para_requirements(contenido, version="3.12")
    tag_310 = etiqueta_para_requirements(contenido, version="3.10")

    # Mismo contenido, pero hashes distintos porque la versión de Python cambia
    assert tag_311 != tag_312
    assert tag_311 != tag_310
    assert tag_312 != tag_310

    # Compatibilidad hacia atrás: sin versión es 3.11
    assert tag_311 == etiqueta_para_requirements(contenido)

    # Vía etiqueta_para_dependencias con imagen_base
    dep_311 = etiqueta_para_dependencias(
        "req-", {"requirements.txt": contenido}, imagen_base="qagent-sandbox:base"
    )
    dep_312 = etiqueta_para_dependencias(
        "req-",
        {"requirements.txt": contenido},
        imagen_base="qagent-sandbox:base-py3.12",
    )
    assert dep_311 == tag_311
    assert dep_312 == tag_312
    assert dep_311 != dep_312


def test_dockerfile_pip_usa_base_especificada() -> None:
    df_311 = _dockerfile_pip(base="qagent-sandbox:base", archivos=["requirements.txt"])
    assert "FROM qagent-sandbox:base" in df_311

    df_312 = _dockerfile_pip(
        base="qagent-sandbox:base-py3.12", archivos=["requirements.txt"]
    )
    assert "FROM qagent-sandbox:base-py3.12" in df_312


# --- Construcción con Docker simulado --------------------------------------------------


def test_construir_imagen_base_pasa_buildarg_version() -> None:
    sim = DockerSimulado()
    construir_imagen_base(cliente=sim.cliente, imagen="qagent-sandbox:base-py3.12")

    assert len(sim.construcciones) == 1
    c = sim.construcciones[0]
    assert c["tag"] == "qagent-sandbox:base-py3.12"
    assert c["buildargs"] == {"PYTHON_VERSION": "3.12"}


def test_asegurar_imagen_construye_si_no_existe(tmp_path: Path) -> None:
    sim = DockerSimulado()
    asegurar_imagen(tmp_path, cliente=sim.cliente, imagen="qagent-sandbox:base-py3.12")

    assert "qagent-sandbox:base-py3.12" in sim.existentes
    assert sim.construcciones[0]["buildargs"] == {"PYTHON_VERSION": "3.12"}


def test_preparar_imagen_proyecto_con_requirements_en_312(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("pytest\n", encoding="utf-8")

    # Simulamos que la base ya existe
    sim = DockerSimulado("qagent-sandbox:base-py3.12")
    imagen_final = preparar_imagen(
        tmp_path, cliente=sim.cliente, imagen="qagent-sandbox:base-py3.12"
    )

    # Verificamos que se construyó una imagen derivada usando la base 3.12
    assert imagen_final.startswith("qagent-sandbox:req-")
    assert len(sim.construcciones) == 1
    assert "FROM qagent-sandbox:base-py3.12" in sim.construcciones[0]["dockerfile"]


def test_asegurar_librerias_sistema_respeta_base_python_versionada() -> None:
    sim = DockerSimulado("qagent-sandbox:base-py3.12")

    # Las imágenes base ya incluyen las librerías del sistema en el Dockerfile;
    # no deben generar una imagen con sufijo -sis ni invocar construcción
    resultado = asegurar_librerias_sistema(
        "qagent-sandbox:base-py3.12",
        cliente=sim.cliente,
    )
    assert resultado.imagen == "qagent-sandbox:base-py3.12"
    assert len(sim.construcciones) == 0
