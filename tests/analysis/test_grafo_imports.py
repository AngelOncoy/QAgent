"""Pruebas unitarias para el prototipo de grafo de imports tree-sitter (SPK #196)."""

from __future__ import annotations

from pathlib import Path

from qagent.agents.generator import GeneratorAgent
from qagent.analysis.grafo_imports import (
    construir_grafo_dependencias,
    formatear_contexto_grafo,
    parsear_archivo,
)
from qagent.llm import TokenTracker
from qagent.llm.modelos import RespuestaLLM


class ClienteEspia:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generar(self, prompt: str, rol: str = "generator") -> RespuestaLLM:
        self.prompts.append(prompt)
        return RespuestaLLM(
            contenido="def test_dummy():\n    assert True\n",
            tokens_entrada=10,
            tokens_salida=5,
            costo_usd=0.0,
            modelo="espia",
        )


def test_parsear_archivo_valido(tmp_path: Path) -> None:
    archivo = tmp_path / "modulo.py"
    archivo.write_text(
        "def saludar(nombre: str) -> str:\n    return f'Hola {nombre}'\n",
        encoding="utf-8",
    )
    resultado = parsear_archivo(archivo)
    assert resultado is not None
    _arbol, fuente = resultado
    assert "def saludar" in fuente


def test_parsear_archivo_inexistente(tmp_path: Path) -> None:
    assert parsear_archivo(tmp_path / "fantasma.py") is None


def test_construir_grafo_en_bench_dependencias() -> None:
    raiz = Path(".")
    grafo = construir_grafo_dependencias(
        raiz,
        "bench/dependencias/procesador_pagos.py",
        "procesar_transferencia",
        tipo_objetivo="funcion",
    )
    nombres_directos = [s.nombre for s in grafo.simbolos_directos]
    assert "ejecutar_debito" in nombres_directos
    assert "ejecutar_credito" in nombres_directos
    assert "Transaccion" in nombres_directos

    debito_info = next(
        s for s in grafo.simbolos_directos if s.nombre == "ejecutar_debito"
    )
    assert debito_info.tipo == "funcion"
    assert "cuenta: str" in debito_info.firma
    assert "-> str" in debito_info.firma
    assert "Debita el monto" in debito_info.docstring

    # Llamadas transitivas
    llamadas = grafo.llamadas_transitivas
    assert any(origen == "ejecutar_debito" for origen, _ in llamadas)

    # Formateo de texto
    texto_formateado = formatear_contexto_grafo(
        grafo, "bench.dependencias.procesador_pagos"
    )
    assert "DEPENDENCIAS INTERNAS DEL PROYECTO" in texto_formateado
    assert "ejecutar_debito" in texto_formateado
    assert (
        "unittest.mock.patch('bench.dependencias.procesador_pagos.ejecutar_debito'"
        in texto_formateado
    )


def test_construir_grafo_en_endpoint_api() -> None:
    raiz = Path(".")
    grafo = construir_grafo_dependencias(
        raiz,
        "bench/dependencias/api.py",
        "crear_transferencia",
        tipo_objetivo="endpoint",
    )
    nombres_directos = [s.nombre for s in grafo.simbolos_directos]
    assert "procesar_transferencia" in nombres_directos

    texto_formateado = formatear_contexto_grafo(grafo, "bench.dependencias.api")
    assert "Este endpoint invoca funciones y servicios" in texto_formateado
    assert "procesar_transferencia" in texto_formateado
    # Detecta que procesar_transferencia llama internamente a debito y credito
    assert any(dest == "ejecutar_debito" for _, dest in grafo.llamadas_transitivas)


def test_generator_con_grafo_incluye_contexto_en_prompt() -> None:
    cliente = ClienteEspia()
    tracker = TokenTracker()
    contrato = {
        "version": "2",
        "modulo": "bench/dependencias/procesador_pagos.py",
        "huella": "0" * 64,
        "tipo": "funcion",
        "objetivo": "procesar_transferencia",
        "firma": "(cuenta_origen: str, cuenta_destino: str, monto: float) -> dict[str, Any]",
        "critical": False,
        "llama_a": ["ejecutar_debito", "ejecutar_credito"],
        "casos": [
            {
                "id": "caso_1",
                "entrada": {"cuenta_origen": "A", "cuenta_destino": "B", "monto": 50.0},
                "valor_esperado": {"estado": "COMPLETADA"},
                "origen": "docstring",
            }
        ],
    }
    generator = GeneratorAgent(
        cliente,
        tracker,
        ruta_proyecto=Path("."),
    )
    generator.generar(contrato, 1, None)

    assert len(cliente.prompts) == 1
    prompt = cliente.prompts[0]
    assert "DEPENDENCIAS INTERNAS DEL PROYECTO" in prompt
    assert "ejecutar_debito(cuenta: str, monto: float) -> str" in prompt
    assert (
        "unittest.mock.patch('bench.dependencias.procesador_pagos.ejecutar_debito'"
        in prompt
    )


def test_generator_sin_grafo_no_incluye_bloque() -> None:
    cliente = ClienteEspia()
    tracker = TokenTracker()
    contrato = {
        "version": "2",
        "modulo": "bench/dependencias/procesador_pagos.py",
        "huella": "0" * 64,
        "tipo": "funcion",
        "objetivo": "procesar_transferencia",
        "firma": "(cuenta_origen: str, cuenta_destino: str, monto: float) -> dict[str, Any]",
        "critical": False,
        "llama_a": [],
        "casos": [
            {
                "id": "caso_1",
                "entrada": {"cuenta_origen": "A", "cuenta_destino": "B", "monto": 50.0},
                "valor_esperado": {"estado": "COMPLETADA"},
                "origen": "docstring",
            }
        ],
    }
    generator = GeneratorAgent(
        cliente,
        tracker,
        ruta_proyecto=None,
    )
    generator.generar(contrato, 1, None)

    prompt = cliente.prompts[0]
    assert "DEPENDENCIAS INTERNAS DEL PROYECTO" not in prompt
