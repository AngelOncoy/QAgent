"""Tipos de prueba escalares del Sprint 1."""

from __future__ import annotations

import pytest

from qagent.pruebas.tipos import (
    ESTRATEGIAS_PRUEBA,
    EstrategiaInvalida,
    estrategia_historica,
    validar_estrategia,
)


def test_existen_exactamente_las_cuatro_estrategias() -> None:
    assert ESTRATEGIAS_PRUEBA == ("unitaria", "limites", "humo", "regresion")


@pytest.mark.parametrize(
    "valor", ["desconocida", "", ["unitaria"], ["humo", "regresion"], None]
)
def test_rechaza_valores_desconocidos_y_seleccion_multiple(valor) -> None:
    with pytest.raises(EstrategiaInvalida):
        validar_estrategia(valor)


def test_compatibilidad_con_perfiles_historicos() -> None:
    assert estrategia_historica(None, perfil="reg") == "regresion"
    assert estrategia_historica(None, perfil="humo") == "humo"
    assert estrategia_historica(None, perfil="deep") == "unitaria"
    assert estrategia_historica("limites", perfil="reg") == "limites"
