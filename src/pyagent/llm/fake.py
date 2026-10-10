"""Cliente de IA simulada (Fake LLM): 0 tokens, sin red (EN-11).

Responde según el rol y, cuando el prompt trae los datos marcados por los agentes,
según lo que se le pide:

- **Planner:** devuelve los casos grabados en `bench/ia_simulada.json` para las
  funciones del módulo (el oráculo se escribió a mano a partir de los docstrings).
  Una función sin casos grabados queda fuera del plan.
- **Generator:** arma el archivo pytest directamente desde el contrato del Planner.
- **Reviewer:** no clasifica fallos ambiguos (la decisión queda en manos de las reglas).

Si el prompt no trae esos datos, devuelve las respuestas grabadas de siempre.
"""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any, ClassVar

from pyagent.llm.modelos import RespuestaLLM

#: Marcadores de las líneas con datos que escriben los agentes en sus prompts.
MARCA_MODULO = "MODULO:"
MARCA_OBJETIVOS = "OBJETIVOS_JSON:"
MARCA_CONTRATO = "CONTRATO_JSON:"

RUTA_GRABACIONES = Path(__file__).resolve().parents[3] / "bench" / "ia_simulada.json"


class FakeLLMClient:
    """Simulador de LLM que devuelve respuestas grabadas y reporta 0 tokens."""

    # Respuestas que cumplen los contratos de contracts/ (EN-01): el Planner devuelve
    # una lista de planner_contract.v2 por módulo y el Reviewer un review_result.
    RESPUESTAS_GRABADAS: ClassVar[dict[str, str]] = {
        "planner": json.dumps(
            [
                {
                    "version": "2",
                    "modulo": "modulo_simulado.py",
                    "huella": "0" * 64,
                    "tipo": "funcion",
                    "objetivo": "duplicar",
                    "firma": "(x: int) -> int",
                    "critical": False,
                    "llama_a": [],
                    "casos": [
                        {
                            "id": "caso_1",
                            "entrada": {"x": 10},
                            "valor_esperado": 20,
                            "origen": "docstring",
                        }
                    ],
                }
            ]
        ),
        "generator": (
            "from modulo_simulado import duplicar\n\n\n"
            "def test_caso_1():\n"
            "    assert duplicar(10) == 20\n"
        ),
        "reviewer": json.dumps(
            {
                "version": "1",
                "objetivo": "duplicar",
                "intento": 1,
                "estado_sandbox": "ok",
                "cobertura": {"lineas": 100.0, "ramas": 100.0},
                "laundering_detectado": False,
                "tipo_fallo": None,
                "hash_error": None,
                "decision": "accept",
                "feedback": "Test aprobado en sandbox.",
            }
        ),
    }

    def __init__(
        self,
        modelo: str = "fake-model-v1",
        grabaciones: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        """Inicializa el cliente simulado.

        Args:
            modelo: Nombre que se registrará como modelo utilizado.
            grabaciones: casos por `"<archivo>.py::<función>"`; si es None se leen de
                `bench/ia_simulada.json` (o quedan vacías si no existe).
        """
        self.modelo = modelo
        self.grabaciones = (
            grabaciones if grabaciones is not None else cargar_grabaciones()
        )

    def generar(self, prompt: str, rol: str = "generator") -> RespuestaLLM:
        """Devuelve una respuesta simulada según el rol solicitado.

        Args:
            prompt: Instrucción recibida. No se envía a internet.
            rol: Agente que solicita la respuesta: planner, generator o reviewer.

        Returns:
            Respuesta simulada con consumo de cero tokens y costo cero.
        """
        rol = rol.lower()
        contenido: str | None = None
        if rol == "planner":
            contenido = self._planificar(prompt)
        elif rol == "generator":
            contenido = self._generar_test(prompt)
        if contenido is None:
            contenido = self.RESPUESTAS_GRABADAS.get(
                rol, f"Respuesta simulada para prompt: {prompt[:30]}..."
            )
        return RespuestaLLM(
            contenido=contenido,
            tokens_entrada=0,
            tokens_salida=0,
            costo_usd=0.0,
            modelo=self.modelo,
        )

    # --- Planner ----------------------------------------------------------------------

    def _planificar(self, prompt: str) -> str | None:
        modulo = _valor_marcado(prompt, MARCA_MODULO)
        objetivos = _json_marcado(prompt, MARCA_OBJETIVOS)
        if modulo is None or not isinstance(objetivos, list):
            return None
        archivo = PurePosixPath(modulo.replace("\\", "/")).name
        plan = []
        for objetivo in objetivos:
            nombre = objetivo.get("nombre") if isinstance(objetivo, dict) else None
            casos = self.grabaciones.get(f"{archivo}::{nombre}")
            if casos:
                plan.append({"objetivo": nombre, "casos": casos})
        return json.dumps(plan, ensure_ascii=False)

    # --- Generator --------------------------------------------------------------------

    @staticmethod
    def _generar_test(prompt: str) -> str | None:
        contrato = _json_marcado(prompt, MARCA_CONTRATO)
        if not isinstance(contrato, dict):
            return None
        return generar_test_desde_contrato(contrato)


def cargar_grabaciones(
    ruta: Path = RUTA_GRABACIONES,
) -> dict[str, list[dict[str, Any]]]:
    """Lee los casos grabados de la IA simulada; {} si el archivo no existe o es inválido."""
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    casos = datos.get("casos") if isinstance(datos, dict) else None
    return casos if isinstance(casos, dict) else {}


def generar_test_desde_contrato(contrato: dict[str, Any]) -> str:
    """Archivo pytest con una función `test_<id>` por caso del contrato.

    Los valores esperados se copian del contrato (nunca de ejecutar el código); los
    `float` se comparan con `pytest.approx`.
    """
    modulo = (
        PurePosixPath(str(contrato["modulo"]).replace("\\", "/"))
        .with_suffix("")
        .as_posix()
        .replace("/", ".")
    )
    objetivo = contrato["objetivo"]
    lineas = ["import pytest", "", f"from {modulo} import {objetivo}", ""]
    for caso in contrato.get("casos", []):
        llamada = f"{objetivo}({_argumentos(caso.get('entrada'))})"
        lineas += ["", f"def test_{caso['id']}():"]
        if "excepcion" in caso:
            lineas += [
                f"    with pytest.raises({caso['excepcion']}):",
                f"        {llamada}",
            ]
        else:
            lineas.append(
                f"    assert {llamada} {_comparacion(caso['valor_esperado'])}"
            )
    return "\n".join(lineas) + "\n"


def _argumentos(entrada: Any) -> str:
    if isinstance(entrada, dict):
        return ", ".join(f"{nombre}={valor!r}" for nombre, valor in entrada.items())
    if isinstance(entrada, list):
        return ", ".join(repr(valor) for valor in entrada)
    return "" if entrada is None else repr(entrada)


def _comparacion(esperado: Any) -> str:
    if esperado is None:
        return "is None"
    if isinstance(esperado, float):
        return f"== pytest.approx({esperado!r})"
    return f"== {esperado!r}"


def _valor_marcado(prompt: str, marca: str) -> str | None:
    """Texto que sigue a `marca` en la primera línea que empieza con ella."""
    for linea in prompt.splitlines():
        if linea.startswith(marca):
            return linea[len(marca) :].strip()
    return None


def _json_marcado(prompt: str, marca: str) -> Any:
    texto = _valor_marcado(prompt, marca)
    if texto is None:
        return None
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        return None
