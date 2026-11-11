"""Contexto estático para inferir funciones sin docstring (#275, ADR-016)."""

from __future__ import annotations

from pathlib import Path

from qagent.analysis.inferencia import (
    ContextoInferencia,
    ProveedorInferencia,
    indice_de_tests,
    indice_llamadores,
    motivo_evidencia,
)

MODULOS = [
    {
        "ruta": "calc.py",
        "funciones": [{"nombre": "producto", "llama_a": []}],
    },
    {
        "ruta": "uso.py",
        "funciones": [{"nombre": "cuadrado", "llama_a": ["calc.py::producto"]}],
    },
]


def _proyecto(tmp_path: Path) -> Path:
    (tmp_path / "calc.py").write_text(
        "def producto(a, b):\n    return a * b\n", encoding="utf-8"
    )
    (tmp_path / "uso.py").write_text(
        "from calc import producto\n\n\n"
        "def cuadrado(n):\n    total = producto(n, n)\n    return total\n",
        encoding="utf-8",
    )
    carpeta = tmp_path / "tests"
    carpeta.mkdir()
    (carpeta / "test_calc.py").write_text(
        "from calc import producto\n\n\n"
        "def test_producto():\n    assert producto(2, 3) == 6\n\n\n"
        "def test_otra_cosa():\n    assert 1 == 1\n",
        encoding="utf-8",
    )
    return tmp_path


def test_indice_llamadores_invierte_llama_a() -> None:
    assert indice_llamadores(MODULOS) == {"calc.py::producto": ["uso.py::cuadrado"]}


def test_indice_de_tests_solo_incluye_los_tests_que_mencionan_la_funcion(
    tmp_path: Path,
) -> None:
    indice = indice_de_tests(_proyecto(tmp_path))

    referencias = [ref for ref, _ in indice["producto"]]
    assert referencias == ["tests/test_calc.py::test_producto"]
    assert "assert producto(2, 3) == 6" in indice["producto"][0][1]


def test_indice_de_tests_ignora_carpetas_ocultas(tmp_path: Path) -> None:
    oculta = tmp_path / ".qagent" / "tests"
    oculta.mkdir(parents=True)
    (oculta / "test_generado.py").write_text(
        "def test_x():\n    producto(1, 1)\n", encoding="utf-8"
    )

    assert indice_de_tests(tmp_path) == {}


def test_contexto_junta_cuerpo_llamadores_y_tests(tmp_path: Path) -> None:
    proveedor = ProveedorInferencia(_proyecto(tmp_path), MODULOS)

    contexto = proveedor.contexto("calc.py", "producto")

    assert contexto is not None
    assert "return a * b" in contexto.codigo
    assert [ref for ref, _ in contexto.llamadores] == ["uso.py::cuadrado"]
    assert "producto(n, n)" in contexto.llamadores[0][1]
    assert [ref for ref, _ in contexto.tests] == ["tests/test_calc.py::test_producto"]
    assert contexto.referencias == {
        "cuerpo",
        "llamador:uso.py::cuadrado",
        "test_existente:tests/test_calc.py::test_producto",
    }


def test_contexto_es_none_si_la_funcion_no_existe(tmp_path: Path) -> None:
    proveedor = ProveedorInferencia(_proyecto(tmp_path), MODULOS)

    assert proveedor.contexto("calc.py", "no_existe") is None
    assert proveedor.contexto("falta.py", "producto") is None


def test_a_dict_lleva_las_referencias_validas() -> None:
    contexto = ContextoInferencia(
        modulo="m.py",
        nombre="f",
        codigo="def f(): ...",
        simbolos=("g",),
        tests=(("t.py::test_f", "def test_f(): ..."),),
    )

    datos = contexto.a_dict()

    assert datos["referencias"] == [
        "cuerpo",
        "dependencia:g",
        "test_existente:t.py::test_f",
    ]
    assert datos["tests_existentes"] == [
        {"ref": "t.py::test_f", "codigo": "def test_f(): ..."}
    ]


def test_motivo_evidencia() -> None:
    permitidas = frozenset({"cuerpo", "llamador:a.py::f"})

    assert motivo_evidencia(["cuerpo"], permitidas) is None
    assert "al menos una fuente" in motivo_evidencia([], permitidas)
    assert "al menos una fuente" in motivo_evidencia(None, permitidas)
    assert "no se entregaron" in motivo_evidencia(["llamador:x.py::g"], permitidas)
