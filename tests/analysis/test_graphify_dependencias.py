"""Pruebas unitarias para la integración de Graphify + Tree-sitter (SPK #196 / Migración).

Verifica la detección de dependencias inter-archivo, la extracción de firmas con
Tree-sitter, la caché incremental de alta velocidad y la inyección en el Generator.
"""

from __future__ import annotations

import time
from pathlib import Path

from qagent.analysis.graphify_dependencias import (
    analizar_dependencias_con_graphify,
    calcular_hash_directorio,
    formatear_contexto_graphify,
)
from qagent.lenguajes.python_generacion import prompt_generator

RAIZ_REPO = Path(__file__).resolve().parent.parent.parent
RUTA_BENCH = RAIZ_REPO / "bench" / "dependencias"


def test_calcular_hash_directorio_determinista() -> None:
    """Verifica que el hash MD5 de la carpeta sea determinista y no vacío."""
    h1 = calcular_hash_directorio(RUTA_BENCH)
    h2 = calcular_hash_directorio(RUTA_BENCH)
    assert h1 != ""
    assert h1 == h2


def test_analizar_dependencias_funcion_procesar_transferencia() -> None:
    """Comprueba que se detecten las dependencias inter-archivo de procesar_transferencia."""
    deps = analizar_dependencias_con_graphify(
        raiz_proyecto=RAIZ_REPO,
        modulo="bench/dependencias/procesador_pagos.py",
        objetivo="procesar_transferencia",
        tipo_objetivo="funcion",
    )
    assert len(deps) >= 1
    nombres = [d.nombre for d in deps]
    # Debe detectar al menos ejecutar_debito o ejecutar_credito del core bancario
    assert any(
        n in nombres for n in ("ejecutar_debito", "ejecutar_credito", "Transaccion")
    )

    # Verifica que Tree-sitter haya extraído firmas tipadas de las funciones
    funcs = [d for d in deps if d.tipo == "funcion"]
    if funcs:
        assert funcs[0].firma != ""
        assert "(" in funcs[0].firma


def test_analizar_dependencias_endpoint_api() -> None:
    """Comprueba que el endpoint de FastAPI detecte la delegación en procesar_transferencia."""
    deps = analizar_dependencias_con_graphify(
        raiz_proyecto=RAIZ_REPO,
        modulo="bench/dependencias/api.py",
        objetivo="crear_transferencia",
        tipo_objetivo="endpoint",
    )
    assert len(deps) >= 1
    nombres = [d.nombre for d in deps]
    assert "procesar_transferencia" in nombres or "RespuestaTransferencia" in nombres


def test_cache_incremental_alta_velocidad() -> None:
    """Verifica que la consulta subsecuente se resuelva inmediatamente desde caché (< 30 ms)."""
    # Primera llamada (pobla caché)
    analizar_dependencias_con_graphify(
        raiz_proyecto=RAIZ_REPO,
        modulo="bench/dependencias/procesador_pagos.py",
        objetivo="procesar_transferencia",
    )

    # Segunda llamada (debe ser casi instantánea)
    t0 = time.perf_counter()
    deps_rapidas = analizar_dependencias_con_graphify(
        raiz_proyecto=RAIZ_REPO,
        modulo="bench/dependencias/procesador_pagos.py",
        objetivo="procesar_transferencia",
    )
    duracion_ms = (time.perf_counter() - t0) * 1000.0

    assert len(deps_rapidas) >= 1
    assert duracion_ms < 30.0, (
        f"La caché tardó {duracion_ms:.2f} ms (se esperaba < 30 ms)"
    )


def test_formatear_contexto_graphify() -> None:
    """Comprueba el formateo del bloque de dependencias con sugerencias de mock."""
    deps = analizar_dependencias_con_graphify(
        raiz_proyecto=RAIZ_REPO,
        modulo="bench/dependencias/procesador_pagos.py",
        objetivo="procesar_transferencia",
    )
    texto = formatear_contexto_graphify(deps, "bench.dependencias.procesador_pagos")
    assert "DEPENDENCIAS INTERNAS DEL PROYECTO" in texto
    assert "unittest.mock.patch" in texto
    assert "REGLA OBLIGATORIA: Simula las funciones anteriores" in texto


def test_prompt_generator_con_dependencias_incluye_bloque() -> None:
    """Verifica que prompt_generator enriquezca el prompt cuando hay ruta_proyecto y dependencias."""
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

    prompt = prompt_generator(
        contrato, intento=1, feedback=None, ruta_proyecto=RAIZ_REPO
    )
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
    prompt = prompt_generator(
        contrato, intento=1, feedback=None, ruta_proyecto=RAIZ_REPO
    )
    assert "DEPENDENCIAS INTERNAS DEL PROYECTO" in prompt
    assert "procesar_transferencia" in prompt
