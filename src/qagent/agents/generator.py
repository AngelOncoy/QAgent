"""Agente Generator: convierte un contrato del Planner en código pytest."""

from __future__ import annotations

import ast
import json
from pathlib import PurePosixPath
from typing import Any

from qagent import contracts
from qagent.llm import ClienteLLM, TokenTracker
from qagent.llm.fake import MARCA_CONTRATO

#: Caracteres de feedback (salida de pytest) que se reenvían al modelo.
LARGO_MAXIMO_FEEDBACK = 2000


class ErrorRespuestaGenerator(ValueError):
    """El Generator devolvió una respuesta que no puede utilizarse."""

    def __init__(self, mensaje: str, *, codigo: str = "") -> None:
        super().__init__(mensaje)
        self.codigo = codigo


class GeneratorAgent:
    """Genera el test de un único objetivo a partir de su contrato."""

    def __init__(
        self,
        cliente: ClienteLLM,
        tracker: TokenTracker,
        *,
        es_simulado: bool = False,
    ) -> None:
        """Inicializa el Generator con su cliente y registro de tokens."""
        self.cliente = cliente
        self.tracker = tracker
        self.es_simulado = es_simulado

    def generar(
        self,
        contrato: dict[str, Any],
        intento: int,
        feedback: str | None,
    ) -> dict[str, Any]:
        """Genera o corrige un test pytest."""
        prompt = self._crear_prompt(contrato, intento, feedback)
        respuesta = self.cliente.generar(prompt, rol="generator")

        self.tracker.registrar(
            agente="generator",
            modelo=respuesta.modelo,
            tokens_entrada=respuesta.tokens_entrada,
            tokens_salida=respuesta.tokens_salida,
            costo_usd=respuesta.costo_usd,
            es_simulado=self.es_simulado,
        )

        codigo = _quitar_cerca_python(respuesta.contenido)
        if not codigo.strip():
            raise ErrorRespuestaGenerator("El Generator devolvió código vacío.")
        try:
            ast.parse(codigo)
        except (SyntaxError, ValueError) as error:
            raise ErrorRespuestaGenerator(
                f"El Generator devolvió código Python inválido: {type(error).__name__}: {error}",
                codigo=codigo,
            ) from error

        generado = {
            "version": "1",
            "objetivo": contrato["objetivo"],
            "intento": intento,
            "codigo": codigo,
            "casos_cubiertos": [caso["id"] for caso in contrato["casos"]],
        }
        contracts.validar(contracts.GENERATED_TEST, generado)
        return generado

    @staticmethod
    def _crear_prompt(
        contrato: dict[str, Any],
        intento: int,
        feedback: str | None,
    ) -> str:
        # Una sola línea: más corto (menos tokens) y la IA simulada lo puede leer.
        contrato_json = json.dumps(contrato, ensure_ascii=False)
        correccion = (
            _recortar(feedback)
            if feedback
            else "No existe feedback porque este es el primer intento."
        )
        if contrato.get("tipo") == "endpoint":
            reglas_objetivo = _reglas_endpoint(contrato)
        else:
            importacion = (
                f"from {modulo_importable(contrato['modulo'])} import "
                f"{contrato['objetivo']}"
            )
            reglas_objetivo = f"""
- Importa el objetivo exactamente así: {importacion}
- Llama directamente a la función con la entrada de cada caso.
- Para un caso con "excepcion" usa: with pytest.raises(<Excepcion>).
""".strip()
        return f"""
Escribe un archivo pytest completo para el contrato indicado.

REGLAS OBLIGATORIAS:
{reglas_objetivo}
- Escribe una función test_<id> por cada caso del contrato.
- Usa exactamente los valores esperados del contrato (pytest.approx para float).
- No ejecutes el código para descubrir resultados.
- No elimines, cambies ni debilites las aserciones; sin try/except, skip ni xfail.
- Simula con mocks las funciones incluidas en llama_a.
- Devuelve únicamente código Python, sin explicaciones.
- Este es el intento {intento}.

FEEDBACK DEL INTENTO ANTERIOR:
{correccion}

{MARCA_CONTRATO} {contrato_json}
""".strip()


def _reglas_endpoint(contrato: dict[str, Any]) -> str:
    """Reglas de generación para un endpoint FastAPI descrito por el contrato."""
    modulo = modulo_importable(contrato["modulo"])
    aplicacion = contrato["aplicacion"]
    dependencias = contrato.get("dependencias", [])
    simbolos = [aplicacion]
    for dependencia in dependencias:
        simbolos.extend([dependencia["funcion"], dependencia["reemplazo"]])
    importacion = f"from {modulo} import {', '.join(dict.fromkeys(simbolos))}"
    detalle_overrides = (
        json.dumps(dependencias, ensure_ascii=False)
        if dependencias
        else "[] (este endpoint no declara Depends)"
    )
    return f"""
- Usa fastapi.testclient.TestClient para realizar una petición HTTP real en memoria.
- Importa la aplicación y los símbolos de override exactamente así: {importacion}
- Construye TestClient({aplicacion}, raise_server_exceptions=False).
- Usa client.request con método, ruta, query, json y headers del contrato.
- Comprueba siempre response.status_code.
- Si valor_esperado trae "json", compara response.json() completo.
- Si trae "json_contiene", comprueba cada clave y valor indicados.
- Dependencias a reemplazar: {detalle_overrides}
- Para cada dependencia asigna {aplicacion}.dependency_overrides[funcion] = reemplazo.
- Si una entrada trae "preparacion", instancia el reemplazo una vez en la fixture,
  ejecuta allí cada método/modelo/argumentos declarado y usa un lambda que devuelva
  esa misma instancia durante el test.
- Usa una fixture con try/finally: guarda una copia de los overrides anteriores y,
  al terminar cada test, limpia el diccionario y restaura exactamente esa copia.
- Nunca reemplaces el manejador de la ruta ni modelos Pydantic.
""".strip()


def modulo_importable(modulo: str) -> str:
    """Ruta del módulo relativa al proyecto -> nombre importable.

    En el sandbox `PYTHONPATH` es la raíz del proyecto, así que
    `bench/banco_mvp.py` se importa como `bench.banco_mvp`.
    """
    return (
        PurePosixPath(modulo.replace("\\", "/"))
        .with_suffix("")
        .as_posix()
        .replace("/", ".")
    )


def _recortar(texto: str, maximo: int = LARGO_MAXIMO_FEEDBACK) -> str:
    """Deja solo el final del feedback (donde pytest pone el error) para ahorrar tokens."""
    if len(texto) <= maximo:
        return texto
    return "[…recortado…]\n" + texto[-maximo:]


def _quitar_cerca_python(contenido: str) -> str:
    """Elimina una cerca Markdown ```python si el modelo la agregó."""
    texto = contenido.strip()
    if texto.startswith("```"):
        lineas = texto.splitlines()
        if lineas and lineas[0].strip().startswith("```"):
            lineas.pop(0)
        if lineas and lineas[-1].strip() == "```":
            lineas.pop()
        texto = "\n".join(lineas).strip()
    return texto + "\n" if texto else ""
