"""PIT real, acotado a un método crítico, dentro de qagent-sandbox:java (#180)."""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from qagent.lenguajes import JavaAdapter
from qagent.sandbox.imagen import _imagen_existe
from qagent.sandbox.modelos import IMAGEN_JAVA
from qagent.sandbox.mutacion import OK

pytestmark = pytest.mark.docker


def test_pit_real_solo_metodo_critico(cliente_docker, tmp_path: Path) -> None:
    """Una prueba débil deja sobrevivientes del método crítico, nunca del otro.

    El proyecto usa las versiones ya preparadas por la imagen del equipo. No
    descarga dependencias ni ejecuta Maven en el anfitrión. Solo cuando se define
    QAGENT_GRABAR_PIT=1 se guarda el XML real, después de verificar el resultado,
    en tests/fixtures/pit/critico-real.xml para las pruebas de interpretación.
    """
    if not _imagen_existe(cliente_docker, IMAGEN_JAVA):
        pytest.skip("Falta construir qagent-sandbox:java; no se ha validado PIT real.")
    receta = (
        Path(__file__).resolve().parents[2]
        / "src/qagent/sandbox/java/calentamiento/pom.xml"
    )
    pom = ET.fromstring(receta.read_text(encoding="utf-8"))
    plugins = pom.find("{*}build/{*}plugins")
    for plugin in list(plugins):
        if plugin.findtext("{*}artifactId") == "pitest-maven":
            plugins.remove(
                plugin
            )  # La fixture es un proyecto sin configuración PIT propia.
    proyecto = tmp_path / "proyecto"
    modulo = "src/main/java/qagent/Criticos.java"
    fuente = proyecto / modulo
    fuente.parent.mkdir(parents=True)
    codigo = """package qagent;
/** Banco controlado para probar el alcance de PIT. */
public class Criticos {
    /** Duplica valores mayores a diez; en otro caso devuelve el valor. */
    public static int critico(int valor) {
        if (valor > 10) { return valor * 2; }
        return valor;
    }
    /** Método deliberadamente fuera de la selección de mutación. */
    public static int noCritico(int valor) { return valor + 1; }
}
"""
    fuente.write_text(codigo, encoding="utf-8")
    ET.ElementTree(pom).write(
        proyecto / "pom.xml", encoding="utf-8", xml_declaration=True
    )
    pom_original = (proyecto / "pom.xml").read_bytes()
    pruebas = tmp_path / "aprobadas"
    pruebas.mkdir()
    (pruebas / "test_hash.py").write_text(
        """package qagent;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
public class CriticosTest {
    @Test void soloCasoNormal() { assertEquals(40, Criticos.critico(20)); }
}
""",
        encoding="utf-8",
    )
    informes = []
    resultado = JavaAdapter().ejecutar_mutacion(
        IMAGEN_JAVA,
        proyecto,
        pruebas,
        modulo,
        ["Criticos.critico"],
        cliente=cliente_docker,
        al_informe=informes.append,
    )
    funcion = resultado.funciones["Criticos.critico"]
    assert funcion.estado == OK, f"{funcion.mensaje}\n{resultado.salida}"
    assert funcion.detectados >= 1, resultado.salida
    assert funcion.sobrevivientes, (
        "La prueba no cubre el límite y debe dejar mutantes vivos."
    )
    assert 0 < funcion.puntuacion < 100
    assert (proyecto / "pom.xml").read_bytes() == pom_original
    assert fuente.read_text(encoding="utf-8") == codigo
    assert len(informes) == 1
    raiz = ET.fromstring(informes[0])
    assert {m.findtext("mutatedClass") for m in raiz} == {"qagent.Criticos"}
    assert {m.findtext("mutatedMethod") for m in raiz} == {"critico"}
    assert not (proyecto / ".qagent-pit.xml").exists()
    print(
        f"PIT real: {funcion.puntuacion} %, {funcion.detectados} detectados, {len(funcion.sobrevivientes)} sobrevivientes; solo Criticos.critico; {resultado.duracion_s} s"
    )
    if os.environ.get("QAGENT_GRABAR_PIT") == "1":
        destino = Path(__file__).resolve().parents[1] / "fixtures/pit/critico-real.xml"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(informes[0], encoding="utf-8")
        print("Informe PIT real guardado en tests/fixtures/pit/critico-real.xml")
