"""EN-18 (#130): contrato y validación de oráculos JavaScript/TypeScript."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from qagent import contracts
from qagent.contracts import ContratoInvalido
from tests.test_contracts import ejemplo

BANCO = Path(__file__).parent / "fixtures/en18/oraculos_js_ts.json"


def casos() -> list[dict[str, Any]]:
    """Banco documentado de tres oráculos verificables y tres insuficientes."""
    return json.loads(BANCO.read_text(encoding="utf-8"))["casos"]


def registro(caso: dict[str, Any]) -> dict[str, dict[str, Any]]:
    evidencia = caso["contrato"].get("evidencia")
    if evidencia is None:
        return {}
    return {evidencia["id"]: {"evidencia": evidencia, **caso["registro"]}}


@pytest.mark.parametrize("caso", casos()[:3], ids=lambda c: c["nombre"])
def test_tres_oraculos_js_ts_verificables(caso: dict[str, Any]) -> None:
    contrato = caso["contrato"]

    assert caso["resultado_validacion"] == "verificable"
    assert contracts.validar_oraculo_js_ts(contrato, registro(caso)) is contrato


@pytest.mark.parametrize("caso", casos()[3:], ids=lambda c: c["nombre"])
def test_tres_fuentes_insuficientes_se_clasifican_sin_inventar_resultado(
    caso: dict[str, Any],
) -> None:
    contrato = caso["contrato"]

    assert contrato["estado_evidencia"] in {"insuficiente", "contradictoria"}
    assert "valor_esperado" not in contrato
    assert contracts.validar_oraculo_js_ts(contrato, registro(caso)) is contrato


@pytest.mark.parametrize("indice", [3, 4, 5])
def test_evidencia_insuficiente_no_puede_declararse_verificable(indice: int) -> None:
    caso = copy.deepcopy(casos()[indice])
    contrato = caso["contrato"]
    contrato["estado_evidencia"] = "verificable"
    contrato["valor_esperado"] = 5
    contrato.pop("motivo")
    caso["registro"]["valor_documentado"] = 5

    with pytest.raises(ContratoInvalido, match="no justifica un valor concreto"):
        contracts.validar_oraculo_js_ts(contrato, registro(caso))


def test_rechaza_valor_esperado_inventado() -> None:
    caso = copy.deepcopy(casos()[0])
    caso["contrato"]["valor_esperado"] = 6

    with pytest.raises(ContratoInvalido) as error:
        contracts.validar_oraculo_js_ts(caso["contrato"], registro(caso))

    assert any("valor_esperado" in e for e in error.value.errores)


def test_rechaza_procedencia_inexistente() -> None:
    contrato = copy.deepcopy(casos()[1]["contrato"])

    with pytest.raises(ContratoInvalido) as error:
        contracts.validar_oraculo_js_ts(contrato, {})

    assert error.value.errores == [
        "evidencia/id: 'ev-jsdoc-saludar-ana' no existe en el registro confiable"
    ]


def test_sin_procedencia_se_representa_sin_resultado() -> None:
    contrato = copy.deepcopy(casos()[3]["contrato"])
    contrato.update(
        estado_evidencia="sin_procedencia",
        motivo="No existe una fuente independiente de la implementación.",
    )
    contrato.pop("evidencia")

    assert contracts.validar_oraculo_js_ts(contrato, {}) is contrato
    contrato["valor_esperado"] = 5
    assert not contracts.es_valido(contracts.ORACLE_V1, contrato)


@pytest.mark.parametrize("esperado", [0, False, "", None])
def test_conserva_valores_json_validos_aunque_sean_falsy(esperado: Any) -> None:
    caso = copy.deepcopy(casos()[0])
    caso["contrato"]["valor_esperado"] = esperado
    caso["registro"]["valor_documentado"] = esperado

    assert contracts.validar_oraculo_js_ts(caso["contrato"], registro(caso))


def test_distingue_false_de_cero() -> None:
    caso = copy.deepcopy(casos()[0])
    caso["contrato"]["valor_esperado"] = False
    caso["registro"]["valor_documentado"] = 0

    with pytest.raises(ContratoInvalido, match="no coincide"):
        contracts.validar_oraculo_js_ts(caso["contrato"], registro(caso))


def test_serializacion_conserva_procedencia_y_valor() -> None:
    original = casos()[2]["contrato"]
    recuperado = json.loads(json.dumps(original, ensure_ascii=False))
    caso = {**casos()[2], "contrato": recuperado}

    assert recuperado == original
    assert contracts.validar_oraculo_js_ts(recuperado, registro(caso))


def test_version_desconocida_indica_el_campo() -> None:
    contrato = copy.deepcopy(casos()[0]["contrato"])
    contrato["version"] = "2"

    with pytest.raises(ContratoInvalido) as error:
        contracts.validar_versionado(contracts.FAMILIA_ORACLE, contrato)

    assert error.value.errores[0].startswith("version:")


def test_contratos_python_anteriores_no_cambian() -> None:
    planner_v2 = ejemplo(contracts.PLANNER)

    assert contracts.validar_versionado(contracts.FAMILIA_PLANNER, planner_v2)
    assert contracts.normalizar_planner(planner_v2)["lenguaje"] == "python"
    assert "evidencia" not in planner_v2["casos"][0]
