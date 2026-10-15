"""Graba las salidas de pytest del banco de pruebas para repetirlas sin Docker (EN-17).

Corre la corrida completa de `bench/` con la IA simulada y, en lugar del sandbox Docker,
ejecuta cada test generado con pytest **en esta misma máquina**, con cobertura de líneas
medida con `sys.settrace`. Guarda el resultado en
`tests/orchestrator/grabaciones/bench_ejecuciones.json`, indexado por el hash del test.

Es una herramienta de desarrollo y solo acepta la carpeta `bench/` del repositorio: el
código del banco es propio y los tests salen de la IA simulada. Nunca se debe apuntar a
un proyecto de un usuario (esas pruebas solo corren en el sandbox).

Uso:
    python scripts/grabar_ejecuciones.py            # regraba las ejecuciones del banco
    python scripts/grabar_ejecuciones.py --informes docs/evidencias/en-17/demo
        # además exporta el informe de la corrida en PDF, Markdown, HTML y JSON
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "src"))

BANCO = RAIZ / "bench"
SALIDA = RAIZ / "tests" / "orchestrator" / "grabaciones" / "bench_ejecuciones.json"
IMAGEN = "grabacion-local (sin Docker)"

#: Corre pytest con un medidor de líneas ejecutadas (stdlib) y deja `coverage.json`.
RUNNER = r"""
import json, pathlib, sys
proyecto, tests, junit, cov_out, modulos, con_cobertura = sys.argv[1:7]
sys.path.insert(0, proyecto)
objetivos = {str(pathlib.Path(proyecto, m).resolve()): m for m in modulos.split(",")}
ejecutadas = {ruta: set() for ruta in objetivos}

def tracer(frame, event, arg):
    ruta = str(pathlib.Path(frame.f_code.co_filename).resolve())
    if ruta not in ejecutadas:
        return None
    def local(f, e, a):
        if e == "line":
            ejecutadas[ruta].add(f.f_lineno)
        return local
    return local

if con_cobertura == "1":
    sys.settrace(tracer)
import pytest
codigo = pytest.main([tests, f"--junitxml={junit}", "-p", "no:cacheprovider"])
sys.settrace(None)
if con_cobertura != "1":
    sys.exit(int(codigo))

def ejecutables(ruta):
    codigo_fuente = compile(pathlib.Path(ruta).read_text(encoding="utf-8"), ruta, "exec")
    lineas = set()
    def recorrer(c):
        for _, _, linea in c.co_lines():
            if linea:
                lineas.add(linea)
        for k in c.co_consts:
            if hasattr(k, "co_lines"):
                recorrer(k)
    recorrer(codigo_fuente)
    return lineas

files, total_e, total_m = {}, 0, 0
for ruta, nombre in objetivos.items():
    todas = ejecutables(ruta)
    hechas = ejecutadas[ruta] & todas
    faltan = sorted(todas - hechas)
    files[nombre] = {"executed_lines": sorted(hechas), "missing_lines": faltan,
                     "executed_branches": [], "missing_branches": []}
    total_e += len(hechas); total_m += len(faltan)
pct = 100.0 * total_e / max(1, total_e + total_m)
json.dump({"files": files, "totals": {"percent_covered": round(pct, 2),
           "num_branches": 0, "covered_branches": 0}}, open(cov_out, "w"))
sys.exit(int(codigo))
"""


def _normalizar(texto: str, temporal: Path) -> str:
    """Quita rutas y nombre de esta máquina: lo grabado habla de `/work/...`."""
    for variante in {str(temporal), str(temporal.resolve()), temporal.as_posix()}:
        texto = texto.replace(variante, "/work")
    texto = re.sub(r'hostname="[^"]*"', 'hostname="sandbox"', texto)
    return texto.replace("\\", "/")


class GrabadorLocal:
    """Ejecutor que reemplaza a Docker: pytest local sobre una copia del banco."""

    def __init__(self) -> None:
        self.grabaciones: dict[str, dict] = {}

    def __call__(self, imagen, ruta_proyecto, ruta_tests, modulo_cov):
        from qagent.sandbox import ResultadoSandbox
        from tests.orchestrator.ejecutor_grabado import clave

        codigo = (Path(ruta_tests) / "test_generado.py").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory(prefix="qagent-grabacion-") as t:
            temporal = Path(t)
            proyecto = temporal / "proyecto"
            shutil.copytree(
                ruta_proyecto,
                proyecto,
                ignore=shutil.ignore_patterns(".qagent", ".git", "__pycache__"),
            )
            shutil.copytree(ruta_tests, temporal / "tests")
            modulos = ",".join(p.name for p in proyecto.glob("*.py"))
            junit, cobertura = temporal / "junit.xml", temporal / "coverage.json"

            def pasada(
                con_cobertura: bool,
            ) -> tuple[subprocess.CompletedProcess, float]:
                inicio = time.monotonic()
                r = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        RUNNER,
                        str(proyecto),
                        str(temporal / "tests"),
                        str(junit),
                        str(cobertura),
                        modulos,
                        "1" if con_cobertura else "0",
                    ],
                    cwd=proyecto,
                    capture_output=True,
                    text=True,
                    timeout=300,
                    check=False,
                )
                return r, round(time.monotonic() - inicio, 3)

            r, duracion = pasada(False)  # lo que se guarda: salida y tiempos reales
            junit_texto = junit.read_text(encoding="utf-8") if junit.is_file() else None
            pasada(True)  # solo para medir la cobertura de líneas
            grabado = {
                "exit_code": r.returncode,
                "stdout": _normalizar(r.stdout, temporal),
                "stderr": _normalizar(r.stderr, temporal),
                "coverage": json.loads(cobertura.read_text(encoding="utf-8"))
                if cobertura.is_file()
                else None,
                "timed_out": False,
                "oom_killed": False,
                "duracion_s": duracion,
                "junit_xml": _normalizar(junit_texto, temporal)
                if junit_texto
                else None,
                # Lo que se ejecutó de verdad aquí: pytest local, sin plugin de
                # cobertura (la cobertura de líneas se mide aparte con sys.settrace).
                "comando": [
                    "python",
                    "-m",
                    "pytest",
                    "/work/tests",
                    "--junitxml=/work/junit.xml",
                    "-p",
                    "no:cacheprovider",
                ],
            }
        self.grabaciones[clave(codigo)] = grabado
        return ResultadoSandbox(**grabado)


def correr_banco(carpeta: Path, ejecutor, al_evento=None):
    """Corrida completa del banco con la IA simulada y el ejecutor indicado."""
    from qagent.almacenamiento import AlmacenProyecto
    from qagent.config import cargar_configuracion
    from qagent.config.carga import RUTA_CONFIG
    from qagent.orchestrator.corrida import ejecutar_corrida

    config = cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config
    almacen = AlmacenProyecto(carpeta)
    almacen.inicializar()
    run_id = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
    resumen = ejecutar_corrida(
        carpeta,
        "deep",
        config,
        None,
        simulado=True,
        al_evento=al_evento,
        run_id=run_id,
        preparar_imagen=lambda ruta: IMAGEN,
        ejecutor=ejecutor,
    )
    return resumen, almacen


def copiar_banco(destino: Path) -> Path:
    shutil.copytree(BANCO, destino, ignore=shutil.ignore_patterns("*.md", "*.json"))
    return destino


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--informes", type=Path, help="carpeta donde exportar el informe")
    args = ap.parse_args()

    # El informe guarda la ruta del proyecto: en una carpeta pública no lleva el nombre
    # de usuario de quien grabó (si no hay carpeta pública, se usa la temporal).
    publica = os.environ.get("PUBLIC")
    with tempfile.TemporaryDirectory(
        prefix="qagent-banco-",
        dir=publica if publica and Path(publica).is_dir() else None,
    ) as t:
        carpeta = copiar_banco(Path(t) / "banco")
        grabador = GrabadorLocal()
        resumen, almacen = correr_banco(carpeta, grabador)
        print(
            f"Corrida {resumen.estado}: {resumen.aceptadas} aceptadas, "
            f"{resumen.bugs_detectados} bugs, {resumen.estancadas} estancadas"
        )
        SALIDA.parent.mkdir(parents=True, exist_ok=True)
        SALIDA.write_text(
            json.dumps(
                grabador.grabaciones, indent=1, ensure_ascii=False, sort_keys=True
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"{len(grabador.grabaciones)} ejecuciones grabadas en {SALIDA}")
        if args.informes:
            from qagent.storage.exportar_informe import exportar_informe

            args.informes.mkdir(parents=True, exist_ok=True)
            for formato in ("pdf", "md", "html", "json"):
                r = exportar_informe(
                    carpeta,
                    run_id=resumen.run_id,
                    formato=formato,
                    opciones={"detalle": True, "trazas": True, "codigo": True},
                    carpeta_destino=args.informes,
                )
                print(f"  {formato}: {r['ruta']}")
            detalle = almacen.carpeta_run(resumen.run_id) / "detalle.json"
            shutil.copy(detalle, args.informes / "detalle.json")
            # Lo que recibe la pantalla del Reporte (sirve para capturarla sin Docker).
            from qagent.storage.vista_ejecucion import leer_results
            from qagent.storage.vista_reporte import leer_detalle, vista_reporte

            results = leer_results(carpeta, resumen.run_id)
            vista = vista_reporte(results, leer_detalle(carpeta, resumen.run_id))
            (args.informes / "vista_reporte.json").write_text(
                json.dumps({**vista, "ok": True}, indent=1, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
