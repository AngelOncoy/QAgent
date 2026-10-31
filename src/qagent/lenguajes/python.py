"""Adaptador de Python (EN-17): delega en los módulos que ya usa QAgent.

No reimplementa nada: el análisis es ``qagent.analysis.analizar_proyecto``
(tree-sitter con la gramática de Python, ADR-009 y TA-16), el comando es ``qagent.sandbox.ejecucion.comando_pytest``, el
informe se lee con ``parsear_junit``, la cobertura con ``leer_coverage``, la
mutación usa ``qagent.sandbox.mutacion.comando_mutacion`` y el laundering
``comparar_aserciones``.
Así el flujo actual de Python y este adaptador dan siempre el mismo resultado.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any

from qagent.analysis import analizar_proyecto, comparar_aserciones
from qagent.analysis.contexto import PAQUETES_BASE
from qagent.lenguajes import python_generacion, python_regresion
from qagent.lenguajes.base import (
    ComandoSandbox,
    ComparacionAserciones,
    EntornoSandbox,
    Estructura,
    LanguageAdapter,
)
from qagent.lenguajes.python_planificacion import (
    REGLAS_PLANIFICACION_PYTHON,
    ReglasPlanificacionPython,
)
from qagent.lenguajes.python_revision import (
    REGLAS_REVISION_PYTHON,
    ReglasRevisionPython,
)
from qagent.sandbox.ejecucion import (
    ARCHIVO_JUNIT,
    ARCHIVO_TEST_GENERADO,
    DIR_SALIDA,
    DIR_TESTS,
    comando_pytest,
    leer_coverage,
)
from qagent.sandbox.informe_pytest import parsear_junit
from qagent.sandbox.modelos import IMAGEN_BASE
from qagent.sandbox.mutacion import (
    ResultadoMutacion,
    comando_mutacion,
    ejecutar_mutacion,
)


class PythonAdapter(LanguageAdapter):
    """Python 3.10+ con pytest; endpoints FastAPI con TestClient."""

    lenguaje = "python"
    extensiones = (".py",)
    marcadores = ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")
    frameworks_pruebas = ("pytest",)
    frameworks_app = ("fastapi",)
    motor_mutacion = "mutmut"
    comprobar_librerias_sistema = True

    def analizar(self, raiz: str | os.PathLike[str]) -> Estructura:
        """``analizar_proyecto(raiz)`` (tree-sitter) con ``lenguaje: "python"``."""
        return {"lenguaje": self.lenguaje, **analizar_proyecto(raiz)}

    def comando_pruebas(self, modulo: str, framework: str | None = None) -> list[str]:
        """``comando_pytest(modulo)``: pytest con cobertura de ramas y junit.xml."""
        self.elegir_framework(framework)
        return comando_pytest(modulo)

    def modulo_cobertura(self, modulo: str) -> str:
        """``pkg/mod.py`` -> ``pkg.mod``: lo que mide ``--cov`` (como siempre)."""
        return Path(modulo).with_suffix("").as_posix().replace("/", ".")

    def variables_pruebas(self) -> dict[str, str]:
        """El ``.coverage`` de pytest-cov va a ``/out`` (el resto es de solo lectura)."""
        return {"COVERAGE_FILE": f"{DIR_SALIDA}/.coverage"}

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
        """Parsea con ``ast`` (no ejecuta) y devuelve el error con su línea.

        Revisa las pruebas que genera QAgent, no el código del usuario: sigue con
        ``ast`` para dar los mismos mensajes que CPython (TA-16).
        """
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

    def leer_cobertura(
        self, dir_salida: str | os.PathLike[str]
    ) -> dict[str, Any] | None:
        """El ``coverage.json`` que deja pytest-cov (ya está en el formato común)."""
        return leer_coverage(Path(dir_salida) / "coverage.json")

    def archivo_de_prueba(self, objetivo: str) -> str:
        """Siempre ``test_generado.py``: cada test corre en su propia carpeta temporal."""
        return ARCHIVO_TEST_GENERADO

    def huellas_de_archivo(self, fuente: str, relativa: str) -> dict[str, str] | None:
        """Huella tree-sitter de cada función pública y ruta FastAPI (HU-24, HU-25)."""
        return python_regresion.huellas_de_archivo(fuente, relativa)

    def funciones_de_modulo(self, raiz: Path, modulo: str) -> list[dict[str, Any]]:
        """Línea del `def` de cada función de primer nivel (mutación de reg_deep)."""
        return python_regresion.funciones_de_modulo(raiz, modulo)

    def ejecutar_mutacion(self, *args: Any, **opciones: Any) -> ResultadoMutacion:
        """mutmut en el sandbox, solo sobre las funciones críticas (EN-09, #74)."""
        return ejecutar_mutacion(*args, **opciones)

    def reglas_planificacion(self) -> ReglasPlanificacionPython:
        """Prompts y filtros de casos de pytest y FastAPI para el Planner (#168)."""
        return REGLAS_PLANIFICACION_PYTHON

    def prompt_generator(
        self,
        contrato: dict[str, Any],
        intento: int,
        feedback: str | None,
        ruta_proyecto: Path | None,
    ) -> str:
        """Prompt del test pytest (o TestClient) de ``contrato`` (#168)."""
        return python_generacion.prompt_generator(
            contrato, intento, feedback, ruta_proyecto
        )

    def reglas_revision(self) -> ReglasRevisionPython:
        """Sintaxis, oráculo y salida de pytest para el Reviewer (#168)."""
        return REGLAS_REVISION_PYTHON

    def comando_mutacion(self, modulo: str, funciones: list[str]) -> ComandoSandbox:
        """mutmut sobre las funciones críticas, con el script del sandbox (EN-09)."""
        comando, entorno = comando_mutacion(modulo, funciones)
        return ComandoSandbox(comando, entorno)
