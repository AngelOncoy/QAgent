"""Extensión compatible de generated_test.v2 para rutas Java (#184)."""

import json

import pytest

from qagent import contracts


def ejemplo() -> dict:
    """Contrato Java anterior a #184, con nombre sin carpetas, que debe seguir válido."""
    return json.loads(
        (contracts.DIR_CONTRATOS / "ejemplos/generated_test.v2.java.json").read_text(
            encoding="utf-8"
        )
    )


@pytest.mark.parametrize(
    "archivo",
    [
        "PreciosTest.java",
        "src/test/java/PreciosTest.java",
        "src/test/java/org/ejemplo/PreciosTest.java",
    ],
)
def test_java_admite_ruta_nueva_y_nombre_anterior(archivo: str) -> None:
    """La ruta nueva cumple el contrato sin invalidar pruebas Java guardadas."""
    dato = {**ejemplo(), "archivo": archivo}
    contracts.validar(contracts.GENERATED_TEST_V2, dato)


@pytest.mark.parametrize(
    "archivo",
    [
        "../PreciosTest.java",
        "src/test/java/../PreciosTest.java",
        "src/test/java//PreciosTest.java",
        "/src/test/java/PreciosTest.java",
        "C:/PreciosTest.java",
        "src\\test\\java\\PreciosTest.java",
        "carpeta/PreciosTest.java",
        "src/test/java/Precios.py",
        "src/test/java/Precios.java",
    ],
)
def test_java_rechaza_rutas_que_no_corresponden(archivo: str) -> None:
    """No acepta escapes, rutas de otro lenguaje ni carpetas fuera de src/test/java."""
    with pytest.raises(contracts.ContratoInvalido):
        contracts.validar(
            contracts.GENERATED_TEST_V2, {**ejemplo(), "archivo": archivo}
        )


@pytest.mark.parametrize(
    ("lenguaje", "framework"),
    [("python", "pytest"), ("javascript", "vitest"), ("typescript", "jest")],
)
def test_otros_lenguajes_conservan_restriccion_sin_carpetas(
    lenguaje: str, framework: str
) -> None:
    """Ampliar Java no amplía inadvertidamente el contrato de los otros adaptadores."""
    dato = {
        **ejemplo(),
        "lenguaje": lenguaje,
        "framework_pruebas": framework,
        "archivo": "carpeta/test_x.py",
    }
    assert not contracts.es_valido(contracts.GENERATED_TEST_V2, dato)
