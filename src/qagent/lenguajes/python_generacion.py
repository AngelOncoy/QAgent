"""Prompt del Generator para Python: un archivo pytest por contrato (#168).

Es el código que antes vivía en ``agents/generator.py``, movido sin cambios: el
Generator es compartido y pide el prompt al adaptador del contrato.

Si se conoce la carpeta del proyecto, el prompt de una función lleva el contexto
estático de su módulo (imports, nombres globales que usa, su código y los paquetes
del sandbox; ver ``qagent.analysis.contexto``). Sirve para importar y simular bien,
no para decidir el valor esperado: ese sale del contrato y el Reviewer rechaza
cualquier aserción que se aparte de él.
"""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any

from qagent.analysis.contexto import (
    PAQUETES_BASE,
    ContextoFuncion,
    contexto_de_funcion,
)
from qagent.llm.fake import MARCA_CONTRATO


def prompt_generator(
    contrato: dict[str, Any],
    intento: int,
    feedback: str | None,
    ruta_proyecto: Path | None,
) -> str:
    """Prompt del test pytest de ``contrato``; ``feedback`` ya viene recortado."""
    contexto = _contexto(contrato, ruta_proyecto)
    texto_dependencias = _contexto_dependencias(contrato, ruta_proyecto)
    return crear_prompt(
        contrato,
        intento,
        feedback,
        contexto,
        texto_dependencias=texto_dependencias,
    )


def _contexto_dependencias(contrato: dict[str, Any], ruta_proyecto: Path | None) -> str:
    """Contexto de dependencias inter-archivo con tree-sitter (0 tokens, ADR-012)."""
    if ruta_proyecto is None:
        return ""
    try:
        from qagent.analysis.grafo_imports import (
            construir_grafo_dependencias,
            formatear_contexto_grafo,
        )

        nombre_simbolo = (
            contrato.get("manejador")
            if contrato.get("tipo") == "endpoint" and contrato.get("manejador")
            else funcion_probada(contrato)
        )
        grafo = construir_grafo_dependencias(
            ruta_proyecto,
            contrato["modulo"],
            nombre_simbolo,
            tipo_objetivo=contrato.get("tipo", "funcion"),
        )
        return formatear_contexto_grafo(grafo, modulo_importable(contrato["modulo"]))
    except (ImportError, OSError, ValueError, KeyError, TypeError, AttributeError):
        return ""


def _contexto(
    contrato: dict[str, Any], ruta_proyecto: Path | None
) -> ContextoFuncion | None:
    """Contexto del módulo de una función (los endpoints ya traen su declaración)."""
    if ruta_proyecto is None or contrato.get("tipo") == "endpoint":
        return None
    return contexto_de_funcion(
        ruta_proyecto, contrato["modulo"], funcion_probada(contrato)
    )


def funcion_probada(contrato: dict[str, Any]) -> str:
    """Función que importa y llama el test: el objetivo, o la raíz de una integración."""
    if contrato.get("tipo") == "integracion":
        return str(contrato["cadena"][0])
    return str(contrato["objetivo"])


def crear_prompt(
    contrato: dict[str, Any],
    intento: int,
    feedback: str | None,
    contexto: ContextoFuncion | None = None,
    texto_dependencias: str = "",
) -> str:
    # Una sola línea: más corto (menos tokens) y la IA simulada lo puede leer.
    contrato_json = json.dumps(contrato, ensure_ascii=False)
    correccion = (
        feedback if feedback else "No existe feedback porque este es el primer intento."
    )
    regla_simulacion = "- Simula con mocks las funciones incluidas en llama_a."
    if contrato.get("tipo") == "endpoint":
        reglas_objetivo = _reglas_endpoint(contrato)
    elif contrato.get("tipo") == "integracion":
        reglas_objetivo = _reglas_integracion(contrato)
        regla_simulacion = (
            "- Simula solo lo que sale del proyecto; las funciones de la cadena "
            "se ejecutan de verdad."
        )
        if contexto is not None:
            reglas_objetivo += "\n" + _reglas_contexto(contrato)
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
        if contexto is not None:
            reglas_objetivo += "\n" + _reglas_contexto(contrato)
    return f"""
Escribe un archivo pytest completo para el contrato indicado.

REGLAS OBLIGATORIAS:
{reglas_objetivo}
- Escribe una función test_<id> por cada caso del contrato.
- Usa exactamente los valores esperados del contrato (pytest.approx para float).
- Si un caso trae "tipo_valor_esperado": "tuple", compara exactamente con un
  literal tupla (incluida la coma de una tupla unitaria); no conviertas el resultado
  con list() ni reemplaces la igualdad por longitud o elementos parciales.
- Un array sin esa metadata conserva su significado de lista.
- No ejecutes el código para descubrir resultados.
- No elimines, cambies ni debilites las aserciones; sin try/except, skip ni xfail.
{regla_simulacion}
- Devuelve únicamente código Python, sin explicaciones.
- Este es el intento {intento}.

FEEDBACK DEL INTENTO ANTERIOR:
{correccion}
{_texto_contexto(contexto)}
{texto_dependencias}
{MARCA_CONTRATO} {contrato_json}
""".strip()


def _reglas_integracion(contrato: dict[str, Any]) -> str:
    """Reglas de una prueba de integración interna (#245, ADR-014)."""
    raiz, *internas = contrato["cadena"]
    importacion = f"from {modulo_importable(contrato['modulo'])} import {raiz}"
    efectos = ", ".join(contrato.get("efectos") or []) or "(ninguno detectado)"
    simulables = ", ".join(contrato.get("llama_a") or []) or "(ninguna)"
    return f"""
- Es una prueba de INTEGRACIÓN: llama a la función raíz y deja que se ejecuten DE VERDAD
  las funciones internas de la cadena ({", ".join(internas)}). No las simules ni uses
  patch sobre ellas.
- Importa la raíz exactamente así: {importacion}
- Llama a {raiz} con la entrada de cada caso.
- Para un caso con "excepcion" usa: with pytest.raises(<Excepcion>).
- Simula solo lo que sale del proyecto: red, base de datos, archivos, subprocesos, hora y
  azar. Módulos de efecto que usa la raíz: {efectos}. Funciones internas de efecto
  (simúlalas): {simulables}.
- El valor esperado de cada caso sale SIEMPRE del contrato (firma y documentación de la
  raíz), nunca del código de las funciones internas ni de ejecutarlas.
""".strip()


def _reglas_contexto(contrato: dict[str, Any]) -> str:
    """Reglas para usar el contexto del módulo sin tocar el oráculo del contrato."""
    modulo = modulo_importable(contrato["modulo"])
    return f"""
- Usa el CONTEXTO DEL MÓDULO solo para saber qué importar y qué simular. El valor
  esperado de cada caso sale SIEMPRE del contrato, nunca del código de la función.
- Si la función usa nombres globales del módulo (configuración, clientes, objetos
  de un framework como request o g, bibliotecas opcionales), simúlalos con
  unittest.mock.patch("{modulo}.<nombre>").
- No importes paquetes que no estén instalados en el sandbox: simúlalos.
""".strip()


def _texto_contexto(contexto: ContextoFuncion | None) -> str:
    """Bloque CONTEXTO DEL MÓDULO del prompt (vacío si no hay contexto)."""
    if contexto is None:
        return ""
    instalados = ", ".join([*PAQUETES_BASE, *contexto.paquetes])
    return f"""
CONTEXTO DEL MÓDULO (para importar y simular; no para decidir valores esperados):
Imports del módulo:
{chr(10).join(contexto.imports) or "(ninguno)"}
Nombres globales del módulo que usa la función: {", ".join(contexto.globales_usados) or "(ninguno)"}
Paquetes instalados en el sandbox: {instalados}
Código de la función:
{contexto.codigo}
"""


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
