"""HU-13: evidencias de aislamiento con Docker real.

Se omiten si Docker no está disponible (marcador `docker`). Ejecutar solo estas con:
    pytest -m docker tests/sandbox/test_hu13_aislamiento.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pyagent.sandbox import (
    LimitesSandbox,
    clasificar_resultado,
    ejecutar_en_sandbox,
    ejecutar_pruebas,
)

pytestmark = pytest.mark.docker

CLAVES_DE_IA = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "XIAOMI_API_KEY",
    "OPENROUTER_API_KEY",
)


@pytest.fixture
def proyecto(tmp_path: Path) -> Path:
    """Proyecto mínimo con un `.env` que nunca debe llegar al contenedor."""
    raiz = tmp_path / "proyecto"
    raiz.mkdir()
    (raiz / "calc.py").write_text("def doble(x):\n    return 2 * x\n", encoding="utf-8")
    (raiz / ".env").write_text("OPENAI_API_KEY=sk-del-env\n", encoding="utf-8")
    return raiz


def _tests(tmp_path: Path, codigo: str) -> Path:
    """Crea una carpeta de tests con un único archivo."""
    carpeta = tmp_path / "tests"
    carpeta.mkdir()
    (carpeta / "test_generado.py").write_text(codigo, encoding="utf-8")
    return carpeta


def test_rn02_una_prueba_que_abre_una_conexion_de_red_falla(
    imagen_base, proyecto, tmp_path
):
    tests = _tests(
        tmp_path,
        "import socket\n\n"
        "def test_conectar():\n"
        "    socket.create_connection(('example.com', 80), timeout=5)\n",
    )

    resultado = ejecutar_pruebas(imagen_base, proyecto, tests, "calc")

    assert clasificar_resultado(resultado) == "fallo"
    # Sin red ni DNS: la resolución de example.com falla (socket.gaierror es un OSError).
    assert "gaierror" in resultado.stdout or "OSError" in resultado.stdout


def test_ninguna_clave_de_ia_llega_al_contenedor(
    imagen_base, proyecto, tmp_path, monkeypatch
):
    for clave in CLAVES_DE_IA:
        monkeypatch.setenv(clave, "clave-del-host")
    tests = _tests(tmp_path, "def test_x():\n    assert True\n")

    resultado = ejecutar_en_sandbox(
        imagen_base, ["sh", "-c", "env; ls -a /work/proyecto"], proyecto, tests
    )

    assert resultado.exit_code == 0
    for clave in CLAVES_DE_IA:
        assert clave not in resultado.stdout
    assert "clave-del-host" not in resultado.stdout
    assert ".env" not in resultado.stdout.split()
    assert "sk-del-env" not in resultado.stdout


def test_timeout_mata_el_contenedor_y_lo_elimina(
    imagen_base, proyecto, tmp_path, cliente_docker
):
    tests = _tests(tmp_path, "import time\n\ndef test_lento():\n    time.sleep(60)\n")

    resultado = ejecutar_pruebas(
        imagen_base, proyecto, tests, "calc", LimitesSandbox(timeout_s=3)
    )

    assert resultado.timed_out is True
    assert clasificar_resultado(resultado) == "timeout"
    assert resultado.duracion_s < 30
    restantes = cliente_docker.containers.list(
        all=True, filters={"label": "pyagent=sandbox"}
    )
    assert restantes == []
