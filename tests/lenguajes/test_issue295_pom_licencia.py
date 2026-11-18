"""El POM derivado conserva avisos del original y los controles Maven (#295)."""

import xml.etree.ElementTree as ET

import pytest

from qagent.lenguajes.java_ejecucion import POM, _serializar_pom, preparar_java
from tests.lenguajes.test_java_ejecucion import crear_proyecto


@pytest.mark.parametrize(
    "declaracion", ["", '<?xml version="1.0" encoding="UTF-8"?>\n']
)
def test_pom_auxiliar_conserva_cabecera_y_plugin(tmp_path, declaracion):
    copia, pruebas = crear_proyecto(tmp_path)
    pom = copia / "pom.xml"
    aviso = "<!-- Licencia del proyecto de ejemplo. -->\n<!-- Segundo aviso. -->\n"
    contenido = pom.read_text(encoding="utf-8").replace(
        "<plugins>",
        "<plugins><plugin><groupId>org.apache.rat</groupId><artifactId>apache-rat-plugin</artifactId><version>0.18</version></plugin>",
    )
    original = declaracion + aviso + contenido
    pom.write_text(original, encoding="utf-8")
    preparar_java(copia, pruebas)
    generado = (copia / POM).read_text(encoding="utf-8")
    assert aviso in generado
    assert pom.read_text(encoding="utf-8") == original
    assert "apache-rat-plugin" in generado
    assert "rat.skip" not in generado
    assert ET.fromstring(generado).tag.endswith("project")
    # La segunda serialización del espejo reactor conserva la misma cabecera.
    assert aviso in _serializar_pom(ET.fromstring(generado), generado).decode()
