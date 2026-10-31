"""Agente Reviewer/Executor: ejecuta y clasifica los tests generados.

Es compartido por todos los lenguajes (#168): ejecuta en el sandbox con el comando,
el archivo, el informe y la cobertura del adaptador del contrato, y le pide sus
reglas para la sintaxis, el oráculo y la clasificación de la salida. Lo que decide
(aceptar, reintentar, bug o estancado) es igual en todos los lenguajes.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from qagent import contracts
from qagent.lenguajes import LanguageAdapter, adaptador_de_contrato
from qagent.llm import ClienteLLM, TokenTracker
from qagent.sandbox import (
    LIMITES_POR_DEFECTO,
    LimitesSandbox,
    ResultadoSandbox,
    clasificar_resultado,
    ejecutar_pruebas,
    resumir_ejecucion,
)
from qagent.sandbox.archivos_prueba import ruta_de_prueba
from qagent.sandbox.ejecucion import ejecutar_comando_pruebas
from qagent.sandbox.normalizacion import hash_error

Ejecutor = Callable[[str, Path, Path, str], ResultadoSandbox]


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
        ejecutor: Ejecutor | None = None,
        es_simulado: bool = False,
        limites: LimitesSandbox = LIMITES_POR_DEFECTO,
    ) -> None:
        """Inicializa el Reviewer con el sandbox y cliente opcional.

        `limites` son los de `[sandbox]` en config.toml; se aplican al sandbox real.
        Sin `ejecutor` (o con `ejecutar_pruebas`), las pruebas corren con el
        comando y los lectores del adaptador del contrato (#168). Un ejecutor de
        pruebas conserva su firma de 4 argumentos.
        """
        self.tracker = tracker
        self.ruta_proyecto = Path(ruta_proyecto)
        self.imagen = imagen
        self.cliente = cliente
        self.modulo_cov = modulo_cov
        self.limites = limites
        self.ejecutor = None if ejecutor is ejecutar_pruebas else ejecutor
        self.es_simulado = es_simulado
        # Último test NO debilitado de cada objetivo: la referencia contra la que se
        # busca laundering. Si se comparara solo con el intento anterior, un intento
        # rechazado por laundering pasaría a ser la referencia del siguiente.
        self._referencias: dict[tuple[str, str], str] = {}
        # `ejecucion` del último intento que llegó al sandbox (EN-17).
        self._ejecucion: dict[str, Any] | None = None

    def revisar(
        self,
        contrato: dict[str, Any],
        test: dict[str, Any],
        test_anterior: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Revisa un intento y decide si aceptar, reintentar o reportar un bug.

        Si el test llegó a ejecutarse en el sandbox, el veredicto incluye `ejecucion`
        (casos, salida y entorno) para el informe detallado (EN-17).
        """
        self._ejecucion = None
        revision = self._revisar(contrato, test, test_anterior)
        if self._ejecucion is not None:
            revision["ejecucion"] = self._ejecucion
            contracts.validar(contracts.REVIEW_RESULT, revision)
        return revision

    def _revisar(
        self,
        contrato: dict[str, Any],
        test: dict[str, Any],
        test_anterior: dict[str, Any] | None,
    ) -> dict[str, Any]:
        codigo = test["codigo"]
        intento = test["intento"]
        # #168: el lenguaje sale del contrato (un v2 es Python).
        adaptador = adaptador_de_contrato(contrato)
        reglas = adaptador.reglas_revision()

        error_sintaxis = reglas.error_de_sintaxis(codigo)
        if error_sintaxis is not None:
            return self._error_test(contrato, intento, error_sintaxis)

        clave = (contrato["modulo"], contrato["objetivo"])
        if intento == 1:
            self._referencias.pop(clave, None)  # nueva corrida de este objetivo
        referencia = self._referencias.get(clave)
        if referencia is None and test_anterior is not None:
            codigo_anterior = test_anterior["codigo"]
            try:
                if (
                    adaptador.validar_oraculo(
                        contrato, codigo_anterior, self.ruta_proyecto
                    )
                    is None
                ):
                    referencia = codigo_anterior
            except (SyntaxError, ValueError):
                referencia = None

        laundering = self._comparar_con_referencia(adaptador, referencia, codigo)
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

        problema_oraculo = adaptador.validar_oraculo(
            contrato, codigo, self.ruta_proyecto
        )
        if problema_oraculo is not None:
            return self._error_test(contrato, intento, problema_oraculo)
        try:
            archivo_calculado = adaptador.archivo_para_contrato(
                contrato, self.ruta_proyecto
            )
            archivo = (
                test.get("archivo")
                or archivo_calculado
                or adaptador.archivo_de_prueba(contrato["objetivo"])
            )
            if archivo_calculado is not None and archivo not in {
                archivo_calculado,
                Path(archivo_calculado).name,
            }:
                return self._error_test(
                    contrato,
                    intento,
                    "El archivo de prueba no corresponde al paquete y clase del contrato.",
                )
        except (OSError, UnicodeError, ValueError) as error:
            return self._error_test(contrato, intento, str(error))
        self._referencias[clave] = codigo

        modulo_cov = self.modulo_cov or adaptador.modulo_cobertura(contrato["modulo"])
        framework = contracts.normalizar_planner(contrato)["framework_pruebas"]
        comando = adaptador.comando_pruebas(modulo_cov, framework)
        with tempfile.TemporaryDirectory(prefix="qagent-reviewer-") as temporal:
            ruta_tests = Path(temporal)
            try:
                destino = ruta_de_prueba(ruta_tests, archivo)
            except ValueError as error:
                return self._error_test(contrato, intento, str(error))
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(codigo, encoding="utf-8")
            if self.ejecutor is not None:
                resultado = self.ejecutor(
                    self.imagen, self.ruta_proyecto, ruta_tests, modulo_cov
                )
            else:
                opciones_sandbox = {}
                if (preparar := adaptador.preparador_sandbox()) is not None:
                    opciones_sandbox["preparar"] = preparar
                if (leer_informe := adaptador.lector_informe_sandbox()) is not None:
                    opciones_sandbox["leer_informe"] = leer_informe
                resultado = ejecutar_comando_pruebas(
                    self.imagen,
                    comando,
                    self.ruta_proyecto,
                    ruta_tests,
                    leer_cobertura=adaptador.leer_cobertura,
                    archivo_informe=adaptador.entorno_sandbox().informe,
                    variables=adaptador.variables_pruebas(),
                    limites=self.limites,
                    **opciones_sandbox,
                )

        estado = clasificar_resultado(resultado)
        modulo = contrato["modulo"].replace("\\", "/")
        rango = reglas.rango_de_objetivo(
            self.ruta_proyecto,
            modulo,
            contrato.get("manejador") or contrato["objetivo"],
        )
        self._ejecucion = resumir_ejecucion(
            resultado,
            imagen=self.imagen,
            comando=comando,
            limites=resultado.limites or self.limites,
            lineas_sin_cubrir=self._lineas_sin_cubrir(
                resultado.coverage, modulo, rango
            ),
            codigo_test=codigo,
            interpretar=adaptador.interpretar_resultados,
        )
        salida = "\n".join(
            parte for parte in (resultado.stdout, resultado.stderr) if parte
        ).strip()
        # Cobertura de la función bajo prueba; si no se puede ubicar, la del módulo.
        cobertura = adaptador.cobertura_de_objetivo(
            resultado.coverage, modulo, contrato["objetivo"]
        )
        if cobertura is NotImplemented:
            cobertura = self._cobertura_de_funcion(
                resultado.coverage, modulo, rango
            ) or self._extraer_cobertura(resultado.coverage)

        clasificacion = adaptador.clasificar_ejecucion(resultado)
        if clasificacion is not None and clasificacion.motivo_sin_veredicto:
            revision = self._resultado(
                objetivo=contrato["objetivo"],
                intento=intento,
                estado_sandbox=estado,
                cobertura=cobertura,
                laundering_detectado=False,
                tipo_fallo=None,
                hash_actual=hash_error(salida or clasificacion.detalle),
                decision="stalled",
                feedback=clasificacion.detalle,
            )
            revision["motivo_sin_veredicto"] = clasificacion.motivo_sin_veredicto
            contracts.validar(contracts.REVIEW_RESULT, revision)
            return revision

        if estado == "ok" and clasificacion is None:
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

        if clasificacion is None:
            clasificacion = reglas.clasificar_salida(
                salida, contrato, self.ruta_proyecto
            )
        tipo = clasificacion.tipo if clasificacion is not None else None
        if clasificacion is not None and tipo == "entorno":
            return self._resultado(
                objetivo=contrato["objetivo"],
                intento=intento,
                estado_sandbox="fallo",  # no aborta el módulo
                cobertura=cobertura,
                laundering_detectado=False,
                tipo_fallo=None,
                hash_actual=hash_error(salida),
                decision="stalled",
                feedback=(
                    f"Error de entorno: {clasificacion.detalle}. "
                    "Reintentar no lo corrige."
                ),
            )

        if clasificacion is not None and tipo == "bug_respuesta":
            return self._resultado(
                objetivo=contrato["objetivo"],
                intento=intento,
                estado_sandbox="fallo",
                cobertura=cobertura,
                laundering_detectado=False,
                tipo_fallo="bug_codigo",
                hash_actual=hash_error(salida),
                decision="bug_detectado",
                feedback=clasificacion.detalle,
            )

        if tipo == "error_test":
            return self._error_test(
                contrato,
                intento,
                salida or "El test generado contiene un error técnico.",
                cobertura,
            )

        if estado == "fallo" and tipo == "fallo_asercion":
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

        tipo_ambiguo = self._clasificar_con_llm(salida, contrato, framework)
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

    @staticmethod
    def _validar_oraculo(contrato: dict[str, Any], codigo: str) -> str | None:
        """Oráculo del test según las reglas del lenguaje del contrato."""
        reglas = adaptador_de_contrato(contrato).reglas_revision()
        return reglas.validar_oraculo(contrato, codigo)

    @staticmethod
    def _comparar_con_referencia(
        adaptador: LanguageAdapter,
        codigo_referencia: str | None,
        codigo_actual: str,
    ) -> str | None:
        """Resumen del laundering si `codigo_actual` debilitó la referencia; si no, None."""
        if codigo_referencia is None:
            return None
        try:
            comparacion = adaptador.comparar_aserciones(
                codigo_referencia, codigo_actual
            )
        except (SyntaxError, ValueError):
            return None
        if comparacion.es_laundering:
            return comparacion.resumen
        return None

    def _clasificar_con_llm(
        self,
        salida: str,
        contrato: dict[str, Any],
        framework: str,
    ) -> str | None:
        if self.cliente is None or not salida:
            return None

        prompt = f"""
Clasifica el siguiente fallo de {framework}.

Responde únicamente con una de estas opciones:
- error_test: el test tiene un error de sintaxis, import, fixture o mock.
- bug_codigo: una aserción legítima demuestra que el código no cumple el contrato.

CONTRATO DEL PLANNER:
{json.dumps(contrato, ensure_ascii=False, indent=2)}

SALIDA DE {framework.upper()}:
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
            es_estimado=getattr(respuesta, "es_estimado", False),
        )
        decision = respuesta.contenido.strip().lower()
        if decision in {"error_test", "bug_codigo"}:
            return decision
        return None

    @staticmethod
    def _datos_del_modulo(
        coverage: dict[str, Any] | None, modulo: str
    ) -> dict[str, Any] | None:
        """Datos de `modulo` en la cobertura (formato JSON de coverage.py)."""
        if not coverage or not isinstance(coverage.get("files"), dict):
            return None
        datos = next(
            (
                v
                for k, v in coverage["files"].items()
                if k.replace("\\", "/").endswith(modulo)
            ),
            None,
        )
        return datos if isinstance(datos, dict) else None

    def _cobertura_de_funcion(
        self,
        coverage: dict[str, Any] | None,
        modulo: str,
        rango: tuple[int, int] | None,
    ) -> dict[str, float | None] | None:
        """Cobertura de líneas y ramas solo dentro del cuerpo de la función probada.

        La cobertura mide el módulo completo; aquí se cuentan solo las líneas y ramas
        que caen dentro de la función (su rango lo da el adaptador, sin ejecutar el
        código). Devuelve None si no se puede ubicar el archivo o la función.
        """
        datos = self._datos_del_modulo(coverage, modulo)
        if datos is None or rango is None:
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

    def _lineas_sin_cubrir(
        self,
        coverage: dict[str, Any] | None,
        modulo: str,
        rango: tuple[int, int] | None,
    ) -> list[int] | None:
        """Líneas de la función probada que ningún caso ejecutó (EN-17)."""
        datos = self._datos_del_modulo(coverage, modulo)
        if datos is None or rango is None:
            return None
        inicio, fin = rango
        faltantes = {
            _linea(n)
            for n in datos.get("missing_lines") or []
            if inicio <= _linea(n) <= fin
        }
        return sorted(faltantes)

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
