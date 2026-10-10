"""Agente Reviewer/Executor: ejecuta y clasifica los tests generados."""

from __future__ import annotations

import ast
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

_PATRONES_ERROR_TEST = (
    "syntaxerror",
    "indentationerror",
    "importerror",
    "modulenotfounderror",
    "failed to import test module",
    "error at setup",
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

        laundering = self._comparar_con_anterior(test_anterior, codigo)
        if laundering is not None:
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
        cobertura = self._extraer_cobertura(resultado.coverage)

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

        if estado == "fallo":
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

        tipo_ambiguo = self._clasificar_con_llm(salida)
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

    @staticmethod
    def _comparar_con_anterior(
        test_anterior: dict[str, Any] | None,
        codigo_actual: str,
    ) -> str | None:
        if test_anterior is None:
            return None
        try:
            comparacion = comparar_aserciones(
                test_anterior["codigo"],
                codigo_actual,
            )
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

    def _clasificar_con_llm(self, salida: str) -> str | None:
        if self.cliente is None or not salida:
            return None

        prompt = f"""
Clasifica el siguiente fallo de pytest.

Responde únicamente con una de estas opciones:
- error_test: el test tiene un error de sintaxis, import, fixture o mock.
- bug_codigo: una aserción legítima demuestra que el código no cumple el contrato.

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
