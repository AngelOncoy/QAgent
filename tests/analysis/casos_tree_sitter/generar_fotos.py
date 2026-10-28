"""Genera las fotos (salida esperada) de los casos límite de tree-sitter (TA-16).

Se corrió una sola vez con el analizador anterior, basado en ``ast``, antes de migrar
a tree-sitter: las fotos son la referencia de «estructura idéntica» que verifica
``tests/analysis/test_tree_sitter_identico.py``. Volver a correrlo con el analizador
nuevo solo tiene sentido si cambia a propósito lo que recibe el Planner.

Uso: ``python tests/analysis/casos_tree_sitter/generar_fotos.py``
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ_REPO = AQUI.parents[2]
sys.path.insert(0, str(RAIZ_REPO / "src"))

from qagent.agents import planner
from qagent.analysis import analizar_proyecto
from qagent.analysis.contexto import contexto_de_funcion
from qagent.orchestrator import regresion
from qagent.sandbox import manejadores

PROYECTO = AQUI / "proyecto"
FOTOS = AQUI / "fotos"

#: Anotaciones y firmas sueltas para las ayudas del Planner, además de las del análisis.
ANOTACIONES = [
    "tuple[int, int]",
    "Tuple[int]",
    "typing.Tuple[str, ...]",
    "tuple",
    " tuple [ int ] ",
    "list[tuple[int]]",
    "Literal['a']",
    "Literal[1]",
    "typing.Literal[-1]",
    "Literal['a', 'b']",
    "Literal[None]",
    "Literal[x]",
    "int |",
    "",
    "Literal[('a', 'b')]",
    'Literal["x" "y"]',
]
FIRMAS = [
    "(a, b=1, /, c=2, *args, d, e=3, **kw)",
    "(a: int, b: str = 'x') -> tuple[int, str]",
    "(*, a)",
    "() -> None",
    "(a",
    "sin parentesis",
]
ENTRADAS = [{}, {"a": 1}, {"a": 1, "d": 2}, {"a": 1, "z": 3}, {"b": 1}, {"kw": 1}]


def _modulos(analisis: dict) -> list[str]:
    return [m["ruta"] for m in analisis["modulos"]]


def _funciones_de_nivel(ruta: Path) -> list[str]:
    return [f["nombre"] for f in regresion._lineas_de(ruta.parent, ruta.name)]


def fotos() -> dict[str, object]:
    analisis = analizar_proyecto(PROYECTO)
    resultado: dict[str, object] = {
        "analisis_proyecto": analisis,
        "analisis_bench": analizar_proyecto(RAIZ_REPO / "bench"),
    }

    contexto: dict[str, object] = {}
    lineas: dict[str, object] = {}
    for modulo in _modulos(analisis):
        lineas[modulo] = regresion._lineas_de(PROYECTO, modulo)
        nombres = [f["nombre"] for f in lineas[modulo]] + ["no_existe"]
        for nombre in nombres:
            ctx = contexto_de_funcion(PROYECTO, modulo, nombre)
            contexto[f"{modulo}::{nombre}"] = None if ctx is None else vars(ctx)
    for error in analisis["errores"]:
        contexto[f"{error['ruta']}::f"] = contexto_de_funcion(
            PROYECTO, error["ruta"], "f"
        )
        lineas[error["ruta"]] = regresion._lineas_de(PROYECTO, error["ruta"])
    resultado["contexto"] = contexto
    resultado["lineas"] = lineas

    aislados: dict[str, object] = {}
    for modulo in ("api/rutas.py", "api/main.py", "api/extra.py", "funciones.py"):
        fuente = (PROYECTO / modulo).read_text(encoding="utf-8")
        nombres = [f["nombre"] for f in regresion._lineas_de(PROYECTO, modulo)]
        motivos = {n: manejadores.motivo_no_aislable(fuente, n) for n in nombres}
        motivos["no_existe"] = manejadores.motivo_no_aislable(fuente, "no_existe")
        aislables = [n for n, m in motivos.items() if m is None]
        aislados[modulo] = {
            "motivos": motivos,
            "aislado": manejadores.aislar_manejadores(fuente, aislables)
            if aislables
            else None,
        }
    aislados["roto"] = manejadores.motivo_no_aislable("def f(:\n", "f")
    resultado["manejadores"] = aislados

    firmas = (
        FIRMAS
        + [f["firma"] for m in analisis["modulos"] for f in m["funciones"]]
        + [e["firma"] for m in analisis["modulos"] for e in m["endpoints"]]
    )
    anotaciones = ANOTACIONES + [
        f["retorno"]
        for m in analisis["modulos"]
        for f in m["funciones"]
        if f["retorno"]
    ]
    resultado["planner"] = {
        "es_tupla": {a: planner._anotacion_es_tupla(a) for a in anotaciones},
        "literal_unico": {
            a: repr(planner._literal_unico(a))
            for a in anotaciones
            if planner._literal_unico(a) is not planner._SIN_LITERAL
        },
        "retorno_de_firma": {f: planner._retorno_de_firma(f) for f in firmas},
        "no_liga": {
            f: [planner._llamada_no_liga({"firma": f}, e) for e in ENTRADAS]
            for f in firmas
        },
        "docstring_tupla": [
            planner._docstring_respalda_tupla(d, {"valor_esperado": v})
            for d, v in [
                ("f(1) -> (1, 2)", [1, 2]),
                ("f(1) -> (1, 'a')", [1, "a"]),
                ("f(1) -> [1, 2]", [1, 2]),
                ("f(1) -> (1, 2)  # comentario", [1, 2]),
                ("f(1) -> (1, x)", [1, 2]),
                ("f(1) -> -1, 2", [-1, 2]),
            ]
        ],
    }
    resultado["objetivos_huella"] = sorted(
        f"{m}::{o}" for m, o in regresion.huellas_de_objetivos(PROYECTO)
    )
    return resultado


def main() -> None:
    FOTOS.mkdir(exist_ok=True)
    for nombre, valor in fotos().items():
        texto = json.dumps(valor, ensure_ascii=False, indent=2, sort_keys=False)
        (FOTOS / f"{nombre}.json").write_text(texto + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
