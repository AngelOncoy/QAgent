"""Benchmark estático reproducible: no importa ni ejecuta las fuentes fixture."""

import argparse
import contextlib
import hashlib
import json
import tempfile
import time
import tracemalloc
from pathlib import Path

from qagent.lenguajes import (
    JavaAdapter,
    java,
    java_generacion,
    java_revision,
    treesitter,
)

argumentos = argparse.ArgumentParser(description=__doc__)
argumentos.add_argument("etiqueta", choices=["antes", "despues", "medicion"])
argumentos.add_argument("--salida", type=Path, required=True)
opciones = argumentos.parse_args()
base = opciones.salida.resolve()
base.mkdir(parents=True, exist_ok=True)
etiqueta = opciones.etiqueta
contador = {"parseos": 0, "declaraciones": 0}
parser_original = treesitter.obtener_parser
declaraciones_original = java._declaraciones


class ParserContado:
    def __init__(self, lenguaje):
        self.parser = parser_original(lenguaje)

    def parse(self, *a, **k):
        contador["parseos"] += 1
        return self.parser.parse(*a, **k)


def declaraciones(*a, **k):
    contador["declaraciones"] += 1
    return declaraciones_original(*a, **k)


java._declaraciones = declaraciones
for modulo in (java, java_generacion, java_revision):
    modulo.obtener_parser = ParserContado
try:
    from qagent.lenguajes import java_sesion

    java_sesion.obtener_parser = ParserContado
except ImportError:
    pass

with tempfile.TemporaryDirectory(prefix="qagent-medicion-308-") as temporal:
    raiz = Path(temporal)
    carpeta = raiz / "src/main/java/ejemplo"
    carpeta.mkdir(parents=True)
    for i in range(12):
        metodos = "\n".join(
            f"/** Devuelve dos veces x. */ public static int f{j}(int x) {{ return x * 2; }}"
            for j in range(8)
        )
        (carpeta / f"Banco{i}.java").write_text(
            f"package ejemplo; public class Banco{i} {{\n{metodos}\n}}\n",
            encoding="utf-8",
        )
    adaptador = JavaAdapter()
    sesion = (
        adaptador.recursos_corrida(raiz)
        if hasattr(adaptador, "recursos_corrida")
        else contextlib.nullcontext()
    )
    salidas, tiempos = [], {}
    tracemalloc.start()
    inicio = time.perf_counter()
    with sesion as recursos:
        t = time.perf_counter()
        analisis = adaptador.analizar(raiz)
        tiempos["analisis_s"] = time.perf_counter() - t
        for modulo in analisis["modulos"]:
            for f in modulo["funciones"]:
                contrato = {
                    "modulo": modulo["ruta"],
                    "objetivo": f["nombre"],
                    "firma": f["firma"],
                }
                t = time.perf_counter()
                contextos = [
                    java_generacion.contexto_java(contrato, raiz) for _ in range(3)
                ]
                tiempos["contexto_s"] = (
                    tiempos.get("contexto_s", 0) + time.perf_counter() - t
                )
                t = time.perf_counter()
                rango = java_revision.ReglasRevisionJava().rango_de_objetivo(
                    raiz, modulo["ruta"], f["nombre"]
                )
                tiempos["rangos_s"] = (
                    tiempos.get("rangos_s", 0) + time.perf_counter() - t
                )
                salidas.append((f["nombre"], contextos, rango))
            t = time.perf_counter()
            salidas.append(
                adaptador.huellas_de_archivo(
                    (raiz / modulo["ruta"]).read_text(encoding="utf-8"), modulo["ruta"]
                )
            )
            tiempos["huellas_s"] = tiempos.get("huellas_s", 0) + time.perf_counter() - t
    detalle_recursos = recursos.resumen() if recursos is not None else None
    duracion = time.perf_counter() - inicio
    _, pico = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    salida = {
        "revision": __import__("subprocess")
        .check_output(["git", "rev-parse", "HEAD"], text=True)
        .strip(),
        "archivos": 12,
        "objetivos": 96,
        **contador,
        "tiempos": tiempos,
        "duracion_s": duracion,
        "pico_python_tracemalloc_bytes": pico,
        "rss_host_bytes": None,
        "cpu_docker": None,
        "memoria_docker_bytes": None,
        "copias_proyecto": 0,
        "compilaciones": 0,
        "alcance": "solo análisis estático; Docker y fuentes no ejecutados; pico incluye solo asignaciones Python rastreadas",
        "sha256_resultados": hashlib.sha256(
            json.dumps(salidas, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest(),
        "recursos": detalle_recursos,
    }
    (base / f"estatico-{etiqueta}.json").write_text(
        json.dumps(salida, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(salida, ensure_ascii=True), flush=True)
