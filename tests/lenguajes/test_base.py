"""Interfaz LanguageAdapter (EN-17): operaciones comunes y puntos de extensión."""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from qagent.lenguajes import (
    AdaptadorEnDesarrollo,
    Deteccion,
    EntornoSandbox,
    LanguageAdapter,
    NoImplementado,
)

OPERACIONES_ABSTRACTAS = {
    "analizar",
    "comando_pruebas",
    "entorno_sandbox",
    "interpretar_resultados",
    "validar_sintaxis",
    "comparar_aserciones",
}


class AdaptadorEnPruebas(AdaptadorEnDesarrollo):
    lenguaje = "java"
    extensiones = (".java",)
    marcadores = ("pom.xml", "build.gradle")
    frameworks_pruebas = ("junit5",)
    frameworks_app = ("spring",)


def test_la_interfaz_declara_detectar_analizar_y_extensiones() -> None:
    assert LanguageAdapter.__abstractmethods__ == OPERACIONES_ABSTRACTAS
    for nombre in (*OPERACIONES_ABSTRACTAS, "detectar", "objetivos"):
        assert inspect.getdoc(getattr(LanguageAdapter, nombre)), nombre


def test_no_se_puede_instanciar_sin_implementar_las_operaciones() -> None:
    class Incompleto(LanguageAdapter):
        lenguaje = "java"
        extensiones = (".java",)
        frameworks_pruebas = ("junit5",)

    with pytest.raises(TypeError):
        Incompleto()  # type: ignore[abstract]


# --- Detección ---------------------------------------------------------------------


def test_detectar_cuenta_fuentes_y_marcadores() -> None:
    deteccion = AdaptadorEnPruebas().detectar(
        ["pom.xml", "src/main/App.java", "src/main/Util.JAVA", "README.md"]
    )
    assert deteccion == Deteccion("java", archivos=2, marcadores=("pom.xml",))


def test_detectar_sin_indicios() -> None:
    assert AdaptadorEnPruebas().detectar(["app.py", "README.md"]) is None
    assert AdaptadorEnPruebas().detectar([]) is None


def test_un_marcador_solo_cuenta_por_su_nombre_exacto() -> None:
    assert AdaptadorEnPruebas().detectar(["docs/pom.xml.bak"]) is None
    deteccion = AdaptadorEnPruebas().detectar(["modulo/build.gradle"])
    assert deteccion is not None and deteccion.archivos == 0


# --- Información estructural -------------------------------------------------------


def test_objetivos_lista_funciones_y_endpoints() -> None:
    estructura: dict[str, Any] = {
        "modulos": [
            {
                "ruta": "tienda/api.py",
                "funciones": [{"nombre": "calcular"}],
                "endpoints": [{"objetivo": "GET /items/{id}"}, {"objetivo": None}],
            },
            {"ruta": "vacio.py", "funciones": []},
        ]
    }
    assert AdaptadorEnPruebas().objetivos(estructura) == [
        {"modulo": "tienda/api.py", "tipo": "funcion", "objetivo": "calcular"},
        {"modulo": "tienda/api.py", "tipo": "endpoint", "objetivo": "GET /items/{id}"},
    ]


def test_objetivos_de_una_estructura_vacia() -> None:
    assert AdaptadorEnPruebas().objetivos({}) == []


# --- Selección de framework --------------------------------------------------------


def test_framework_predeterminado_y_valido() -> None:
    adaptador = AdaptadorEnPruebas()
    assert adaptador.framework_predeterminado == "junit5"
    assert adaptador.elegir_framework() == "junit5"
    assert adaptador.elegir_framework("junit5") == "junit5"


def test_framework_de_otro_lenguaje_se_rechaza() -> None:
    with pytest.raises(ValueError, match="pytest"):
        AdaptadorEnPruebas().elegir_framework("pytest")


# --- Puntos de extensión pendientes -------------------------------------------------


@pytest.mark.parametrize(
    ("operacion", "argumentos"),
    [
        ("analizar", (".",)),
        ("comando_pruebas", ("App",)),
        ("entorno_sandbox", ()),
        ("interpretar_resultados", ("<testsuites/>",)),
        ("validar_sintaxis", ("class A {}",)),
        ("comparar_aserciones", ("a", "b")),
    ],
)
def test_operacion_pendiente_avisa_que_falta(operacion: str, argumentos: tuple) -> None:
    with pytest.raises(NoImplementado) as error:
        getattr(AdaptadorEnPruebas(), operacion)(*argumentos)
    assert error.value.lenguaje == "java"
    assert error.value.operacion == operacion
    assert isinstance(error.value, NotImplementedError)


def test_entorno_sandbox_es_inmutable() -> None:
    entorno = EntornoSandbox("img", ("x",), "/work/tests", "/out", "junit.xml")
    with pytest.raises(AttributeError):
        entorno.imagen = "otra"  # type: ignore[misc]
