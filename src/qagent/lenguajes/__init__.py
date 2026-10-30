"""Adaptadores por lenguaje (EN-17): lo específico de cada lenguaje, separado de los agentes.

``REGISTRO`` trae los cuatro lenguajes de los contratos. Python está completo (delega
en el flujo actual); JavaScript y TypeScript validan sintaxis con tree-sitter (ADR-009);
Java detecta, analiza fuentes y valida sintaxis como prototipo de EN-19.

Ver ``src/qagent/lenguajes/README.md`` y ``docs/decisiones/ADR-007-adaptadores-por-lenguaje.md``.
"""

from __future__ import annotations

import os
from typing import Any

from qagent import contracts
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
from qagent.lenguajes.registro import LenguajeNoSoportado, Registro, listar_archivos
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


def adaptador_del_proyecto(raiz: str | os.PathLike[str]) -> LanguageAdapter:
    """Adaptador con el que se corre el proyecto (ver ``Registro.adaptador_del_proyecto``).

    Sin archivos fuente reconocibles se usa el de los contratos anteriores a EN-17.

    Raises:
        LenguajeNoSoportado: si el lenguaje del proyecto aún no permite corridas.
    """
    return REGISTRO.adaptador_del_proyecto(
        raiz, contracts.LENGUAJE_CONTRATOS_ANTERIORES
    )


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
    "LenguajeNoSoportado",
    "NoImplementado",
    "PythonAdapter",
    "Registro",
    "TypeScriptAdapter",
    "adaptador_de_contrato",
    "adaptador_del_proyecto",
    "adaptador_para",
    "cargar_gramatica",
    "detectar_lenguaje",
    "listar_archivos",
]
