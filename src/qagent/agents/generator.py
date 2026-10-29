"""Agente Generator: convierte un contrato del Planner en el código de su test.

Es compartido por todos los lenguajes (#168): el prompt lo arma el adaptador del
lenguaje del contrato (en Python, un archivo pytest con el contexto estático del
módulo) y su sintaxis la revisan las reglas del mismo adaptador. El valor esperado
sale siempre del contrato; el Reviewer rechaza cualquier aserción que se aparte de él.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from qagent import contracts
from qagent.lenguajes import adaptador_de_contrato
from qagent.llm import ClienteLLM, TokenTracker

#: Caracteres de feedback (salida del runner) que se reenvían al modelo.
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
        ruta_proyecto: str | Path | None = None,
    ) -> None:
        """Inicializa el Generator con su cliente y registro de tokens.

        Args:
            ruta_proyecto: carpeta del proyecto; si se da, el adaptador puede sumar
                al prompt el contexto estático del módulo. Si es None, solo el contrato.
        """
        self.cliente = cliente
        self.tracker = tracker
        self.es_simulado = es_simulado
        self.ruta_proyecto = Path(ruta_proyecto) if ruta_proyecto else None

    def generar(
        self,
        contrato: dict[str, Any],
        intento: int,
        feedback: str | None,
    ) -> dict[str, Any]:
        """Genera o corrige el test de `contrato` (`generated_test.v2`)."""
        adaptador = adaptador_de_contrato(contrato)
        prompt = adaptador.prompt_generator(
            contrato,
            intento,
            _recortar(feedback) if feedback else None,
            self.ruta_proyecto,
        )
        respuesta = self.cliente.generar(prompt, rol="generator")

        self.tracker.registrar(
            agente="generator",
            modelo=respuesta.modelo,
            tokens_entrada=respuesta.tokens_entrada,
            tokens_salida=respuesta.tokens_salida,
            costo_usd=respuesta.costo_usd,
            es_simulado=self.es_simulado,
            es_estimado=getattr(respuesta, "es_estimado", False),
        )

        codigo = _quitar_cerca(respuesta.contenido)
        if not codigo.strip():
            raise ErrorRespuestaGenerator("El Generator devolvió código vacío.")
        error = adaptador.reglas_revision().error_de_sintaxis(codigo)
        if error is not None:
            raise ErrorRespuestaGenerator(
                f"El Generator devolvió código {adaptador.nombre_visible} "
                f"inválido: {error}",
                codigo=codigo,
            )

        # generated_test.v2 (#168): con el lenguaje y el framework del contrato.
        return contracts.generated_test_para(contrato, intento, codigo)


def _recortar(texto: str, maximo: int = LARGO_MAXIMO_FEEDBACK) -> str:
    """Deja solo el final del feedback (donde el runner pone el error) para ahorrar tokens."""
    if len(texto) <= maximo:
        return texto
    return "[…recortado…]\n" + texto[-maximo:]


def _quitar_cerca(contenido: str) -> str:
    """Elimina una cerca Markdown (```python, ```ts...) si el modelo la agregó."""
    texto = contenido.strip()
    if texto.startswith("```"):
        lineas = texto.splitlines()
        if lineas and lineas[0].strip().startswith("```"):
            lineas.pop(0)
        if lineas and lineas[-1].strip() == "```":
            lineas.pop()
        texto = "\n".join(lineas).strip()
    return texto + "\n" if texto else ""
