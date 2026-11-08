"""Simula JavaScript y TypeScript como lenguajes en desarrollo (EP-11).

JS/TS ya corren completos, pero el mecanismo de un lenguaje en desarrollo (aviso
claro, apertura solo para E2E, tipos «próximamente») sigue existiendo para el
próximo lenguaje. Estas pruebas lo cubren devolviendo JS/TS a ese estado.
"""

from __future__ import annotations

import pytest

from qagent.lenguajes import JavaScriptAdapter, TypeScriptAdapter

TIPOS_NODE = ("funcion", "mutacion", "componente")


def simular_node_en_desarrollo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deja JavaScript y TypeScript como antes de EP-11: sin corridas."""
    for clase in (JavaScriptAdapter, TypeScriptAdapter):
        monkeypatch.setattr(clase, "completo", False)
        monkeypatch.setattr(clase, "tipos_prueba", ())
        monkeypatch.setattr(clase, "tipos_prueba_previstos", TIPOS_NODE)
