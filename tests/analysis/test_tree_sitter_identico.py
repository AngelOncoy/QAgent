"""TA-16: con tree-sitter, lo que recibe QAgent es idéntico a lo que daba ``ast``.

Las fotos de ``casos_tree_sitter/fotos/`` se tomaron con el analizador anterior (``ast``)
sobre el proyecto de casos límite ``casos_tree_sitter/proyecto/`` y sobre ``bench/``,
antes de migrar. Aquí se recalcula todo con tree-sitter y se compara campo por campo.

Solo se excluye el texto de ``mensaje`` de los errores de sintaxis (ya variaba entre
versiones de Python; ver ``test_analyzer.py``). La única diferencia aceptada está en
:data:`ARCHIVO_CON_BOM` y no toca la estructura del Planner.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import pytest

CASOS = Path(__file__).resolve().parent / "casos_tree_sitter"
SRC = Path(__file__).resolve().parents[2] / "src" / "qagent"
#: La regresión y la mutación leían el archivo con ``read_text`` y ``ast.parse``
#: rechazaba el BOM: esas funciones quedaban fuera. tree-sitter sí las ve, como el
#: analizador (que siempre leyó con ``tokenize``).
ARCHIVO_CON_BOM = "con_bom.py"
#: Módulos que leen código del usuario: ya no usan ``ast`` (TA-16).
LEEN_CODIGO_DEL_USUARIO = (
    "analysis/analyzer.py",
    "analysis/rutas.py",
    "analysis/ramas.py",
    "analysis/contexto.py",
    "analysis/arbol_ts.py",
    "analysis/texto_ts.py",
    "sandbox/manejadores.py",
    "orchestrator/regresion.py",
    "lenguajes/python_planificacion.py",
    "lenguajes/python_regresion.py",
)


def _cargar_generador():
    especificacion = importlib.util.spec_from_file_location(
        "generar_fotos", CASOS / "generar_fotos.py"
    )
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


@pytest.fixture(scope="module")
def fotos_nuevas() -> dict[str, Any]:
    # Por JSON, como las fotos: las tuplas pasan a listas y las claves a texto.
    return json.loads(json.dumps(_cargar_generador().fotos(), ensure_ascii=False))


def _foto(nombre: str) -> Any:
    return json.loads((CASOS / "fotos" / f"{nombre}.json").read_text(encoding="utf-8"))


def _sin_mensajes(analisis: dict[str, Any]) -> dict[str, Any]:
    return {
        **analisis,
        "errores": [
            {k: v for k, v in e.items() if k != "mensaje"} for e in analisis["errores"]
        ],
    }


@pytest.mark.parametrize("nombre", ["analisis_proyecto", "analisis_bench"])
def test_estructura_del_planner_identica(fotos_nuevas, nombre) -> None:
    assert _sin_mensajes(fotos_nuevas[nombre]) == _sin_mensajes(_foto(nombre))


def test_errores_de_sintaxis_se_siguen_reportando(fotos_nuevas) -> None:
    errores = fotos_nuevas["analisis_proyecto"]["errores"]
    assert {e["ruta"] for e in errores} >= {
        "errores/roto.py",
        "errores/py2_print.py",
        "errores/sangria.py",
        "binario.py",
    }
    assert all(e["mensaje"] for e in errores)


@pytest.mark.parametrize("nombre", ["manejadores", "planner"])
def test_salidas_identicas(fotos_nuevas, nombre) -> None:
    assert fotos_nuevas[nombre] == _foto(nombre)


def test_contexto_del_generator_identico(fotos_nuevas) -> None:
    esperado = _foto("contexto")
    nuevo = dict(fotos_nuevas["contexto"])
    agregado = nuevo.pop(f"{ARCHIVO_CON_BOM}::con_bom")
    assert nuevo == esperado
    assert agregado["codigo"].startswith("def con_bom(")


def test_lineas_y_objetivos_de_la_regresion(fotos_nuevas) -> None:
    lineas = _foto("lineas")
    lineas[ARCHIVO_CON_BOM] = [{"nombre": "con_bom", "linea": 4}]
    assert fotos_nuevas["lineas"] == lineas
    objetivos = sorted([*_foto("objetivos_huella"), f"{ARCHIVO_CON_BOM}::con_bom"])
    assert fotos_nuevas["objetivos_huella"] == objetivos


@pytest.mark.parametrize("modulo", LEEN_CODIGO_DEL_USUARIO)
def test_el_codigo_del_usuario_ya_no_se_lee_con_ast(modulo) -> None:
    fuente = (SRC / modulo).read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import ast|from ast import)", fuente, re.MULTILINE)
