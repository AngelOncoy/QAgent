"""Huellas Java para caché de mutación: solo análisis estático (#180)."""

from pathlib import Path

import pytest

from qagent.lenguajes import JavaAdapter
from qagent.orchestrator.regresion import huellas_de_objetivos

MODULO = "src/main/java/ejemplo/Banco.java"
FUENTE = """package ejemplo;
public class Banco {
    private static int factor = 2;
    /** Multiplica por el factor configurado. */
    public static int calcular(int valor) { return valor * factor; }
    private static int auxiliar() { return 1; }
}
"""


def test_huellas_disponibles_sin_habilitar_la_corrida_java(tmp_path: Path) -> None:
    """El recolector común obtiene Java sin declarar completo su adaptador."""
    archivo = tmp_path / MODULO
    archivo.parent.mkdir(parents=True)
    archivo.write_text(FUENTE, encoding="utf-8")
    adaptador = JavaAdapter()
    huellas = adaptador.huellas_de_archivo(FUENTE, MODULO)
    assert not adaptador.completo
    assert set(huellas) == {"Banco.calcular"}
    assert len(huellas["Banco.calcular"]) == 64
    assert huellas_de_objetivos(tmp_path) == {
        (MODULO, "Banco.calcular"): huellas["Banco.calcular"]
    }
    assert adaptador.funciones_de_modulo(tmp_path, MODULO) == [
        {"nombre": "Banco.calcular", "linea": 5}
    ]


@pytest.mark.parametrize(
    ("anterior", "nuevo"),
    [
        ("valor * factor", "valor + factor"),
        ("factor = 2", "factor = 3"),
        ("return 1", "return 2"),
        ("Multiplica", "Calcula"),
    ],
)
def test_cambios_de_metodo_o_contexto_invalidan_huella(
    anterior: str, nuevo: str
) -> None:
    """Cambiar cuerpo, campo, auxiliar o documentación fuerza recalcular el score."""
    adaptador = JavaAdapter()
    original = adaptador.huellas_de_archivo(FUENTE, MODULO)
    assert original == adaptador.huellas_de_archivo(FUENTE, MODULO)
    assert original != adaptador.huellas_de_archivo(
        FUENTE.replace(anterior, nuevo), MODULO
    )


@pytest.mark.parametrize(
    "fuente",
    [
        "public class Rota {",
        "public class Banco { public int x() { return 1; } public int x(int a) { return a; } }",
    ],
)
def test_fuentes_invalidas_o_ambiguas_no_se_reutilizan(
    fuente: str, tmp_path: Path
) -> None:
    """Sintaxis inválida y sobrecargas producen None y ninguna ubicación de método."""
    archivo = tmp_path / "Banco.java"
    archivo.write_text(fuente, encoding="utf-8")
    adaptador = JavaAdapter()
    assert adaptador.huellas_de_archivo(fuente, "Banco.java") is None
    assert adaptador.funciones_de_modulo(tmp_path, "Banco.java") == []
    assert adaptador.funciones_de_modulo(tmp_path, "no-existe.java") == []


def test_ruta_externa_no_se_lee(tmp_path: Path) -> None:
    """La consulta de líneas rechaza una ruta que sale de la raíz del proyecto."""
    raiz = tmp_path / "proyecto"
    raiz.mkdir()
    (tmp_path / "Banco.java").write_text(FUENTE, encoding="utf-8")
    assert JavaAdapter().funciones_de_modulo(raiz, "../Banco.java") == []
