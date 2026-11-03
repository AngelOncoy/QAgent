"""Rutas de tests temporales, incluida la disposición Java, sin ejecutar código (#184)."""

from pathlib import Path

import pytest

from qagent.sandbox.archivos_prueba import ruta_de_prueba


@pytest.mark.parametrize(
    "archivo",
    ["test_generado.py", "precios.test.ts", "src/test/java/ejemplo/BancoTest.java"],
)
def test_ruta_segura_conserva_destino_sin_crear_archivos(
    tmp_path: Path, archivo: str
) -> None:
    """Python y JS mantienen nombres simples; Java admite carpetas dentro del temporal."""
    destino = ruta_de_prueba(tmp_path, archivo)
    assert destino == tmp_path / archivo
    assert not destino.exists()


@pytest.mark.parametrize(
    "archivo",
    [
        "../escape.java",
        "/tmp/Test.java",
        "C:/Test.java",
        "a/../Test.java",
        "a/./Test.java",
        "a//Test.java",
        "a\\Test.java",
        "a/Test.java:flujo",
        "a/Test.java\x00",
        "CON.java",
        "a/aux/Test.java",
        "a/LPT1.log",
        "a./Test.java",
        "",
        "a" * 513,
    ],
)
def test_ruta_externa_ambigua_o_reservada_se_rechaza(
    tmp_path: Path, archivo: str
) -> None:
    """Ningún nombre recibido puede escapar ni usar dispositivos del anfitrión."""
    with pytest.raises(ValueError):
        ruta_de_prueba(tmp_path, archivo)
