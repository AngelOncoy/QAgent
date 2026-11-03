from __future__ import annotations

import pytest

from qagent import contracts
from qagent.arquitectura.modelo import (
    REGLA_UNIVERSAL,
    reglas_ejecutables,
    reglas_para_proyecto,
    validar_documento,
)


def documento(*reglas: dict) -> dict:
    return {"version": "1", "reglas": list(reglas)}


def regla_usuario(**cambios: object) -> dict:
    regla = {
        "id": "capas-001",
        "tipo": "dependencia_prohibida",
        "nombre": "Dominio no importa interfaz",
        "origen": "usuario",
        "confirmada": True,
        "desde": "dominio",
        "hacia": "interfaz",
    }
    regla.update(cambios)
    return regla


def test_regla_universal_y_documento_sin_personalizadas() -> None:
    dato = reglas_para_proyecto()
    assert dato == documento(REGLA_UNIVERSAL)
    assert contracts.es_valido(contracts.ARCHITECTURE_RULES_V1, dato)


def test_regla_personalizada_valida_y_serializable() -> None:
    dato = documento(regla_usuario())
    assert validar_documento(dato) is dato
    assert (
        contracts.validar_versionado(contracts.FAMILIA_ARCHITECTURE_RULES, dato) == dato
    )


@pytest.mark.parametrize(
    ("cambio", "valor"),
    [
        ("tipo", "shell"),
        ("id", None),
        ("origen", "modelo"),
        ("desde", "dominio; rm -rf /"),
    ],
)
def test_rechaza_campos_invalidos(cambio: str, valor: object) -> None:
    regla = regla_usuario()
    if valor is None:
        regla.pop(cambio)
    else:
        regla[cambio] = valor
    with pytest.raises(contracts.ContratoInvalido):
        validar_documento(documento(regla))


@pytest.mark.parametrize("campo", ["command", "comando", "args", "shell"])
def test_rechaza_campos_de_ejecucion(campo: str) -> None:
    regla = regla_usuario()
    regla[campo] = "echo no"
    with pytest.raises(contracts.ContratoInvalido):
        validar_documento(documento(regla))


def test_rechaza_version_capas_faltantes_e_ids_duplicados() -> None:
    with pytest.raises(contracts.ContratoInvalido):
        validar_documento({"version": "2", "reglas": []})
    sin_hacia = regla_usuario()
    sin_hacia.pop("hacia")
    with pytest.raises(contracts.ContratoInvalido):
        validar_documento(documento(sin_hacia))
    with pytest.raises(contracts.ContratoInvalido, match="únicos"):
        validar_documento(documento(regla_usuario(), regla_usuario()))


def test_sugerencia_no_confirmada_no_es_ejecutable() -> None:
    sugerida = regla_usuario(id="ia-001", origen="ia", confirmada=False)
    dato = reglas_para_proyecto(documento(sugerida))
    assert [r["id"] for r in reglas_ejecutables(dato)] == [REGLA_UNIVERSAL["id"]]


def test_sugerencia_confirmada_si_es_ejecutable() -> None:
    sugerida = regla_usuario(id="ia-001", origen="ia", confirmada=True)
    assert len(reglas_ejecutables(reglas_para_proyecto(documento(sugerida)))) == 2


def test_json_malformado_se_rechaza_antes_del_schema() -> None:
    import json

    with pytest.raises(json.JSONDecodeError):
        json.loads('{"version": "1",')
