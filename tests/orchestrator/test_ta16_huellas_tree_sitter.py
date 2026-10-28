"""TA-16: huella por función con tree-sitter y migración de las specs guardadas.

Hasta TA-16 la huella de cada función (`huella_objetivo`) era el SHA-256 de `ast.dump`.
Ahora sale del árbol de tree-sitter (versión 2). Una spec guardada con la huella
vieja sigue sirviendo si su módulo no cambió; si cambió, la función se trata como
modificada, igual que antes.
"""

from __future__ import annotations

import json
from pathlib import Path

from qagent.almacenamiento import huella_de_prueba
from qagent.almacenamiento.proyecto import VERSION_HUELLA_OBJETIVO
from qagent.analysis.arbol_ts import (
    definicion,
    huella_de_definicion,
    parsear,
    sentencias,
)
from qagent.orchestrator.regresion import huellas_de_objetivos, objetivos_repetibles
from tests.orchestrator.test_hu25_regresion import config, preparado  # noqa: F401

LEGADO = "c" * 64
RUN = "20261017-101500-abcd"
MUTACION = {
    "estado": "ok",
    "puntuacion": 80.0,
    "detectados": 4,
    "sobrevivientes": [],
    "mensaje": None,
}


def _huella(codigo: str) -> str:
    return huella_de_definicion(definicion(sentencias(parsear(codigo).root_node)[0]))


def test_la_huella_ignora_comentarios_espacios_y_posicion() -> None:
    base = _huella('def f(a, b=1):\n    """Doc."""\n    return a + b\n')
    assert len(base) == 64
    assert base == _huella(
        'def f(a,   b=1):  # comentario\n    """Doc."""\n\n    return a+b\n'
    )
    assert base == _huella('def f(a, b=1):\n  """Doc."""\n  return a + b\n')


def test_la_huella_cambia_con_el_codigo_el_docstring_o_los_decoradores() -> None:
    base = _huella('def f(a):\n    """Doc."""\n    return a\n')
    assert base != _huella('def f(a):\n    """Doc."""\n    return a + 1\n')
    assert base != _huella('def f(a):\n    """Otra."""\n    return a\n')
    assert base != _huella('def f(a=2):\n    """Doc."""\n    return a\n')
    assert base != _huella('@app.get("/")\ndef f(a):\n    """Doc."""\n    return a\n')


def _specs_aprobadas(almacen) -> list[Path]:
    return [
        p
        for p in sorted(almacen.carpeta_specs.glob("*.json"))
        if not p.name.endswith(".spec.json")
        and json.loads(p.read_text(encoding="utf-8")).get("archivo_prueba")
    ]


def _a_legado(ruta: Path) -> dict:
    """Deja la spec como la guardaba QAgent antes de TA-16."""
    spec = json.loads(ruta.read_text(encoding="utf-8"))
    spec.pop("version_huella_objetivo")
    spec["huella_objetivo"] = LEGADO
    ruta.write_text(json.dumps(spec), encoding="utf-8")
    return spec


def test_las_specs_nuevas_guardan_la_version_de_la_huella(preparado) -> None:  # noqa: F811
    _, almacen, _ = preparado
    for ruta in _specs_aprobadas(almacen):
        spec = json.loads(ruta.read_text(encoding="utf-8"))
        assert spec["version_huella_objetivo"] == VERSION_HUELLA_OBJETIVO


def test_spec_vieja_de_un_modulo_sin_cambios_se_migra(preparado) -> None:  # noqa: F811
    raiz, almacen, _ = preparado
    ruta = _specs_aprobadas(almacen)[0]
    spec = _a_legado(ruta)
    prueba = huella_de_prueba("def test_x(): pass\n")
    almacen.guardar_mutacion(spec["id"], LEGADO, prueba, MUTACION, RUN)
    contrato = spec["contrato"]

    huellas = huellas_de_objetivos(raiz)

    migrada = json.loads(ruta.read_text(encoding="utf-8"))
    nueva = huellas[(contrato["modulo"], contrato["objetivo"])]
    assert migrada["huella_objetivo"] == nueva
    assert migrada["version_huella_objetivo"] == VERSION_HUELLA_OBJETIVO
    mutacion = json.loads(
        (almacen.carpeta_mutacion / f"{spec['id']}.json").read_text(encoding="utf-8")
    )
    assert mutacion["huella_objetivo"] == nueva
    assert mutacion["version"] == str(VERSION_HUELLA_OBJETIVO)
    assert {"modulo": contrato["modulo"], "objetivo": contrato["objetivo"]} in (
        objetivos_repetibles(raiz)
    )


def test_spec_vieja_de_un_modulo_que_cambio_no_se_migra(preparado) -> None:  # noqa: F811
    raiz, almacen, _ = preparado
    ruta = _specs_aprobadas(almacen)[0]
    spec = _a_legado(ruta)
    contrato = spec["contrato"]
    modulo = raiz / contrato["modulo"]
    modulo.write_text(
        modulo.read_text(encoding="utf-8") + "\n# cambio\n", encoding="utf-8"
    )

    huellas_de_objetivos(raiz)

    sin_migrar = json.loads(ruta.read_text(encoding="utf-8"))
    assert sin_migrar["huella_objetivo"] == LEGADO
    assert "version_huella_objetivo" not in sin_migrar
    assert {"modulo": contrato["modulo"], "objetivo": contrato["objetivo"]} not in (
        objetivos_repetibles(raiz)
    )
