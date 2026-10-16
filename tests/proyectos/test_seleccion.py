"""Validación del alcance elegido en la Vista previa."""

from __future__ import annotations

import pytest

from qagent.proyectos.seleccion import SeleccionInvalida, filtrar_modulos


@pytest.fixture
def modulos() -> list[dict]:
    return [
        {"ruta": "vacio.py", "funciones": [], "endpoints": []},
        {
            "ruta": "funciones.py",
            "funciones": [{"nombre": "sumar"}, {"nombre": "restar"}],
            "endpoints": [],
        },
        {
            "ruta": "api.py",
            "funciones": [],
            "endpoints": [
                {"objetivo": "GET /items"},
                {"objetivo": "POST /items"},
            ],
        },
    ]


def test_sin_seleccion_incluye_funciones_y_endpoints_pero_no_archivos_vacios(
    modulos,
) -> None:
    resultado = filtrar_modulos(modulos, None)

    assert [m["ruta"] for m in resultado] == ["funciones.py", "api.py"]


def test_filtra_funciones_y_conserva_varios_endpoints_seleccionados(modulos) -> None:
    seleccion = [
        {"ruta": "funciones.py", "funciones": ["restar"], "endpoints": []},
        {
            "ruta": "api.py",
            "funciones": [],
            "endpoints": ["GET /items", "POST /items"],
        },
    ]

    resultado = filtrar_modulos(modulos, seleccion)

    assert [f["nombre"] for f in resultado[0]["funciones"]] == ["restar"]
    assert [e["objetivo"] for e in resultado[1]["endpoints"]] == [
        "GET /items",
        "POST /items",
    ]


@pytest.mark.parametrize(
    "seleccion, mensaje",
    [
        ([], "Selecciona al menos"),
        (
            [{"ruta": "vacio.py", "funciones": [], "endpoints": []}],
            "no existe o no contiene",
        ),
        (
            [{"ruta": "funciones.py", "funciones": ["inventada"], "endpoints": []}],
            "Objetivos inexistentes",
        ),
    ],
)
def test_rechaza_seleccion_vacia_o_inexistente(modulos, seleccion, mensaje) -> None:
    with pytest.raises(SeleccionInvalida, match=mensaje):
        filtrar_modulos(modulos, seleccion)
