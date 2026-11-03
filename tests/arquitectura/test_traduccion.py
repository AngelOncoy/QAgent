from __future__ import annotations

import json
from pathlib import Path

import pytest

from qagent.arquitectura.traduccion import traducir_java, traducir_node, traducir_python

REGLAS = [
    {
        "id": "universal-sin-ciclos",
        "tipo": "ciclos_importacion",
        "nombre": "Sin ciclos",
        "origen": "universal",
        "confirmada": True,
    },
    {
        "id": "capas-001",
        "tipo": "dependencia_prohibida",
        "nombre": "Capas",
        "origen": "usuario",
        "confirmada": True,
        "desde": "dominio",
        "hacia": "interfaz",
    },
]


def test_python_traduce_ciclos_y_capas_a_import_linter(tmp_path: Path) -> None:
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "__init__.py").touch()
    planes = traducir_python(REGLAS, tmp_path)
    assert len(planes) == 2
    assert planes[0].comando[0] == "lint-imports"
    assert "type = acyclic_siblings" in next(iter(planes[0].archivos.values()))
    assert "app.dominio" in next(iter(planes[1].archivos.values()))
    assert all(";" not in argumento for p in planes for argumento in p.comando)


def test_python_sin_paquete_da_error_explicito(tmp_path: Path) -> None:
    (tmp_path / "solo.py").touch()
    with pytest.raises(ValueError, match="__init__"):
        traducir_python(REGLAS, tmp_path)


@pytest.mark.parametrize("lenguaje", ["javascript", "typescript"])
def test_node_traduce_a_json_dependency_cruiser(tmp_path: Path, lenguaje: str) -> None:
    planes = traducir_node(REGLAS, tmp_path, lenguaje)
    configuracion = json.loads(planes[1].archivos["dependency-cruiser-1.json"])
    assert planes[0].comando[0] == "dependency-cruiser"
    assert configuracion["forbidden"][0]["from"]["path"] == r"(^|/)dominio(/|$)"
    assert configuracion["forbidden"][0]["to"]["path"] == r"(^|/)interfaz(/|$)"
    assert configuracion["options"]["skipAnalysisNotInRules"] is True


def test_java_traduce_a_archunit_sin_modificar_pom(tmp_path: Path) -> None:
    fuente = tmp_path / "src/main/java/com/app/dominio/Servicio.java"
    fuente.parent.mkdir(parents=True)
    fuente.write_text("package com.app.dominio; class Servicio {}", encoding="utf-8")
    otra = tmp_path / "src/main/java/com/app/interfaz/Vista.java"
    otra.parent.mkdir(parents=True)
    otra.write_text("package com.app.interfaz; class Vista {}", encoding="utf-8")
    planes = traducir_java(REGLAS, tmp_path)
    assert "SlicesRuleDefinition" in planes[0].archivos["QAgentArchitecture.java"]
    assert "resideInAPackage" in planes[1].archivos["QAgentArchitecture.java"]
    assert not (tmp_path / "pom.xml").exists()
