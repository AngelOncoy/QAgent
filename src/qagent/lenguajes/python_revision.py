"""Reglas de revisión de los tests de Python (pytest) para el Reviewer (#168).

Es el código que antes vivía en ``agents/reviewer.py``, movido sin cambios de
comportamiento: el Reviewer es compartido y pide estas reglas al adaptador.

- Sintaxis del test generado (``ast.parse``: revisa las pruebas de QAgent, no el
  código del usuario).
- Oráculo: el test compara el resultado con los valores esperados del contrato y no
  usa construcciones que silencian fallos (try/except, skip, xfail).
- Clasificación de la salida de pytest: error del entorno, respuesta inválida de
  FastAPI, error del test o fallo de una aserción.
- Rango de líneas de la función probada, para medir su cobertura.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from qagent import contracts
from qagent.lenguajes.base import Clasificacion

_NO_LITERAL = object()

_PATRONES_ERROR_TEST = (
    "syntaxerror",
    "indentationerror",
    "importerror",
    "modulenotfounderror",
    "failed to import test module",
    "error at setup",
    "fixturelookuperror",
    "invalidspecerror",
    "name 'pytest' is not defined",
    "name 'mock' is not defined",
    "does not have the attribute",
    # pytest sale con código 5: el archivo no tiene funciones test_ que recolectar.
    "no tests ran",
    "collected 0 items",
)


# Fallos del entorno, no del test ni del código: reintentar no los arregla (EN-16).
_PATRONES_ENTORNO = (
    "connectionrefusederror",
    "connection refused",
    "operationalerror",
    "could not connect to server",
)
# FastAPI valida la respuesta contra el response_model: si no la cumple, TestClient
# lanza esta excepción en vez de devolver un 500. Es un bug de la API (EN-16).
_PATRON_RESPUESTA_INVALIDA = "responsevalidationerror"
_MODULO_FALTANTE = re.compile(r"No module named '([A-Za-z0-9_.]+)'")
#: El cargador dinámico no encontró una librería del sistema (issue 142).
_LIBRERIA_SISTEMA_FALTANTE = re.compile(
    r"(lib[A-Za-z0-9_.+\-]*?\.so(?:\.[0-9]+)*): cannot open shared object file"
)


class ReglasRevisionPython:
    """Reglas del Reviewer para tests pytest (ver ``ReglasRevision`` en ``base``)."""

    # --- Sintaxis -----------------------------------------------------------------

    @staticmethod
    def error_de_sintaxis(codigo: str) -> str | None:
        """``SyntaxError: ...`` si el test no se puede parsear; None si es válido."""
        try:
            ast.parse(codigo)
        except (SyntaxError, ValueError) as error:
            return f"{type(error).__name__}: {error}"
        return None

    # --- Oráculo --------------------------------------------------------------------

    @classmethod
    def validar_oraculo(
        cls,
        contrato: dict[str, Any],
        codigo: str,
    ) -> str | None:
        """Comprueba que el test use los valores esperados del Planner."""
        arbol = ast.parse(codigo)

        evasion = cls._detectar_evasion(arbol)
        if evasion is not None:
            return f"Oráculo inválido: {evasion}"

        valores_disponibles = cls.valores_de_aserciones(
            arbol,
            None if contrato.get("tipo") == "endpoint" else contrato["objetivo"],
        )
        excepciones_disponibles = cls._excepciones_esperadas(arbol)
        cantidad_aserciones = sum(
            isinstance(nodo, (ast.Assert, ast.With)) for nodo in ast.walk(arbol)
        )
        if cantidad_aserciones == 0:
            return "Oráculo inválido: el test no contiene aserciones."

        if contrato.get("tipo") == "endpoint":
            return cls._validar_oraculo_endpoint(contrato, valores_disponibles)

        for caso in contrato["casos"]:
            if "valor_esperado" in caso:
                esperado = contracts.valor_esperado_python(caso)
                posicion = cls._buscar_valor(valores_disponibles, esperado)
                if posicion is None:
                    return (
                        f"Oráculo inválido: el caso '{caso['id']}' no comprueba "
                        f"el valor esperado {esperado!r}."
                    )
                valores_disponibles.pop(posicion)
                continue

            excepcion = caso.get("excepcion")
            posicion = cls._buscar_excepcion(excepciones_disponibles, excepcion)
            if posicion is None:
                return (
                    f"Oráculo inválido: el caso '{caso['id']}' no comprueba "
                    f"la excepción {excepcion}."
                )
            excepciones_disponibles.pop(posicion)

        return None

    @classmethod
    def _validar_oraculo_endpoint(
        cls, contrato: dict[str, Any], valores: list[Any]
    ) -> str | None:
        """Cada caso de endpoint debe comprobar su status_code y su cuerpo esperado.

        El cuerpo completo (`json`) debe aparecer como literal; de `json_contiene`
        basta un dict literal que incluya esos campos o cada valor por separado.
        """
        for caso in contrato["casos"]:
            esperado = caso["valor_esperado"]
            estado = esperado["status_code"]
            posicion = cls._buscar_valor(valores, estado)
            if posicion is None:
                return (
                    f"Oráculo inválido: el caso '{caso['id']}' no comprueba "
                    f"el status_code {estado}."
                )
            valores.pop(posicion)
            if "json" in esperado:
                posicion = cls._buscar_valor(valores, esperado["json"])
                if posicion is None:
                    return (
                        f"Oráculo inválido: el caso '{caso['id']}' no comprueba "
                        f"el cuerpo esperado {esperado['json']!r}."
                    )
                valores.pop(posicion)
            parcial = esperado.get("json_contiene")
            if parcial:
                problema = cls._consumir_json_contiene(valores, parcial)
                if problema is not None:
                    return f"Oráculo inválido: el caso '{caso['id']}' {problema}."
        return None

    @classmethod
    def _consumir_json_contiene(
        cls, valores: list[Any], parcial: dict[str, Any]
    ) -> str | None:
        for posicion, valor in enumerate(valores):
            if isinstance(valor, dict) and all(
                k in valor and valor[k] == v for k, v in parcial.items()
            ):
                valores.pop(posicion)
                return None
        for clave, esperado in parcial.items():
            posicion = cls._buscar_valor(valores, esperado)
            if posicion is None:
                return f"no comprueba el campo {clave!r} == {esperado!r}"
            valores.pop(posicion)
        return None

    @staticmethod
    def valores_de_aserciones(arbol: ast.AST, objetivo: str | None = None) -> list[Any]:
        """Extrae valores comparados exactamente con el resultado del objetivo.

        Para endpoints conserva el recorrido histórico de todos los comparadores. En
        funciones exige una igualdad cuyo sujeto sea la llamada al objetivo o una
        variable asignada desde ella; no confunde longitud, índices ni literales de
        aserciones ajenas con el oráculo del caso.
        """
        valores: list[Any] = []
        variables_resultado: set[str] = set()
        if objetivo is not None:
            for nodo in ast.walk(arbol):
                if isinstance(nodo, (ast.Assign, ast.AnnAssign)):
                    valor = nodo.value
                    if not ReglasRevisionPython.es_resultado_objetivo(
                        valor, objetivo, variables_resultado
                    ):
                        continue
                    destinos = (
                        nodo.targets if isinstance(nodo, ast.Assign) else [nodo.target]
                    )
                    variables_resultado.update(
                        destino.id
                        for destino in destinos
                        if isinstance(destino, ast.Name)
                    )
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Assert):
                continue
            prueba = nodo.test
            if not isinstance(prueba, ast.Compare):
                continue
            if objetivo is not None:
                if (
                    len(prueba.ops) != 1
                    or not isinstance(prueba.ops[0], (ast.Eq, ast.Is))
                    or len(prueba.comparators) != 1
                ):
                    continue
                derecha = prueba.comparators[0]
                if ReglasRevisionPython.es_resultado_objetivo(
                    prueba.left, objetivo, variables_resultado
                ):
                    candidatos = [derecha]
                elif ReglasRevisionPython.es_resultado_objetivo(
                    derecha, objetivo, variables_resultado
                ):
                    candidatos = [prueba.left]
                else:
                    continue
            else:
                candidatos = prueba.comparators
            for comparador in candidatos:
                valor = ReglasRevisionPython.valor_literal(comparador)
                if valor is not _NO_LITERAL:
                    valores.append(valor)
        return valores

    @staticmethod
    def es_resultado_objetivo(
        nodo: ast.AST | None, objetivo: str, variables: set[str]
    ) -> bool:
        """Si el nodo representa el resultado completo de la función objetivo."""
        if isinstance(nodo, ast.Name):
            return nodo.id in variables
        if not isinstance(nodo, ast.Call):
            return False
        funcion = nodo.func
        if isinstance(funcion, ast.Name):
            return funcion.id == objetivo
        return isinstance(funcion, ast.Attribute) and funcion.attr == objetivo

    @staticmethod
    def valor_literal(nodo: ast.AST) -> Any:
        """Obtiene un literal o el valor pasado a pytest.approx."""
        candidato = nodo
        if (
            isinstance(nodo, ast.Call)
            and isinstance(nodo.func, ast.Attribute)
            and nodo.func.attr == "approx"
            and nodo.args
        ):
            candidato = nodo.args[0]
        try:
            return ast.literal_eval(candidato)
        except (ValueError, TypeError):
            return _NO_LITERAL

    @staticmethod
    def _excepciones_esperadas(arbol: ast.AST) -> list[str]:
        """Extrae las excepciones utilizadas en pytest.raises."""
        excepciones: list[str] = []
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.With):
                continue
            for elemento in nodo.items:
                contexto = elemento.context_expr
                if (
                    isinstance(contexto, ast.Call)
                    and isinstance(contexto.func, ast.Attribute)
                    and contexto.func.attr == "raises"
                    and contexto.args
                ):
                    excepciones.append(ast.unparse(contexto.args[0]).strip())
        return excepciones

    @staticmethod
    def _buscar_valor(valores: list[Any], esperado: Any) -> int | None:
        for posicion, valor in enumerate(valores):
            if valor == esperado:
                return posicion
        return None

    @staticmethod
    def _buscar_excepcion(
        excepciones: list[str],
        esperada: str | None,
    ) -> int | None:
        if esperada is None:
            return None
        for posicion, encontrada in enumerate(excepciones):
            if encontrada == esperada or encontrada.endswith(f".{esperada}"):
                return posicion
        return None

    @staticmethod
    def _detectar_evasion(arbol: ast.AST) -> str | None:
        """Detecta construcciones que permiten evitar o silenciar el test."""
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Try) and nodo.handlers:
                return "el test contiene try/except que puede ocultar un fallo"

            if isinstance(nodo, ast.Call):
                funcion = nodo.func
                nombre = ""
                if isinstance(funcion, ast.Attribute):
                    nombre = funcion.attr
                elif isinstance(funcion, ast.Name):
                    nombre = funcion.id
                if nombre in {"skip", "xfail"}:
                    return f"el test utiliza {nombre}"

            if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorador in nodo.decorator_list:
                    texto = ast.unparse(decorador)
                    if "skip" in texto or "xfail" in texto:
                        return f"el test utiliza el decorador {texto}"

        return None

    # --- Salida de pytest -------------------------------------------------------

    @classmethod
    def clasificar_salida(
        cls, salida: str, contrato: dict[str, Any], raiz: Path
    ) -> Clasificacion | None:
        """Qué dice la salida de pytest, en el orden en que lo revisa el Reviewer.

        Primero un error del entorno, después una respuesta que no cumple el
        response_model (solo endpoints), un error del propio test y, por último, el
        fallo claro de una aserción. None si no se reconoce ninguno.
        """
        entorno = cls._error_de_entorno(salida, raiz)
        if entorno is not None:
            return Clasificacion("entorno", entorno)
        if (
            contrato.get("tipo") == "endpoint"
            and _PATRON_RESPUESTA_INVALIDA in salida.lower()
        ):
            return Clasificacion(
                "bug_respuesta",
                "La respuesta del endpoint no cumple su response_model "
                f"(ResponseValidationError).\n{salida}",
            )
        if cls._es_error_del_test(salida):
            return Clasificacion("error_test", salida)
        if cls._es_fallo_asercion(salida):
            return Clasificacion("fallo_asercion", salida)
        return None

    @classmethod
    def _error_de_entorno(cls, salida: str, raiz: Path) -> str | None:
        """Describe un fallo del entorno (servicio caído, dependencia sin instalar).

        Un módulo faltante solo cuenta como entorno si el proyecto lo declara como
        dependencia; si no, es un import inventado por el test y se reintenta.
        """
        texto = salida.lower()
        for patron in _PATRONES_ENTORNO:
            if patron in texto:
                return f"el servicio externo no respondió ({patron})"
        # Issue 142: una librería del sistema que no se pudo cargar es del entorno, no
        # del test. Reintentar no la instala y empuja al Generator a simular la dependencia.
        if libreria := _LIBRERIA_SISTEMA_FALTANTE.search(salida):
            return (
                f"falta la librería del sistema '{libreria.group(1)}' en el entorno "
                "aislado (la necesita una dependencia del proyecto)"
            )
        for nombre in _MODULO_FALTANTE.findall(salida):
            raiz_modulo = nombre.split(".")[0]
            if raiz_modulo in cls._dependencias_declaradas(raiz):
                return f"la dependencia '{raiz_modulo}' no está instalada en el sandbox"
        return None

    @staticmethod
    def _dependencias_declaradas(raiz: Path) -> set[str]:
        """Nombres de paquete de requirements*.txt y pyproject.toml (en minúsculas)."""
        nombres: set[str] = set()
        archivos = [
            *raiz.glob("requirements*.txt"),
            raiz / "pyproject.toml",
        ]
        for archivo in archivos:
            try:
                texto = archivo.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for linea in texto.splitlines():
                coincidencia = re.match(r"\s*[\"']?([A-Za-z0-9_.-]+)", linea)
                if coincidencia and not linea.lstrip().startswith(("#", "[", "-")):
                    nombre = coincidencia.group(1).lower().replace("-", "_")
                    nombres.add(nombre)
        return nombres

    @staticmethod
    def _es_error_del_test(salida: str) -> bool:
        texto = salida.lower()
        if any(patron in texto for patron in _PATRONES_ERROR_TEST):
            return True
        return "fixture" in texto and "not found" in texto

    @staticmethod
    def _es_fallo_asercion(salida: str) -> bool:
        """Reconoce un fallo claro de una aserción pytest."""
        texto = salida.lower()
        return (
            "assertionerror" in texto or "\nassert " in texto or " - assert " in texto
        )

    # --- Cobertura ------------------------------------------------------------------

    @staticmethod
    def rango_de_objetivo(
        raiz: Path, modulo: str, nombre: str
    ) -> tuple[int, int] | None:
        """Primera y última línea del cuerpo de una función de nivel superior."""
        try:
            fuente = (raiz / modulo).read_text(encoding="utf-8")
            arbol = ast.parse(fuente)
        except (OSError, SyntaxError, ValueError):
            return None
        for nodo in arbol.body:
            if (
                isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef))
                and nodo.name == nombre
                and nodo.body
            ):
                return nodo.body[0].lineno, nodo.end_lineno or nodo.body[-1].lineno
        return None


#: Instancia única: las reglas no guardan estado.
REGLAS_REVISION_PYTHON = ReglasRevisionPython()
