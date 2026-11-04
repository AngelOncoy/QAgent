"""Pruebas unitarias para el grafo de imports tree-sitter (SPK #196, ADR-012)."""

from __future__ import annotations

from pathlib import Path

import pytest

from qagent.agents.generator import GeneratorAgent
from qagent.analysis.grafo_imports import (
    construir_grafo_dependencias,
    formatear_contexto_grafo,
    parsear_archivo,
)
from qagent.lenguajes.python_generacion import prompt_generator
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


def test_prompt_generator_con_dependencias_incluye_bloque() -> None:
    """Verifica que prompt_generator enriquezca el prompt cuando hay ruta_proyecto y dependencias."""
    raiz = Path(__file__).resolve().parent.parent.parent
    contrato = {
        "modulo": "bench/dependencias/procesador_pagos.py",
        "objetivo": "procesar_transferencia",
        "tipo": "funcion",
        "lenguaje": "python",
        "framework": "pytest",
        "casos": [
            {
                "id": "c1",
                "descripcion": "transferencia valida",
                "entrada": {"origen": "A", "destino": "B", "monto": 50.0},
                "valor_esperado": {"estado": "completada"},
            }
        ],
    }

    prompt = prompt_generator(contrato, intento=1, feedback=None, ruta_proyecto=raiz)
    assert "DEPENDENCIAS INTERNAS DEL PROYECTO" in prompt
    assert "unittest.mock.patch" in prompt


def test_prompt_generator_sin_ruta_proyecto_no_incluye_bloque() -> None:
    """Verifica que sin ruta_proyecto el prompt no incluya el bloque para ahorrar tokens."""
    contrato = {
        "modulo": "bench/dependencias/procesador_pagos.py",
        "objetivo": "procesar_transferencia",
        "tipo": "funcion",
        "lenguaje": "python",
        "framework": "pytest",
        "casos": [],
    }

    prompt = prompt_generator(contrato, intento=1, feedback=None, ruta_proyecto=None)
    assert "DEPENDENCIAS INTERNAS DEL PROYECTO" not in prompt


def test_prompt_generator_endpoint_con_manejador() -> None:
    """Verifica que un contrato de endpoint con manejador resuelva dependencias inter-archivo."""
    raiz = Path(__file__).resolve().parent.parent.parent
    contrato = {
        "modulo": "bench/dependencias/api.py",
        "tipo": "endpoint",
        "objetivo": "POST /transferencias",
        "manejador": "crear_transferencia",
        "aplicacion": "app",
        "lenguaje": "python",
        "framework": "pytest",
        "casos": [],
    }
    prompt = prompt_generator(contrato, intento=1, feedback=None, ruta_proyecto=raiz)
    assert "DEPENDENCIAS INTERNAS DEL PROYECTO" in prompt
    assert "procesar_transferencia" in prompt


def test_graphify_exe_en_proyecto_no_se_ejecuta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Confirma que un .venv/Scripts/graphify.exe dentro del proyecto analizado nunca se ejecuta."""
    scripts_dir = tmp_path / ".venv" / "Scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    fake_exe = scripts_dir / "graphify.exe"
    fake_exe.write_bytes(b"echo NO EJECUTAR")

    # Módulo a analizar con dependencia
    dep_file = tmp_path / "servicio.py"
    dep_file.write_text("def consultar() -> str:\n    return 'ok'\n", encoding="utf-8")
    mod_file = tmp_path / "modulo.py"
    mod_file.write_text(
        "from servicio import consultar\n\ndef tarea():\n    return consultar()\n",
        encoding="utf-8",
    )

    import subprocess

    def no_subproceso(*args, **kwargs):
        raise AssertionError("Se intentó ejecutar un subproceso fuera del sandbox!")

    monkeypatch.setattr(subprocess, "run", no_subproceso)
    monkeypatch.setattr(subprocess, "Popen", no_subproceso)

    contrato = {
        "modulo": "modulo.py",
        "objetivo": "tarea",
        "tipo": "funcion",
        "lenguaje": "python",
        "framework": "pytest",
        "casos": [],
    }

    # prompt_generator y construir_grafo_dependencias deben funcionar sin subprocesos
    prompt = prompt_generator(
        contrato, intento=1, feedback=None, ruta_proyecto=tmp_path
    )
    assert "DEPENDENCIAS INTERNAS DEL PROYECTO" in prompt
    assert "consultar" in prompt
