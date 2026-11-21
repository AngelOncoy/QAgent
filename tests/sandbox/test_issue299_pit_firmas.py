"""PIT distingue descriptores y excluye declaraciones antes de mutar (#299)."""

import shutil
from pathlib import Path

import pytest

from qagent.sandbox.mutacion import ERROR, OK
from qagent.sandbox.pit import interpretar_pit
from qagent.sandbox.pit_preparacion import preparar_pit
from tests.lenguajes.test_issue299_sobrecargas import codigo, preparar


def test_prepara_exclusion_sin_cambiar_cuerpos_ni_originales(tmp_path):
    original = tmp_path / "original"
    contrato = preparar(original)
    copia = tmp_path / "copia"
    shutil.copytree(original, copia)
    pruebas = tmp_path / "pruebas"
    pruebas.mkdir()
    (pruebas / "BancoTest.java").write_text(codigo(), encoding="utf-8")
    anteriores = {
        p.relative_to(original): p.read_bytes()
        for p in original.rglob("*")
        if p.is_file()
    }
    objetivos = preparar_pit(copia, pruebas, contrato["modulo"], ["Banco.f(int)"])
    assert objetivos == {"Banco.f(int)": ("ejemplo.Banco", "f", "(I)I")}
    fuente = (copia / contrato["modulo"]).read_text(encoding="utf-8")
    assert (
        "@qagent.internal.exclusion299.QAgentNoMutar public static String f" in fuente
    )
    assert (
        "@qagent.internal.exclusion299.QAgentNoMutar public static int f" not in fuente
    )
    assert fuente.count("\n") == (original / contrato["modulo"]).read_text(
        encoding="utf-8"
    ).count("\n")
    assert {
        p.relative_to(original): p.read_bytes()
        for p in original.rglob("*")
        if p.is_file()
    } == anteriores


def test_xml_pit_de_otra_firma_invalida_score_completo():
    xml = (Path(__file__).parents[1] / "fixtures/pit/critico-real.xml").read_text(
        encoding="utf-8"
    )
    objetivos = {"Criticos.critico(int)": ("qagent.Criticos", "critico", "(I)I")}
    correcto = interpretar_pit(xml, "Criticos.java", objetivos)
    assert correcto.funciones["Criticos.critico(int)"].estado == OK
    incorrecto = interpretar_pit(
        xml.replace("(I)I", "(J)I", 1), "Criticos.java", objetivos
    )
    assert incorrecto.funciones["Criticos.critico(int)"].estado == ERROR
    assert incorrecto.funciones["Criticos.critico(int)"].puntuacion is None


@pytest.mark.parametrize(
    "descriptor", ["(I)", "(I)Q", "(I)Ibasura", "(V)I", "(Ljava.lang.String;)I"]
)
def test_descriptor_invalido_no_recibe_score(descriptor):
    xml = (Path(__file__).parents[1] / "fixtures/pit/critico-real.xml").read_text(
        encoding="utf-8"
    )
    resultado = interpretar_pit(
        xml.replace("(I)I", descriptor),
        "Criticos.java",
        {"Criticos.critico": ("qagent.Criticos", "critico")},
    )
    assert resultado.funciones["Criticos.critico"].estado == ERROR
    assert resultado.funciones["Criticos.critico"].puntuacion is None


def test_objetivo_historico_no_suma_mutantes_de_otras_firmas():
    xml = (Path(__file__).parents[1] / "fixtures/pit/critico-real.xml").read_text(
        encoding="utf-8"
    )
    resultado = interpretar_pit(
        xml.replace("(I)I", "(J)I", 1),
        "Criticos.java",
        {"Criticos.critico": ("qagent.Criticos", "critico")},
    )
    assert resultado.funciones["Criticos.critico"].estado == ERROR
    assert resultado.funciones["Criticos.critico"].puntuacion is None
