"""Agente Reviewer/Executor: ejecuta y clasifica los tests generados."""

from __future__ import annotations

import ast
import json
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pyagent import contracts
from pyagent.analysis import comparar_aserciones
from pyagent.llm import ClienteLLM, TokenTracker
from pyagent.sandbox import ResultadoSandbox, clasificar_resultado, ejecutar_pruebas
from pyagent.sandbox.normalizacion import hash_error

Ejecutor = Callable[[str, Path, Path, str], ResultadoSandbox]

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


class ReviewerAgent:
    """Ejecuta un test en Docker y emite un review_result."""

    def __init__(
        self,
        tracker: TokenTracker,
        ruta_proyecto: str | Path,
        imagen: str,
        *,
        cliente: ClienteLLM | None = None,
        modulo_cov: str | None = None,
        ejecutor: Ejecutor = ejecutar_pruebas,
        es_simulado: bool = False,
    ) -> None:
        """Inicializa el Reviewer con el sandbox y cliente opcional."""
        self.tracker = tracker
        self.ruta_proyecto = Path(ruta_proyecto)
        self.imagen = imagen
        self.cliente = cliente
        self.modulo_cov = modulo_cov
        self.ejecutor = ejecutor
        self.es_simulado = es_simulado
        # Último test NO debilitado de cada objetivo: la referencia contra la que se
        # busca laundering. Si se comparara solo con el intento anterior, un intento
        # rechazado por laundering pasaría a ser la referencia del siguiente.
        self._referencias: dict[tuple[str, str], str] = {}

    def revisar(
        self,
        contrato: dict[str, Any],
        test: dict[str, Any],
        test_anterior: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Revisa un intento y decide si aceptar, reintentar o reportar un bug."""
        codigo = test["codigo"]
        intento = test["intento"]

        try:
            ast.parse(codigo)
        except (SyntaxError, ValueError) as error:
            detalle = f"{type(error).__name__}: {error}"
            return self._error_test(contrato, intento, detalle)

        clave = (contrato["modulo"], contrato["objetivo"])
        if intento == 1:
            self._referencias.pop(clave, None)  # nueva corrida de este objetivo
        referencia = self._referencias.get(clave)
        if referencia is None and test_anterior is not None:
            referencia = test_anterior["codigo"]

        laundering = self._comparar_con_referencia(referencia, codigo)
        if laundering is None:
            self._referencias[clave] = codigo
        else:
            return self._resultado(
                objetivo=contrato["objetivo"],
                intento=intento,
                estado_sandbox="fallo",
                cobertura=None,
                laundering_detectado=True,
                tipo_fallo="error_test",
                hash_actual=hash_error(laundering),
                decision=self._decision_reintento(intento),
                feedback=laundering,
            )

        problema_oraculo = self._validar_oraculo(contrato, codigo)
        if problema_oraculo is not None:
            return self._error_test(contrato, intento, problema_oraculo)

        with tempfile.TemporaryDirectory(prefix="qagent-reviewer-") as temporal:
            ruta_tests = Path(temporal)
            (ruta_tests / "test_generado.py").write_text(codigo, encoding="utf-8")

            resultado = self.ejecutor(
                self.imagen,
                self.ruta_proyecto,
                ruta_tests,
                self.modulo_cov or self._modulo_cobertura(contrato["modulo"]),
            )

        estado = clasificar_resultado(resultado)
        salida = "\n".join(
            parte for parte in (resultado.stdout, resultado.stderr) if parte
        ).strip()
        # Cobertura de la función bajo prueba; si no se puede ubicar, la del módulo.
        cobertura = self._cobertura_de_funcion(
            resultado.coverage, contrato
        ) or self._extraer_cobertura(resultado.coverage)

        if estado == "ok":
            return self._resultado(
                objetivo=contrato["objetivo"],
                intento=intento,
                estado_sandbox="ok",
                cobertura=cobertura,
                laundering_detectado=False,
                tipo_fallo=None,
                hash_actual=None,
                decision="accept",
                feedback="Test aprobado en el sandbox.",
            )

        if self._es_error_del_test(salida):
            return self._error_test(
                contrato,
                intento,
                salida or "El test generado contiene un error técnico.",
                cobertura,
            )

        if estado == "fallo" and self._es_fallo_asercion(salida):
            return self._resultado(
                objetivo=contrato["objetivo"],
                intento=intento,
                estado_sandbox="fallo",
                cobertura=cobertura,
                laundering_detectado=False,
                tipo_fallo="bug_codigo",
                hash_actual=hash_error(salida),
                decision="bug_detectado",
                feedback=salida or "La aserción del contrato no se cumplió.",
            )

        tipo_ambiguo = self._clasificar_con_llm(salida, contrato)
        if tipo_ambiguo == "error_test":
            return self._error_test(contrato, intento, salida, cobertura)
        if tipo_ambiguo == "bug_codigo":
            return self._resultado(
                objetivo=contrato["objetivo"],
                intento=intento,
                estado_sandbox="fallo",
                cobertura=cobertura,
                laundering_detectado=False,
                tipo_fallo="bug_codigo",
                hash_actual=hash_error(salida),
                decision="bug_detectado",
                feedback=salida or "El código no cumple el contrato.",
            )

        if estado == "fallo":
            return self._resultado(
                objetivo=contrato["objetivo"],
                intento=intento,
                estado_sandbox="fallo",
                cobertura=cobertura,
                laundering_detectado=False,
                tipo_fallo=None,
                hash_actual=hash_error(salida) if salida else None,
                decision="stalled",
                feedback=(
                    salida
                    or "No se pudo distinguir entre error del test y bug del código."
                ),
            )

        return self._resultado(
            objetivo=contrato["objetivo"],
            intento=intento,
            estado_sandbox=estado,
            cobertura=cobertura,
            laundering_detectado=False,
            tipo_fallo=None,
            hash_actual=hash_error(salida) if salida else None,
            decision="stalled",
            feedback=salida or f"El sandbox terminó con estado {estado}.",
        )

    def _error_test(
        self,
        contrato: dict[str, Any],
        intento: int,
        detalle: str,
        cobertura: dict[str, float | None] | None = None,
    ) -> dict[str, Any]:
        return self._resultado(
            objetivo=contrato["objetivo"],
            intento=intento,
            estado_sandbox="fallo",
            cobertura=cobertura,
            laundering_detectado=False,
            tipo_fallo="error_test",
            hash_actual=hash_error(detalle),
            decision=self._decision_reintento(intento),
            feedback=detalle,
        )

    @staticmethod
    def _decision_reintento(intento: int) -> str:
        return "retry" if intento < 3 else "stalled"

    @classmethod
    def _validar_oraculo(
        cls,
        contrato: dict[str, Any],
        codigo: str,
    ) -> str | None:
        """Comprueba que el test use los valores esperados del Planner."""
        arbol = ast.parse(codigo)

        evasion = cls._detectar_evasion(arbol)
        if evasion is not None:
            return f"Oráculo inválido: {evasion}"

        valores_disponibles = cls._valores_de_aserciones(arbol)
        excepciones_disponibles = cls._excepciones_esperadas(arbol)
        cantidad_aserciones = sum(
            isinstance(nodo, (ast.Assert, ast.With)) for nodo in ast.walk(arbol)
        )
        if cantidad_aserciones == 0:
            return "Oráculo inválido: el test no contiene aserciones."

        for caso in contrato["casos"]:
            if "valor_esperado" in caso:
                esperado = caso["valor_esperado"]
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

    @staticmethod
    def _valores_de_aserciones(arbol: ast.AST) -> list[Any]:
        """Extrae los valores comparados en las aserciones del test."""
        valores: list[Any] = []
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Assert):
                continue
            prueba = nodo.test
            if not isinstance(prueba, ast.Compare):
                continue
            for comparador in prueba.comparators:
                valor = ReviewerAgent._valor_literal(comparador)
                if valor is not _NO_LITERAL:
                    valores.append(valor)
        return valores

    @staticmethod
    def _valor_literal(nodo: ast.AST) -> Any:
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
            if isinstance(nodo, ast.Try):
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

    @staticmethod
    def _comparar_con_referencia(
        codigo_referencia: str | None,
        codigo_actual: str,
    ) -> str | None:
        """Resumen del laundering si `codigo_actual` debilitó la referencia; si no, None."""
        if codigo_referencia is None:
            return None
        try:
            comparacion = comparar_aserciones(codigo_referencia, codigo_actual)
        except (SyntaxError, ValueError):
            return None
        if comparacion.es_laundering:
            return comparacion.resumen
        return None

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

    def _clasificar_con_llm(
        self,
        salida: str,
        contrato: dict[str, Any],
    ) -> str | None:
        if self.cliente is None or not salida:
            return None

        prompt = f"""
Clasifica el siguiente fallo de pytest.

Responde únicamente con una de estas opciones:
- error_test: el test tiene un error de sintaxis, import, fixture o mock.
- bug_codigo: una aserción legítima demuestra que el código no cumple el contrato.

CONTRATO DEL PLANNER:
{json.dumps(contrato, ensure_ascii=False, indent=2)}

SALIDA DE PYTEST:
{salida}
""".strip()

        respuesta = self.cliente.generar(prompt, rol="reviewer")
        self.tracker.registrar(
            agente="reviewer",
            modelo=respuesta.modelo,
            tokens_entrada=respuesta.tokens_entrada,
            tokens_salida=respuesta.tokens_salida,
            costo_usd=respuesta.costo_usd,
            es_simulado=self.es_simulado,
        )
        decision = respuesta.contenido.strip().lower()
        if decision in {"error_test", "bug_codigo"}:
            return decision
        return None

    @staticmethod
    def _modulo_cobertura(modulo: str) -> str:
        return Path(modulo).with_suffix("").as_posix().replace("/", ".")

    def _cobertura_de_funcion(
        self,
        coverage: dict[str, Any] | None,
        contrato: dict[str, Any],
    ) -> dict[str, float | None] | None:
        """Cobertura de líneas y ramas solo dentro del cuerpo de la función probada.

        coverage.py mide el módulo completo; aquí se cuentan solo las líneas y ramas
        que caen dentro de la función (su rango sale del `ast` del archivo, sin
        ejecutarlo). Devuelve None si no se puede ubicar el archivo o la función.
        """
        if not coverage or not isinstance(coverage.get("files"), dict):
            return None
        modulo = contrato["modulo"].replace("\\", "/")
        datos = next(
            (
                v
                for k, v in coverage["files"].items()
                if k.replace("\\", "/").endswith(modulo)
            ),
            None,
        )
        rango = self._rango_de_funcion(modulo, contrato["objetivo"])
        if not isinstance(datos, dict) or rango is None:
            return None
        inicio, fin = rango

        def dentro(numeros: Any) -> list[Any]:
            return [n for n in numeros or [] if inicio <= _linea(n) <= fin]

        ejecutadas = dentro(datos.get("executed_lines"))
        faltantes = dentro(datos.get("missing_lines"))
        total = len(ejecutadas) + len(faltantes)
        if not total:
            return None
        ramas_ok = dentro(datos.get("executed_branches"))
        ramas_no = dentro(datos.get("missing_branches"))
        total_ramas = len(ramas_ok) + len(ramas_no)
        return {
            "lineas": round(len(ejecutadas) * 100 / total, 2),
            "ramas": (
                round(len(ramas_ok) * 100 / total_ramas, 2) if total_ramas else None
            ),
        }

    def _rango_de_funcion(self, modulo: str, nombre: str) -> tuple[int, int] | None:
        """Primera y última línea del cuerpo de una función de nivel superior."""
        try:
            fuente = (self.ruta_proyecto / modulo).read_text(encoding="utf-8")
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

    @staticmethod
    def _extraer_cobertura(
        coverage: dict[str, Any] | None,
    ) -> dict[str, float | None] | None:
        if not coverage:
            return None
        totales = coverage.get("totals")
        if not isinstance(totales, dict):
            return None

        try:
            lineas = float(totales.get("percent_covered", 0.0))
        except (TypeError, ValueError):
            lineas = 0.0

        ramas_totales = int(totales.get("num_branches", 0) or 0)
        ramas_cubiertas = int(totales.get("covered_branches", 0) or 0)
        ramas = (
            round(ramas_cubiertas * 100 / ramas_totales, 2) if ramas_totales else None
        )
        return {"lineas": round(lineas, 2), "ramas": ramas}

    @staticmethod
    def _resultado(
        *,
        objetivo: str,
        intento: int,
        estado_sandbox: str,
        cobertura: dict[str, float | None] | None,
        laundering_detectado: bool,
        tipo_fallo: str | None,
        hash_actual: str | None,
        decision: str,
        feedback: str,
    ) -> dict[str, Any]:
        revision = {
            "version": "1",
            "objetivo": objetivo,
            "intento": intento,
            "estado_sandbox": estado_sandbox,
            "cobertura": cobertura,
            "laundering_detectado": laundering_detectado,
            "tipo_fallo": tipo_fallo,
            "hash_error": hash_actual,
            "decision": decision,
            "feedback": feedback,
        }
        contracts.validar(contracts.REVIEW_RESULT, revision)
        return revision


def _linea(numero: Any) -> int:
    """Línea de un dato de coverage.json: un número, o el origen de una rama [de, a]."""
    return int(numero[0] if isinstance(numero, (list, tuple)) else numero)
