"""Matriz reproducible de compatibilidad Java con proyectos externos (#309).

    python scripts/matriz_java.py --nivel pr --salida C:/ruta/evidencias
    python scripts/matriz_java.py --nivel ampliada --salida C:/ruta/evidencias
    python scripts/matriz_java.py --fila gs-maven --fila gs-maven-defecto --salida ...
    python scripts/matriz_java.py --listar

Necesita Docker y red (para descargar los commits fijados y preparar las imágenes).
Usa la IA grabada de `tests/compatibilidad_java/` (0 tokens, sin claves) y ejecuta
Maven/JUnit solo en Docker sin red. Deja `matriz.json`, `matriz.md` y una carpeta
por fila en `--salida`, también si alguna fila falla. Devuelve 0 solo si cada fila
terminó como `aprobado` o `no_admitido_confirmado`. Al terminar borra las imágenes
derivadas que creó, salvo con `--conservar-imagenes`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
os.environ["QAGENT_FAKE_LLM"] = "1"
os.environ.pop("PYAGENT_FAKE_LLM", None)

from tests import soporte_docker
from tests.compatibilidad_java import ejecutar, matriz


def _tabla(resultados: list[dict]) -> str:
    """Resumen Markdown de la matriz para el resumen del workflow o un informe."""
    lineas = [
        "| Fila | Tipo | Nivel | Soporte | Configuraciones | Commit | Resultado | Duración |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in resultados:
        commit = (r.get("commit") or "")[:12] or "—"
        lineas.append(
            f"| {r['id']} | {r['tipo']} | {r['nivel']} | {r['soporte']} | "
            f"{', '.join(r['configuraciones'])} | `{commit}` | **{r['resultado']}** | "
            f"{r.get('duracion_s', 0)} s |"
        )
    detalles = [
        f"- **{r['id']}**: " + "; ".join(r["diferencias"])
        for r in resultados
        if r.get("diferencias")
    ]
    if detalles:
        lineas += ["", "Diferencias y fallos:", "", *detalles]
    return "\n".join(lineas) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Ejecuta las filas elegidas y escribe su informe."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--nivel", choices=matriz.NIVELES, default="pr")
    parser.add_argument("--fila", action="append", help="ejecuta solo esta fila")
    parser.add_argument("--salida", type=Path, help="carpeta nueva de evidencia")
    parser.add_argument("--cache", type=Path, help="caché de los commits descargados")
    parser.add_argument(
        "--presupuesto-min",
        type=float,
        default=None,
        help="no inicia filas nuevas pasado este tiempo (quedan no_ejecutado)",
    )
    parser.add_argument("--conservar-imagenes", action="store_true")
    parser.add_argument("--listar", action="store_true", help="solo lista las filas")
    args = parser.parse_args(argv)

    filas = matriz.seleccionar(matriz.cargar(), args.nivel, args.fila)
    if args.listar:
        for fila in filas:
            print(f"{fila.id:32} {fila.tipo:8} {fila.nivel:9} {fila.soporte}")
        return 0
    if args.salida is None:
        parser.error("--salida es obligatoria para ejecutar")
    salida = args.salida.resolve()
    salida.mkdir(parents=True, exist_ok=True)
    cache = (args.cache or salida / "_fuentes").resolve()
    cache.mkdir(parents=True, exist_ok=True)

    from qagent.sandbox import obtener_cliente
    from qagent.sandbox.imagen import _imagen_existe, construir_imagen_base
    from qagent.sandbox.modelos import IMAGEN_JAVA

    cliente = obtener_cliente()
    antes = soporte_docker.etiquetas_qagent(cliente)
    if not _imagen_existe(cliente, IMAGEN_JAVA):
        construir_imagen_base(cliente, avanzar=print, imagen=IMAGEN_JAVA)
    informe = {
        "matriz": "tests/compatibilidad_java/matriz.toml",
        "nivel": args.nivel,
        "filas_pedidas": args.fila,
        "entorno": ejecutar.entorno_de_ejecucion(cliente),
        "filas": [],
    }
    inicio = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="qagent-matriz-") as trabajo:
        for fila in filas:
            transcurrido = (time.monotonic() - inicio) / 60
            if args.presupuesto_min is not None and transcurrido > args.presupuesto_min:
                registro = ejecutar.no_ejecutada(
                    fila, f"presupuesto de {args.presupuesto_min} min agotado"
                )
            elif fila.tipo == "externo":
                print(
                    f"\n=== {fila.id} ({fila.url}@{fila.commit[:12]}) ===", flush=True
                )
                registro = ejecutar.ejecutar_externo(
                    fila,
                    cache=cache,
                    trabajo=Path(trabajo),
                    salida=salida,
                    cliente=cliente,
                )
            else:
                print(f"\n=== {fila.id} ({fila.prueba}) ===", flush=True)
                registro = ejecutar.ejecutar_fixture(
                    fila, salida=salida, cliente=cliente
                )
            print(f"--- {fila.id}: {registro['resultado']}", flush=True)
            for diferencia in registro.get("diferencias", []):
                print(f"    {diferencia}", flush=True)
            informe["filas"].append(registro)

    informe["duracion_s"] = round(time.monotonic() - inicio, 2)
    informe["totales"] = {
        r: sum(f["resultado"] == r for f in informe["filas"]) for r in matriz.RESULTADOS
    }
    if not args.conservar_imagenes:
        nuevas = soporte_docker.imagenes_creadas(
            antes, soporte_docker.etiquetas_qagent(cliente)
        )
        borradas, errores = soporte_docker.borrar_imagenes(cliente, nuevas)
        informe["imagenes_borradas"], informe["imagenes_no_borradas"] = (
            borradas,
            errores,
        )
    ejecutar.guardar_texto(
        salida / "matriz.json",
        json.dumps(informe, ensure_ascii=False, indent=2, default=str),
    )
    tabla = _tabla(informe["filas"])
    ejecutar.guardar_texto(salida / "matriz.md", "# Matriz Java\n\n" + tabla)
    print("\n" + tabla)
    print(f"Evidencia: {salida}")
    return matriz.codigo_salida(informe["filas"])


if __name__ == "__main__":
    sys.exit(main())
