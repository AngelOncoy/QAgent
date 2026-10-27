"""Adaptador de Python (EN-17): delega en los módulos que ya usa QAgent.

No reimplementa nada: el análisis es ``qagent.analysis.analizar_proyecto`` (solo
``ast``, ADR-002), el comando es ``qagent.sandbox.ejecucion.comando_pytest``, el
informe se lee con ``parsear_junit`` y el laundering con ``comparar_aserciones``.
Así el flujo actual de Python y este adaptador dan siempre el mismo resultado.
"""

from __future__ import annotations

import ast
import os
from typing import Any

from qagent.analysis import analizar_proyecto, comparar_aserciones
from qagent.analysis.contexto import PAQUETES_BASE
from qagent.lenguajes.base import (
    ComparacionAserciones,
    EntornoSandbox,
    Estructura,
    LanguageAdapter,
)
from qagent.sandbox.ejecucion import (
    ARCHIVO_JUNIT,
    DIR_SALIDA,
    DIR_TESTS,
    comando_pytest,
)
from qagent.sandbox.informe_pytest import parsear_junit
from qagent.sandbox.modelos import IMAGEN_BASE


class PythonAdapter(LanguageAdapter):
    """Python 3.10+ con pytest; endpoints FastAPI con TestClient."""

    lenguaje = "python"
    extensiones = (".py",)
    marcadores = ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")
    frameworks_pruebas = ("pytest",)
    frameworks_app = ("fastapi",)

    def analizar(self, raiz: str | os.PathLike[str]) -> Estructura:
        """``analizar_proyecto(raiz)`` con ``lenguaje: "python"``."""
        return {"lenguaje": self.lenguaje, **analizar_proyecto(raiz)}

    def comando_pruebas(self, modulo: str, framework: str | None = None) -> list[str]:
        """``comando_pytest(modulo)``: pytest con cobertura de ramas y junit.xml."""
        self.elegir_framework(framework)
        return comando_pytest(modulo)

    def entorno_sandbox(self) -> EntornoSandbox:
        return EntornoSandbox(
            imagen=IMAGEN_BASE,
            paquetes_base=PAQUETES_BASE,
            dir_tests=DIR_TESTS,
            dir_salida=DIR_SALIDA,
            informe=ARCHIVO_JUNIT,
        )

    def interpretar_resultados(self, informe: str) -> dict[str, Any]:
        """Lee el ``junit.xml`` de pytest.

        Raises:
            qagent.sandbox.informe_pytest.JUnitInvalido: si el XML no se puede leer.
        """
        return parsear_junit(informe).a_dict()

    def validar_sintaxis(self, codigo: str) -> list[str]:
        """Parsea con ``ast`` (no ejecuta) y devuelve el error con su línea."""
        try:
            ast.parse(codigo)
        except SyntaxError as error:
            return [f"línea {error.lineno}: {error.msg}"]
        except ValueError as error:  # p. ej. bytes nulos en el código
            return [str(error)]
        return []

    def comparar_aserciones(
        self, original: str, reparado: str
    ) -> ComparacionAserciones:
        return comparar_aserciones(original, reparado)
