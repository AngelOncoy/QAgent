"""Pruebas sin Docker del XML PIT (#180), con informe real y casos sintéticos."""

from pathlib import Path

import pytest

from qagent.sandbox.mutacion import ERROR, OK
from qagent.sandbox.pit import interpretar_pit

OBJETIVOS = {"Banco.sumar": ("ejemplo.Banco", "sumar")}


def test_informe_real_grabado() -> None:
    """Reproduce el score y las ubicaciones del XML obtenido en Docker con PIT."""
    archivo = Path(__file__).resolve().parents[1] / "fixtures/pit/critico-real.xml"
    resultado = interpretar_pit(
        archivo.read_text(encoding="utf-8"),
        "src/main/java/qagent/Criticos.java",
        {"Criticos.critico": ("qagent.Criticos", "critico")},
    )
    funcion = resultado.funciones["Criticos.critico"]
    assert funcion.estado == OK
    assert funcion.detectados == 3
    assert len(funcion.sobrevivientes) == 2
    assert funcion.puntuacion == 60.0
    assert {s.linea for s in funcion.sobrevivientes} == {6, 7}
    assert all(s.cambio for s in funcion.sobrevivientes)


def _mutante(estado: str, indice: int = 0, clase: str = "ejemplo.Banco") -> str:
    """Construye XML sintético de un mutante; no es evidencia de una ejecución real."""
    return f'''<mutation status="{estado}">
      <mutatedClass>{clase}</mutatedClass><mutatedMethod>sumar</mutatedMethod>
      <methodDescription>(II)I</methodDescription><lineNumber>12</lineNumber>
      <mutator>MathMutator</mutator><indexes><index>{indice}</index></indexes>
      <description>Reemplazó suma por resta</description>
    </mutation>'''


def test_score_y_sobrevivientes() -> None:
    """Dos detectados y dos sobrevivientes deben dar 50 %, con ubicación del cambio."""
    xml = (
        "<mutations>"
        + "".join(
            _mutante(e, i)
            for i, e in enumerate(["KILLED", "TIMED_OUT", "SURVIVED", "NO_COVERAGE"])
        )
        + "</mutations>"
    )
    resultado = interpretar_pit(xml, "Banco.java", OBJETIVOS)
    funcion = resultado.funciones["Banco.sumar"]
    assert resultado.modulo == "Banco.java"
    assert funcion.estado == OK
    assert funcion.detectados == 2
    assert funcion.puntuacion == 50.0
    assert len(funcion.sobrevivientes) == 2
    assert funcion.sobrevivientes[0].linea == 12
    assert "Reemplazó suma por resta" in funcion.sobrevivientes[0].cambio


@pytest.mark.parametrize(
    "estado", ["NON_VIABLE", "RUN_ERROR", "MEMORY_ERROR", "NOT_STARTED", "STARTED"]
)
def test_error_tecnico_no_inventa_score(estado: str) -> None:
    """Un mutante no evaluado no puede producir un score de éxito parcial."""
    xml = "<mutations>" + _mutante("KILLED") + _mutante(estado, 1) + "</mutations>"
    funcion = interpretar_pit(xml, "Banco.java", OBJETIVOS).funciones["Banco.sumar"]
    assert funcion.estado == ERROR
    assert funcion.puntuacion is None
    assert estado in funcion.mensaje


def test_sin_mutantes_no_es_cien_por_ciento() -> None:
    """Un informe vacío de mutantes debe dar None, no un score del 100 %."""
    funcion = interpretar_pit("<mutations/>", "Banco.java", OBJETIVOS).funciones[
        "Banco.sumar"
    ]
    assert funcion.estado == OK
    assert funcion.puntuacion is None
    assert funcion.mensaje


@pytest.mark.parametrize(
    "xml",
    [
        "",
        "<mutations>",
        "<otra/>",
        '<!DOCTYPE mutations [<!ENTITY x "texto">]><mutations/>',
        "<mutations>" + _mutante("DESCONOCIDO") + "</mutations>",
        "<mutations>" + _mutante("KILLED", clase="OtraClase") + "</mutations>",
        "<mutations>" + _mutante("KILLED") * 2 + "</mutations>",
        "<mutations><mutation status='KILLED'/></mutations>",
    ],
)
def test_informe_invalido_no_es_exito(xml: str) -> None:
    """XML inválido, duplicado o fuera de alcance devuelve error sin puntuación."""
    funcion = interpretar_pit(xml, "Banco.java", OBJETIVOS).funciones["Banco.sumar"]
    assert funcion.estado == ERROR
    assert funcion.puntuacion is None
