"""Pruebas del mecanismo de las pruebas `docker` (#250): opción, aviso y limpieza.

Ninguna usa Docker: el cliente es un doble que devuelve las imágenes de antes y de después.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests import conftest, soporte_docker

pytest_plugins = ["pytester"]

BASE = "qagent-sandbox:base"


class ImagenesFalsas:
    """`cliente.images` de Docker: cada `list` devuelve el siguiente estado."""

    def __init__(self, *estados: list[str], fallan: tuple[str, ...] = ()) -> None:
        self.estados = list(estados)
        self.fallan = fallan
        self.borradas: list[str] = []
        self.filtros: list[str] = []

    def list(self, name: str):
        self.filtros.append(name)
        etiquetas = self.estados.pop(0) if len(self.estados) > 1 else self.estados[0]
        return [SimpleNamespace(tags=[etiqueta]) for etiqueta in etiquetas]

    def remove(self, etiqueta: str) -> None:
        if etiqueta in self.fallan:
            raise RuntimeError("image is being used by a running container")
        self.borradas.append(etiqueta)


def cliente(*estados: list[str], fallan: tuple[str, ...] = ()):
    return SimpleNamespace(images=ImagenesFalsas(*estados, fallan=fallan))


# --- cuándo se activan ---


@pytest.mark.parametrize(
    ("opcion", "expresion", "esperado"),
    [
        (False, "", False),
        (True, "", True),
        (False, "docker", True),
        (False, "docker and not red", True),
        (False, "not docker", False),
        (False, "not  docker and not red", False),
        (False, "not red", False),
        (True, "not docker", True),
        (False, "dockerizado", False),
    ],
)
def test_pruebas_docker_activas(opcion, expresion, esperado):
    assert soporte_docker.pruebas_docker_activas(opcion, expresion) is esperado


def test_aviso_dice_cuanto_tardan_y_ocupan():
    aviso = soporte_docker.texto_aviso(60, conservar=False)
    assert "60 pruebas" in aviso
    assert "minutos" in aviso and "GB" in aviso
    assert "--conservar-imagenes" in aviso
    assert "1 prueba " in soporte_docker.texto_aviso(1, conservar=True)


# --- qué imágenes se borran ---


def test_etiquetas_qagent_solo_del_repositorio():
    falso = cliente([BASE, "qagent-sandbox:req-1", "node:20-bookworm"])
    assert soporte_docker.etiquetas_qagent(falso) == {BASE, "qagent-sandbox:req-1"}
    assert falso.images.filtros == ["qagent-sandbox"]


def test_imagenes_creadas_no_toca_las_previas_la_base_ni_terceros():
    antes = {BASE, "qagent-sandbox:node", "qagent-sandbox:req-viejo"}
    despues = antes | {
        "qagent-sandbox:java",
        "qagent-sandbox:java-abc",
        "qagent-sandbox:req-nuevo",
        "eclipse-temurin:21",
    }
    assert soporte_docker.imagenes_creadas(antes, despues) == [
        "qagent-sandbox:java-abc",
        "qagent-sandbox:req-nuevo",
        "qagent-sandbox:java",
    ]


def test_imagen_base_creada_por_las_pruebas_no_se_borra():
    assert soporte_docker.imagenes_creadas(set(), {BASE}) == []


def test_borrar_imagenes_sigue_si_una_falla():
    falso = cliente([], fallan=("qagent-sandbox:req-1",))
    borradas, errores = soporte_docker.borrar_imagenes(
        falso, ["qagent-sandbox:req-1", "qagent-sandbox:java"]
    )
    assert borradas == ["qagent-sandbox:java"]
    assert list(errores) == ["qagent-sandbox:req-1"]
    assert "running container" in errores["qagent-sandbox:req-1"]


# --- los hooks, en una sesión de pytest aparte ---

CONFTEST = """
from tests.conftest import (
    pytest_addoption,
    pytest_collection_modifyitems,
    pytest_sessionfinish,
    pytest_terminal_summary,
)
"""
PRUEBAS = """
import pytest

@pytest.mark.docker
def test_con_docker():
    pass

def test_sin_docker():
    pass
"""


@pytest.fixture
def sesion(pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch):
    """Sesión de pytest con los hooks de `tests/conftest.py` y un Docker falso."""
    pytester.makeconftest(CONFTEST)
    pytester.makepyfile(test_docker_falso=PRUEBAS)
    pytester.makeini("[pytest]\nmarkers =\n    docker: con Docker\n")
    falso = cliente([BASE], [BASE, "qagent-sandbox:req-nuevo", "qagent-sandbox:java"])
    monkeypatch.setattr(conftest, "_cliente_docker", lambda: falso)
    return pytester, falso


def test_sin_opcion_las_pruebas_docker_se_omiten(sesion):
    pytester, falso = sesion
    resultado = pytester.runpytest("-rs")
    resultado.assert_outcomes(passed=1, skipped=1)
    resultado.stdout.fnmatch_lines(["*se activa con --docker*"])
    assert falso.images.filtros == [] and falso.images.borradas == []


def test_con_opcion_avisa_corre_y_borra_las_imagenes_nuevas(sesion):
    pytester, falso = sesion
    resultado = pytester.runpytest("--docker")
    resultado.assert_outcomes(passed=2)
    resultado.stdout.fnmatch_lines(
        ["*Pruebas con Docker real activadas (1 prueba)*", "*borrada*req-nuevo*"]
    )
    assert falso.images.borradas == [
        "qagent-sandbox:req-nuevo",
        "qagent-sandbox:java",
    ]


def test_menos_m_docker_tambien_las_activa(sesion):
    pytester, falso = sesion
    resultado = pytester.runpytest("-m", "docker")
    resultado.assert_outcomes(passed=1, deselected=1)
    assert "qagent-sandbox:java" in falso.images.borradas


def test_conservar_imagenes_no_borra_nada(sesion):
    pytester, falso = sesion
    resultado = pytester.runpytest("--docker", "--conservar-imagenes")
    resultado.assert_outcomes(passed=2)
    resultado.stdout.fnmatch_lines(["*Pruebas con Docker real activadas*"])
    assert falso.images.filtros == [] and falso.images.borradas == []


def test_sin_docker_disponible_no_intenta_borrar(sesion, monkeypatch):
    pytester, falso = sesion
    monkeypatch.setattr(conftest, "_cliente_docker", lambda: None)
    resultado = pytester.runpytest("--docker")
    resultado.assert_outcomes(passed=2)
    assert falso.images.borradas == []
