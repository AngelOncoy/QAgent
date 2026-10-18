"""B1: contexto estático del módulo para el Generator (solo `ast`, sin importar)."""

from __future__ import annotations

from pathlib import Path

import pytest

from qagent.agents.generator import GeneratorAgent
from qagent.analysis.contexto import (
    MAX_CARACTERES_CODIGO,
    PAQUETES_BASE,
    contexto_de_funcion,
    paquetes_del_sandbox,
)
from qagent.llm import FakeLLMClient, RespuestaLLM, TokenTracker

MODULO = '''
import logging
from datetime import datetime, timezone

from flask import request, g
from src.config.settings import Config

try:
    import jwt as pyjwt
except ImportError:
    pyjwt = None

ALGORITHM = "HS256"
NO_USADO = 1


def _secret():
    return Config.SECRET_KEY


def decode_token(token, expected_type=None):
    """Decodifica el token. Lanza pyjwt.PyJWTError si es inválido."""
    data = pyjwt.decode(token, _secret(), algorithms=[ALGORITHM])
    local = datetime.now(timezone.utc)
    return data


def sumar(a: int, b: int) -> int:
    """Suma a y b."""
    return a + b
'''


@pytest.fixture
def proyecto(tmp_path: Path) -> Path:
    (tmp_path / "src" / "middleware").mkdir(parents=True)
    (tmp_path / "src" / "middleware" / "jwt_auth.py").write_text(
        MODULO, encoding="utf-8"
    )
    (tmp_path / "requirements.txt").write_text(
        "Flask>=3.1  # web\n# PyJWT>=2.9\n-r otros.txt\n\nrequests==2.32\n",
        encoding="utf-8",
    )
    return tmp_path


def test_junta_imports_globales_usados_codigo_y_paquetes(proyecto) -> None:
    contexto = contexto_de_funcion(
        proyecto, "src/middleware/jwt_auth.py", "decode_token"
    )

    assert "import jwt as pyjwt" in contexto.imports  # dentro del try también cuenta
    assert "from src.config.settings import Config" in contexto.imports
    assert contexto.globales_usados == [
        "ALGORITHM",
        "_secret",
        "datetime",
        "pyjwt",
        "timezone",
    ]
    assert "NO_USADO" not in contexto.globales_usados
    assert contexto.codigo.startswith("def decode_token(token, expected_type=None):")
    assert contexto.paquetes == ["Flask>=3.1", "requests==2.32"]


def test_sin_requirements_no_hay_paquetes_del_proyecto(tmp_path) -> None:
    assert paquetes_del_sandbox(tmp_path) == []


@pytest.mark.parametrize(
    "modulo, nombre",
    [
        ("no_existe.py", "decode_token"),
        ("src/middleware/jwt_auth.py", "no_existe"),
    ],
)
def test_sin_archivo_o_sin_funcion_no_hay_contexto(proyecto, modulo, nombre) -> None:
    assert contexto_de_funcion(proyecto, modulo, nombre) is None


def test_archivo_con_error_de_sintaxis_no_rompe(tmp_path) -> None:
    (tmp_path / "roto.py").write_text("def f(:\n", encoding="utf-8")
    assert contexto_de_funcion(tmp_path, "roto.py", "f") is None


def test_el_codigo_muy_largo_se_recorta(tmp_path) -> None:
    cuerpo = "\n".join(f"    x{i} = {i}" for i in range(2000))
    (tmp_path / "largo.py").write_text(f"def f():\n{cuerpo}\n", encoding="utf-8")

    contexto = contexto_de_funcion(tmp_path, "largo.py", "f")

    assert len(contexto.codigo) <= MAX_CARACTERES_CODIGO + 30
    assert contexto.codigo.endswith("# […recortado…]")


# --- El prompt del Generator ------------------------------------------------------

CONTRATO = {
    "version": "2",
    "modulo": "src/middleware/jwt_auth.py",
    "huella": "a" * 64,
    "tipo": "funcion",
    "objetivo": "decode_token",
    "firma": "(token, expected_type=None)",
    "critical": False,
    "llama_a": [],
    "casos": [
        {
            "id": "token_invalido",
            "entrada": {"token": "x"},
            "excepcion": "PyJWTError",
            "origen": "docstring",
        }
    ],
}


class ClienteEspia:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generar(self, prompt: str, rol: str = "generator") -> RespuestaLLM:
        self.prompts.append(prompt)
        return RespuestaLLM(
            contenido="def test_token_invalido():\n    assert True\n",
            tokens_entrada=1,
            tokens_salida=1,
            costo_usd=0.0,
            modelo="espia",
        )


def test_con_la_carpeta_del_proyecto_el_prompt_lleva_el_contexto(proyecto) -> None:
    cliente = ClienteEspia()
    GeneratorAgent(cliente, TokenTracker(), ruta_proyecto=proyecto).generar(
        CONTRATO, 1, None
    )

    [prompt] = cliente.prompts
    assert "CONTEXTO DEL MÓDULO" in prompt
    assert "import jwt as pyjwt" in prompt
    assert "ALGORITHM, _secret, datetime, pyjwt, timezone" in prompt
    assert all(paquete in prompt for paquete in PAQUETES_BASE)
    assert 'unittest.mock.patch("src.middleware.jwt_auth.<nombre>")' in prompt
    # El oráculo no cambia: se recuerda que el valor esperado sale del contrato.
    assert "sale SIEMPRE del contrato" in prompt
    # El contrato sigue al final, en una línea (lo lee la IA simulada).
    assert prompt.splitlines()[-1].startswith("CONTRATO_JSON: ")


def test_sin_la_carpeta_del_proyecto_el_prompt_queda_como_antes() -> None:
    cliente = ClienteEspia()
    GeneratorAgent(cliente, TokenTracker()).generar(CONTRATO, 1, None)

    assert "CONTEXTO DEL MÓDULO" not in cliente.prompts[0]


def test_la_ia_simulada_sigue_leyendo_el_contrato_con_contexto(proyecto) -> None:
    contrato = {
        **CONTRATO,
        "objetivo": "sumar",
        "firma": "(a: int, b: int) -> int",
        "casos": [
            {
                "id": "suma",
                "entrada": {"a": 2, "b": 3},
                "valor_esperado": 5,
                "origen": "docstring",
            }
        ],
    }
    generado = GeneratorAgent(
        FakeLLMClient(), TokenTracker(), es_simulado=True, ruta_proyecto=proyecto
    ).generar(contrato, 1, None)

    assert "def test_suma" in generado["codigo"]
    assert "== 5" in generado["codigo"]
