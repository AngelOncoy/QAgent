"""Adaptadores por lenguaje (EN-17): lo específico de cada lenguaje, separado de los agentes.

``REGISTRO`` trae los cuatro lenguajes de los contratos. Python está completo (delega
en el flujo actual); JavaScript y TypeScript validan sintaxis con tree-sitter (ADR-009);
Java solo detecta por ahora.

Ver ``src/qagent/lenguajes/README.md`` y ``docs/decisiones/ADR-007-adaptadores-por-lenguaje.md``.
"""

from __future__ import annotations

import os
from typing import Any

from qagent.lenguajes.base import (
    AdaptadorEnDesarrollo,
    ComandoSandbox,
    ComparacionAserciones,
    Deteccion,
    EntornoSandbox,
    LanguageAdapter,
    NoImplementado,
)
from qagent.lenguajes.java import JavaAdapter
from qagent.lenguajes.javascript import JavaScriptAdapter, TypeScriptAdapter
from qagent.lenguajes.python import PythonAdapter
from qagent.lenguajes.registro import Registro, listar_archivos
from qagent.lenguajes.treesitter import cargar_gramatica

#: Registro predeterminado con todos los lenguajes de los contratos.
REGISTRO = Registro(
    [PythonAdapter(), JavaScriptAdapter(), TypeScriptAdapter(), JavaAdapter()]
)


def adaptador_para(lenguaje: str) -> LanguageAdapter:
    """Adaptador de un lenguaje del registro predeterminado (KeyError si no hay)."""
    return REGISTRO.adaptador_para(lenguaje)


def adaptador_de_contrato(contrato: dict[str, Any]) -> LanguageAdapter:
    """Adaptador del lenguaje de un ``planner_contract`` v2 o v3."""
    return REGISTRO.adaptador_de_contrato(contrato)


def detectar_lenguaje(raiz: str | os.PathLike[str]) -> list[Deteccion]:
    """Lenguajes del proyecto en ``raiz``, del más al menos probable."""
    return REGISTRO.detectar(raiz)


__all__ = [
    "REGISTRO",
    "AdaptadorEnDesarrollo",
    "ComandoSandbox",
    "ComparacionAserciones",
    "Deteccion",
    "EntornoSandbox",
    "JavaAdapter",
    "JavaScriptAdapter",
    "LanguageAdapter",
    "NoImplementado",
    "PythonAdapter",
    "Registro",
    "TypeScriptAdapter",
    "adaptador_de_contrato",
    "adaptador_para",
    "cargar_gramatica",
    "detectar_lenguaje",
    "listar_archivos",
]
