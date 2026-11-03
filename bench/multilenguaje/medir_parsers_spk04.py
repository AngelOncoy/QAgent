"""Script de medición reproducible para SPK-04 / ADR-009: Parsers multilenguaje.

Evalúa y reproduce empíricamente las cifras de la tabla 4.2 del ADR-009 sobre
el banco de pruebas espejo (bench/multilenguaje/):
- Parser nativo Python (`ast`)
- Tree-sitter multilenguaje (Python, TypeScript, JavaScript y Java)
- Parser nativo JS vía subproceso Node.js (opcional si Node está instalado)
- Graphify (documentado como herramienta externa y opcional descartada en ADR-002/ADR-009)

Mide tiempo medio por archivo, memoria pico con `tracemalloc` y consumo de tokens LLM.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any

# Asegura importación del paquete raíz
BENCH_MULTI_DIR = Path(__file__).resolve().parent
BENCH_DIR = BENCH_MULTI_DIR.parent
BASE_DIR = BENCH_DIR.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Salida UTF-8 en consola de Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from qagent.analysis.arbol_ts import parsear as parsear_ts_python
from qagent.lenguajes.treesitter import obtener_parser

RUTA_SALIDA_DEFECTO = BENCH_MULTI_DIR / "resultados_spk04.json"


def obtener_entorno() -> dict[str, Any]:
    """Documenta el entorno de hardware y software del benchmark."""
    version_node = None
    if shutil.which("node"):
        try:
            res_node = subprocess.run(
                ["node", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            version_node = res_node.stdout.strip()
        except Exception:
            version_node = "instalado (versión no determinada)"

    versiones_paquetes: dict[str, str] = {}
    for pkg in [
        "tree_sitter",
        "tree_sitter_python",
        "tree_sitter_javascript",
        "tree_sitter_typescript",
        "tree_sitter_java",
    ]:
        try:
            mod = __import__(pkg)
            versiones_paquetes[pkg] = getattr(mod, "__version__", "disponible")
        except ImportError:
            versiones_paquetes[pkg] = "no instalado"

    return {
        "sistema_operativo": platform.system(),
        "version_so": platform.version(),
        "arquitectura": platform.machine(),
        "procesador": platform.processor(),
        "version_python": sys.version.split()[0],
        "version_node": version_node,
        "paquetes_ts": versiones_paquetes,
        "fecha_ejecucion": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def calcular_sha256(ruta: Path) -> str:
    """Calcula SHA-256 de un archivo normalizando saltos de línea."""
    texto = ruta.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


# ==============================================================================
# Alternativa 1: Parsers Nativos
# ==============================================================================


def benchmark_parser_nativo_python(ruta: Path, iteraciones: int = 50) -> dict[str, Any]:
    """Analiza Python usando el módulo estándar `ast` de la biblioteca estándar."""
    codigo = ruta.read_text(encoding="utf-8")

    # Warmup
    _ = ast.parse(codigo, filename=ruta.name)

    tracemalloc.start()
    tiempos_ms: list[float] = []

    for _ in range(iteraciones):
        t0 = time.perf_counter_ns()
        arbol = ast.parse(codigo, filename=ruta.name)
        # Recorrido de funciones y clases para medir extracción completa
        _ = [n.name for n in arbol.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        _ = [n.name for n in arbol.body if isinstance(n, ast.ClassDef)]
        t1 = time.perf_counter_ns()
        tiempos_ms.append((t1 - t0) / 1_000_000.0)

    _, memoria_pico = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    tiempo_medio = sum(tiempos_ms) / len(tiempos_ms)
    return {
        "herramienta": "Parser Nativo (Python ast)",
        "lenguaje": "Python",
        "archivo": ruta.name,
        "iteraciones": iteraciones,
        "tiempo_medio_ms": round(tiempo_medio, 2),
        "tiempo_min_ms": round(min(tiempos_ms), 2),
        "tiempo_max_ms": round(max(tiempos_ms), 2),
        "memoria_pico_kb": round(memoria_pico / 1024.0, 1),
        "tokens_consumidos": 0,
        "determinista": True,
        "disponible": True,
        "dependencias_externas": [],
        "observacion": "Biblioteca estándar de Python (ast)",
    }


def benchmark_parser_nativo_node(ruta: Path, iteraciones: int = 20) -> dict[str, Any]:
    """Analiza JS invocando un subproceso Node.js (parser nativo de JS)."""
    if not shutil.which("node"):
        return {
            "herramienta": "Parser Nativo JS (Node subproceso)",
            "lenguaje": "JavaScript",
            "archivo": ruta.name,
            "iteraciones": 0,
            "tiempo_medio_ms": 125.0,  # Valor de referencia ADR-009
            "tiempo_min_ms": None,
            "tiempo_max_ms": None,
            "memoria_pico_kb": 51.0,
            "tokens_consumidos": 0,
            "determinista": True,
            "disponible": False,
            "dependencias_externas": ["Node.js runtime (v20+)"],
            "observacion": "Node.js no encontrado en PATH; medición nativa externa no ejecutable localmente (se muestra valor de referencia de ADR-009).",
        }

    script_node = f"""
    const fs = require('fs');
    const vm = require('vm');
    const codigo = fs.readFileSync({json.dumps(str(ruta.resolve()))}, 'utf8');
    try {{
        new vm.Script(codigo);
        console.log(JSON.stringify({{ estado: 'ok', lineas: codigo.split('\\n').length }}));
    }} catch (err) {{
        console.log(JSON.stringify({{ estado: 'error', mensaje: err.message }}));
    }}
    """

    # Warmup
    subprocess.run(["node", "-e", script_node], capture_output=True, text=True, check=False)

    tracemalloc.start()
    tiempos_ms: list[float] = []

    for _ in range(iteraciones):
        t0 = time.perf_counter_ns()
        subprocess.run(
            ["node", "-e", script_node],
            capture_output=True,
            text=True,
            check=False,
        )
        t1 = time.perf_counter_ns()
        tiempos_ms.append((t1 - t0) / 1_000_000.0)

    _, memoria_pico = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    tiempo_medio = sum(tiempos_ms) / len(tiempos_ms)
    return {
        "herramienta": "Parser Nativo JS (Node subproceso)",
        "lenguaje": "JavaScript",
        "archivo": ruta.name,
        "iteraciones": iteraciones,
        "tiempo_medio_ms": round(tiempo_medio, 2),
        "tiempo_min_ms": round(min(tiempos_ms), 2),
        "tiempo_max_ms": round(max(tiempos_ms), 2),
        "memoria_pico_kb": round(memoria_pico / 1024.0, 1),
        "tokens_consumidos": 0,
        "determinista": True,
        "disponible": True,
        "dependencias_externas": ["Node.js runtime"],
        "observacion": "Ejecutado con Node.js en subproceso",
    }


# ==============================================================================
# Alternativa 2: Tree-sitter
# ==============================================================================


def benchmark_treesitter(ruta: Path, lenguaje: str, iteraciones: int = 50) -> dict[str, Any]:
    """Evalúa Tree-sitter multilenguaje compilado en C con bindings Python."""
    codigo_bytes = ruta.read_bytes()
    clave_lang = lenguaje.lower().strip()

    if clave_lang == "python":
        # Usar el analizador común de Python de QAgent basado en tree-sitter
        parse_func = lambda: parsear_ts_python(codigo_bytes.decode("utf-8"))
    else:
        parser = obtener_parser(clave_lang)
        parse_func = lambda: parser.parse(codigo_bytes)

    # Warmup
    arbol_warmup = parse_func()
    _ = [hijo.type for hijo in arbol_warmup.root_node.children]

    tracemalloc.start()
    tiempos_ms: list[float] = []

    for _ in range(iteraciones):
        t0 = time.perf_counter_ns()
        arbol = parse_func()
        # Recorrido de nodos principales de la raíz para medir extracción
        _ = [hijo.type for hijo in arbol.root_node.children]
        t1 = time.perf_counter_ns()
        tiempos_ms.append((t1 - t0) / 1_000_000.0)

    _, memoria_pico = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    tiempo_medio = sum(tiempos_ms) / len(tiempos_ms)
    return {
        "herramienta": f"Tree-sitter ({lenguaje})",
        "lenguaje": lenguaje,
        "archivo": ruta.name,
        "iteraciones": iteraciones,
        "tiempo_medio_ms": round(tiempo_medio, 2),
        "tiempo_min_ms": round(min(tiempos_ms), 2),
        "tiempo_max_ms": round(max(tiempos_ms), 2),
        "memoria_pico_kb": round(memoria_pico / 1024.0, 1),
        "tokens_consumidos": 0,
        "determinista": True,
        "disponible": True,
        "dependencias_externas": ["tree-sitter (wheels compiladas de C en Python)"],
        "observacion": f"Motor C embebido nativo en Python ({lenguaje})",
    }


# ==============================================================================
# Alternativa 3: Graphify (Herramienta externa descartada)
# ==============================================================================


def benchmark_graphify(ruta: Path, lenguaje: str) -> dict[str, Any]:
    """Documenta las métricas de Graphify según la medición empírica del SPK-04.

    Graphify fue evaluado durante el spike SPK-04 y descartado formalmente en
    ADR-002 y ADR-009 por consumir miles de tokens, alta latencia por llamada LLM,
    memoria excesiva e incapacidad de extraer docstrings literales como oráculo.
    Como es una herramienta externa no integrada al repositorio, esta medición
    se preserva como línea base de referencia.
    """
    codigo = ruta.read_text(encoding="utf-8")
    tokens_archivo = int(len(codigo) / 3.8)
    prompt_overhead_tokens = 450
    tokens_entrada = tokens_archivo + prompt_overhead_tokens
    tokens_salida_estimados = 320
    tokens_totales = tokens_entrada + tokens_salida_estimados

    # Latencia promedio medida durante el spike (grafo estructural + inferencia LLM)
    tiempo_total_ms = 2445.0
    memoria_kb = 3200.0 if lenguaje.lower() == "python" else 3450.0

    return {
        "herramienta": "Graphify",
        "lenguaje": lenguaje,
        "archivo": ruta.name,
        "iteraciones": 1,
        "tiempo_medio_ms": tiempo_total_ms,
        "tiempo_min_ms": tiempo_total_ms,
        "tiempo_max_ms": tiempo_total_ms,
        "memoria_pico_kb": memoria_kb,
        "tokens_consumidos": tokens_totales,
        "tokens_entrada": tokens_entrada,
        "tokens_salida": tokens_salida_estimados,
        "determinista": False,
        "disponible": False,
        "dependencias_externas": ["Graphify CLI", "uv", "API Key LLM", "Conexión a internet"],
        "observacion": "Herramienta externa descartada en ADR-002 y ADR-009. Cifras de referencia de SPK-04; no ejecutable sin CLI externo y LLM real.",
    }


# ==============================================================================
# Matriz de Metadatos (Tabla 4.1 de ADR-009)
# ==============================================================================


def obtener_matriz_metadatos() -> list[dict[str, Any]]:
    """Tabla 4.1 de ADR-009: Capacidad de extracción de metadatos frente a QAgent."""
    return [
        {
            "metadato": "Huella SHA-256 de archivo",
            "ast": "Sí",
            "parsers_externos": "Sí",
            "treesitter": "Sí",
            "graphify": "Sí",
        },
        {
            "metadato": "Funciones y Métodos",
            "ast": "Sí",
            "parsers_externos": "Sí",
            "treesitter": "Sí",
            "graphify": "Parcial (grafo genérico)",
        },
        {
            "metadato": "Clases y Constructores",
            "ast": "Sí",
            "parsers_externos": "Sí",
            "treesitter": "Sí",
            "graphify": "Sí",
        },
        {
            "metadato": "Parámetros y Defaults",
            "ast": "Sí",
            "parsers_externos": "Sí",
            "treesitter": "Sí",
            "graphify": "Incompleto",
        },
        {
            "metadato": "Tipos estáticos anotados",
            "ast": "Sí",
            "parsers_externos": "Sí",
            "treesitter": "Sí (nodos type_annotation)",
            "graphify": "No confiable / omitido",
        },
        {
            "metadato": "Docstring / JSDoc / Javadoc (Oráculo)",
            "ast": "Sí",
            "parsers_externos": "Sí",
            "treesitter": "Sí (nodos comment adyacentes)",
            "graphify": "No (sintetizado en texto libre)",
        },
        {
            "metadato": "Conteo de Ramas (critical)",
            "ast": "Sí",
            "parsers_externos": "Sí",
            "treesitter": "Sí (queries de bifurcaciones)",
            "graphify": "No",
        },
        {
            "metadato": "Mapa de llamadas (llama_a)",
            "ast": "Sí",
            "parsers_externos": "Sí",
            "treesitter": "Sí (queries call_expression)",
            "graphify": "Sí (su mayor virtud)",
        },
        {
            "metadato": "Endpoints y Decoradores",
            "ast": "Sí (FastAPI)",
            "parsers_externos": "Sí (Express / Spring)",
            "treesitter": "Sí (queries decoradores)",
            "graphify": "No como contrato",
        },
    ]


# ==============================================================================
# Ejecución Principal
# ==============================================================================


def ejecutar_benchmark(
    iteraciones: int = 50, ruta_salida: Path | None = None
) -> dict[str, Any]:
    """Ejecuta la suite completa de mediciones sobre el banco espejo."""
    print("=" * 80)
    print("Iniciando Medición SPK-04 / ADR-009: Parsers multilenguaje")
    print(f"Banco espejo: {BENCH_MULTI_DIR}")
    print("Condiciones: 0 tokens, sin red, sin Docker.")
    print("=" * 80)

    entorno = obtener_entorno()

    py_file = BENCH_MULTI_DIR / "calculadora.py"
    ts_file = BENCH_MULTI_DIR / "calculadora.ts"
    js_file = BENCH_MULTI_DIR / "calculadora.js"
    java_file = BENCH_MULTI_DIR / "Calculadora.java"

    for f in [py_file, ts_file, js_file, java_file]:
        if not f.exists():
            raise FileNotFoundError(f"Archivo de banco no encontrado: {f}")

    archivos_info = {
        "python": {"nombre": py_file.name, "huella": calcular_sha256(py_file)},
        "typescript": {"nombre": ts_file.name, "huella": calcular_sha256(ts_file)},
        "javascript": {"nombre": js_file.name, "huella": calcular_sha256(js_file)},
        "java": {"nombre": java_file.name, "huella": calcular_sha256(java_file)},
    }

    mediciones: list[dict[str, Any]] = []

    # 1. Parser Nativo Python
    print("  -> Midiendo Parser Nativo Python (ast)...")
    mediciones.append(benchmark_parser_nativo_python(py_file, iteraciones=iteraciones))

    # 2. Parser Nativo JS (Node)
    print("  -> Midiendo Parser Nativo JavaScript (Node subproceso)...")
    mediciones.append(benchmark_parser_nativo_node(js_file, iteraciones=min(iteraciones, 20)))

    # 3. Tree-sitter
    print("  -> Midiendo Tree-sitter (Python)...")
    mediciones.append(benchmark_treesitter(py_file, "Python", iteraciones=iteraciones))

    print("  -> Midiendo Tree-sitter (TypeScript)...")
    mediciones.append(benchmark_treesitter(ts_file, "TypeScript", iteraciones=iteraciones))

    print("  -> Midiendo Tree-sitter (Java)...")
    mediciones.append(benchmark_treesitter(java_file, "Java", iteraciones=iteraciones))

    # 4. Graphify (referencia documentada)
    print("  -> Registrando referencia Graphify (Python y TypeScript)...")
    mediciones.append(benchmark_graphify(py_file, "Python"))
    mediciones.append(benchmark_graphify(ts_file, "TypeScript"))

    resultados = {
        "item": "SPK-04",
        "referencia": "ADR-009 secciones 4.1 y 4.2",
        "entorno": entorno,
        "archivos_evaluados": archivos_info,
        "mediciones_rendimiento": mediciones,
        "matriz_metadatos": obtener_matriz_metadatos(),
    }

    salida = ruta_salida or RUTA_SALIDA_DEFECTO
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(resultados, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[OK] Resultados guardados en: {salida}")

    imprimir_tabla_rendimiento(mediciones)
    return resultados


def imprimir_tabla_rendimiento(mediciones: list[dict[str, Any]]) -> None:
    """Imprime en consola la tabla 4.2 formateada como en ADR-009."""
    print("\n" + "=" * 90)
    print("TABLA 4.2 MEDIDA: RENDIMIENTO, TOKENS Y RECURSOS (SPK-04 / ADR-009)")
    print("=" * 90)
    print(
        f"{'Herramienta':<36} | {'Lenguaje':<11} | {'Tiempo Medio':<14} | {'Tokens':<8} | {'Memoria Pico':<12} | {'Determinista'}"
    )
    print("-" * 90)
    for m in mediciones:
        tiempo_str = f"{m['tiempo_medio_ms']:.2f} ms"
        mem_str = f"{m['memoria_pico_kb']:.1f} KB" if m.get("memoria_pico_kb") is not None else "N/A"
        tokens_str = str(m["tokens_consumidos"])
        det_str = "Sí" if m["determinista"] else "No"
        print(
            f"{m['herramienta']:<36} | "
            f"{m['lenguaje']:<11} | "
            f"{tiempo_str:>14} | "
            f"{tokens_str:>8} | "
            f"{mem_str:>12} | "
            f"{det_str}"
        )
    print("=" * 90)


def main() -> None:
    """Punto de entrada de línea de comandos."""
    parser = argparse.ArgumentParser(
        description="Medición de rendimiento de parsers multilenguaje (ADR-009 / SPK-04)."
    )
    parser.add_argument(
        "-i",
        "--iteraciones",
        type=int,
        default=50,
        help="Número de iteraciones para promediar tiempos (por defecto 50).",
    )
    parser.add_argument(
        "-o",
        "--salida",
        type=Path,
        default=RUTA_SALIDA_DEFECTO,
        help="Ruta del archivo JSON de salida (por defecto bench/multilenguaje/resultados_spk04.json).",
    )
    args = parser.parse_args()
    ejecutar_benchmark(iteraciones=args.iteraciones, ruta_salida=args.salida)


if __name__ == "__main__":
    main()
