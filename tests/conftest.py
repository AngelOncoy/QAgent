"""Configuración común de las pruebas."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def corridas_lanzadas(monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    """Ninguna prueba lanza el pipeline real en un hilo al llamar a `start_run`.

    `start_run` decide el modo y llama a `_lanzar_corrida`; aquí esa llamada solo se
    anota (la lista que devuelve el fixture) y Docker se da por no listo, salvo que la
    prueba lo cambie. El pipeline en sí se prueba en `tests/orchestrator/test_corrida.py`.
    """
    lanzadas: list[tuple] = []
    try:
        from pyagent.app import desktop
    except ImportError:  # sin pywebview instalado no hay puente que parchear
        return lanzadas
    monkeypatch.setattr(
        desktop.DesktopAPI,
        "_lanzar_corrida",
        lambda self, *argumentos: lanzadas.append(argumentos),
    )
    monkeypatch.setattr(desktop.DesktopAPI, "_sandbox_listo", lambda self: False)
    return lanzadas
