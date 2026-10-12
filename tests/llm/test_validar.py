"""Validación de claves y modelos con una llamada mínima por agente (sin internet)."""

from __future__ import annotations

from typing import Any

import pytest

from pyagent.llm import validar as modulo
from pyagent.llm.cliente import ErrorLLM
from pyagent.llm.modelos import RespuestaLLM


class ClienteFijo:
    def __init__(self, falla: bool = False) -> None:
        self.falla = falla
        self.prompts: list[str] = []

    def generar(self, prompt: str, rol: str = "generator") -> RespuestaLLM:
        self.prompts.append(prompt)
        if self.falla:
            raise ErrorLLM("El proveedor LLM respondió con HTTP 401.")
        return RespuestaLLM("OK", 7, 1, 0.0, "modelo-x")


def test_todos_responden_devuelve_cero(monkeypatch, capsys) -> None:
    clientes: list[ClienteFijo] = []

    def crear(*_: Any, **__: Any) -> ClienteFijo:
        clientes.append(ClienteFijo())
        return clientes[-1]

    monkeypatch.setattr(modulo, "crear_cliente", crear)

    assert modulo.validar() == 0
    salida = capsys.readouterr().out
    assert salida.count("OK ") == 3
    assert "7+1 tokens" in salida
    assert all(c.prompts == [modulo.PROMPT_PRUEBA] for c in clientes)


def test_un_agente_que_falla_se_informa_y_devuelve_uno(monkeypatch, capsys) -> None:
    respuestas = iter([ClienteFijo(), ClienteFijo(falla=True), ClienteFijo()])
    monkeypatch.setattr(modulo, "crear_cliente", lambda *a, **k: next(respuestas))

    assert modulo.validar() == 1
    salida = capsys.readouterr().out
    assert "FALLA" in salida and "HTTP 401" in salida


def test_lista_solo_los_modelos_gratuitos_de_openrouter() -> None:
    datos = {
        "data": [
            {"id": "b/modelo:free", "context_length": 8000},
            {"id": "a/pago"},
            {"id": "a/otro:free"},
            "basura",
        ]
    }
    assert modulo.modelos_gratis_openrouter(datos) == [
        ("a/otro:free", None),
        ("b/modelo:free", 8000),
    ]
    assert modulo.modelos_gratis_openrouter({"error": "x"}) == []


@pytest.fixture(autouse=True)
def _sin_red(monkeypatch) -> None:
    def prohibido(*_: Any, **__: Any) -> None:
        raise AssertionError("las pruebas no deben salir a internet")

    monkeypatch.setattr(modulo, "urlopen", prohibido)
