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


def test_las_funciones_marcadas_llegan_como_criticas(modulos) -> None:
    seleccion = [
        {
            "ruta": "funciones.py",
            "funciones": ["sumar", "restar"],
            "endpoints": [],
            "criticas": ["restar"],
        }
    ]

    resultado = filtrar_modulos(modulos, seleccion)

    criticas = {f["nombre"]: f["critical"] for f in resultado[0]["funciones"]}
    assert criticas == {"sumar": False, "restar": True}


def test_sin_criticas_ninguna_funcion_es_critica(modulos) -> None:
    seleccion = [{"ruta": "funciones.py", "funciones": ["sumar"], "endpoints": []}]

    resultado = filtrar_modulos(modulos, seleccion)

    assert resultado[0]["funciones"] == [{"nombre": "sumar", "critical": False}]


def test_marcar_criticas_no_modifica_el_analisis_recibido(modulos) -> None:
    seleccion = [
        {
            "ruta": "funciones.py",
            "funciones": ["sumar"],
            "endpoints": [],
            "criticas": ["sumar"],
        }
    ]

    filtrar_modulos(modulos, seleccion)

    assert modulos[1]["funciones"] == [{"nombre": "sumar"}, {"nombre": "restar"}]


@pytest.mark.parametrize(
    "criticas, mensaje",
    [
        (["restar"], "no están seleccionadas en funciones.py: restar"),
        (["inventada"], "no están seleccionadas en funciones.py: inventada"),
        (["sumar", "sumar"], "no es válida"),
        ("sumar", "no es válida"),
        ([1], "no es válida"),
    ],
)
def test_rechaza_criticas_invalidas(modulos, criticas, mensaje) -> None:
    seleccion = [
        {
            "ruta": "funciones.py",
            "funciones": ["sumar"],
            "endpoints": [],
            "criticas": criticas,
        }
    ]

    with pytest.raises(SeleccionInvalida, match=mensaje):
        filtrar_modulos(modulos, seleccion)


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


# --- #74: endpoints marcados para profundizar ---------------------------------------


def test_los_endpoints_marcados_llegan_como_criticos(modulos) -> None:
    seleccion = [
        {
            "ruta": "api.py",
            "funciones": [],
            "endpoints": ["GET /items", "POST /items"],
            "criticas": ["POST /items"],
        }
    ]

    resultado = filtrar_modulos(modulos, seleccion)

    criticos = {e["objetivo"]: e["critical"] for e in resultado[0]["endpoints"]}
    assert criticos == {"GET /items": False, "POST /items": True}
    # El análisis recibido no cambia.
    assert modulos[2]["endpoints"] == [
        {"objetivo": "GET /items"},
        {"objetivo": "POST /items"},
    ]


def test_sin_criticas_ningun_endpoint_es_critico(modulos) -> None:
    seleccion = [{"ruta": "api.py", "funciones": [], "endpoints": ["GET /items"]}]

    resultado = filtrar_modulos(modulos, seleccion)

    assert resultado[0]["endpoints"] == [{"objetivo": "GET /items", "critical": False}]


@pytest.mark.parametrize(
    "criticas, mensaje",
    [
        (["DELETE /items"], "no están seleccionadas en api.py: DELETE /items"),
        (["POST /items"], "no están seleccionadas en api.py: POST /items"),
        (["GET /items", "GET /items"], "no es válida"),
    ],
)
def test_rechaza_endpoints_marcados_invalidos(modulos, criticas, mensaje) -> None:
    seleccion = [
        {
            "ruta": "api.py",
            "funciones": [],
            "endpoints": ["GET /items"],
            "criticas": criticas,
        }
    ]

    with pytest.raises(SeleccionInvalida, match=mensaje):
        filtrar_modulos(modulos, seleccion)
