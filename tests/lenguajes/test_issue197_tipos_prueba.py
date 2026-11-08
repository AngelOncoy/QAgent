"""#197: cada adaptador declara qué tipos de prueba ejecuta y cuáles vienen después."""

from __future__ import annotations

import pytest

from qagent import contracts
from qagent.lenguajes import REGISTRO, AdaptadorEnDesarrollo, Registro


@pytest.mark.parametrize(
    ("lenguaje", "tipos"),
    [
        ("python", ("funcion", "endpoint", "mutacion", "integracion")),
        ("java", ("funcion", "endpoint", "mutacion")),
    ],
)
def test_los_lenguajes_completos_declaran_sus_tipos(
    lenguaje: str, tipos: tuple[str, ...]
) -> None:
    adaptador = REGISTRO.adaptador_para(lenguaje)

    assert adaptador.completo
    assert adaptador.tipos_prueba == tipos


@pytest.mark.parametrize("lenguaje", ["javascript", "typescript"])
def test_javascript_y_typescript_anuncian_sus_tipos_operativos(
    lenguaje: str,
) -> None:
    """EP-11: Vitest, mutación con Stryker y componentes React ya corren."""
    adaptador = REGISTRO.adaptador_para(lenguaje)

    assert adaptador.completo
    assert adaptador.tipos_prueba == ("funcion", "mutacion", "componente")
    assert adaptador.tipos_prueba_previstos == ()


def test_todos_los_tipos_declarados_estan_en_el_contrato() -> None:
    for lenguaje in REGISTRO.lenguajes:
        adaptador = REGISTRO.adaptador_para(lenguaje)
        tipos = {*adaptador.tipos_prueba, *adaptador.tipos_prueba_previstos}
        assert tipos <= set(contracts.TIPOS_PRUEBA_RECOMENDABLES)


class _JavaConTipos(AdaptadorEnDesarrollo):
    lenguaje = "java"
    extensiones = (".java",)
    frameworks_pruebas = ("junit5",)
    tipos_prueba = ("funcion",)


class _JavaTipoDesconocido(AdaptadorEnDesarrollo):
    lenguaje = "java"
    extensiones = (".java",)
    frameworks_pruebas = ("junit5",)
    tipos_prueba_previstos = ("e2e",)


def test_un_adaptador_en_desarrollo_no_puede_declarar_tipos_operativos() -> None:
    with pytest.raises(ValueError, match="en desarrollo"):
        Registro([_JavaConTipos()])


def test_un_tipo_fuera_del_contrato_se_rechaza() -> None:
    with pytest.raises(ValueError, match="fuera del contrato"):
        Registro([_JavaTipoDesconocido()])
