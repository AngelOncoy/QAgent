"""EN-18 (#130): contrato explanation.v1 y validación de evidencia."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from qagent import contracts
from qagent.contracts import ContratoInvalido
from tests.test_contracts import ejemplo

FIXTURE = Path(__file__).parent / "fixtures/en18/explicaciones.json"


def fixture() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def validar(datos: dict[str, Any], explicacion: dict[str, Any] | None = None):
    return contracts.validar_explicacion(
        explicacion or datos["explicacion"],
        hallazgos_confiables=datos["hallazgos_confiables"],
        evidencias_confiables=datos["evidencias_confiables"],
        verificaciones_confiables=datos["verificaciones_confiables"],
    )


def test_caso_a_explicacion_valida_con_evidencia() -> None:
    datos = fixture()

    assert validar(datos) is datos["explicacion"]


def test_caso_b_campo_obligatorio_ausente_da_error_comprensible() -> None:
    datos = fixture()
    del datos["explicacion"]["hallazgo_id"]

    with pytest.raises(ContratoInvalido) as error:
        validar(datos)

    assert any("hallazgo_id" in e for e in error.value.errores)


def test_caso_c_evidencia_inexistente_se_rechaza() -> None:
    datos = fixture()
    datos["explicacion"]["hallazgo"]["evidencia_ids"] = ["evidencia-inventada"]

    with pytest.raises(ContratoInvalido) as error:
        validar(datos)

    assert any("no existe" in e for e in error.value.errores)


def test_caso_d_solucion_propuesta_no_declara_exito() -> None:
    datos = fixture()

    assert datos["explicacion"]["verificacion"] == {"estado": "propuesta"}
    assert validar(datos)


def test_caso_e_verificacion_con_ejecucion_independiente() -> None:
    datos = fixture()
    datos["explicacion"]["verificacion"] = {
        "estado": "verificada",
        "ejecucion_id": "ejecucion-fix-001",
        "run_id": "run-002",
    }

    assert validar(datos)


def test_caso_e_afirmacion_del_llm_no_verifica_una_solucion() -> None:
    datos = fixture()
    datos["explicacion"]["verificacion"] = {
        "estado": "verificada",
        "ejecucion_id": "afirmacion-llm-001",
        "run_id": "run-002",
    }

    with pytest.raises(ContratoInvalido, match="afirmación del LLM"):
        validar(datos)


def test_caso_e_verificacion_inexistente_se_rechaza() -> None:
    datos = fixture()
    datos["explicacion"]["verificacion"] = {
        "estado": "verificada",
        "ejecucion_id": "ejecucion-inventada",
        "run_id": "run-002",
    }

    with pytest.raises(ContratoInvalido, match="no existe una ejecución confiable"):
        validar(datos)


@pytest.mark.parametrize("campo", ["decision", "veredicto", "codigo_prueba", "parche"])
def test_caso_f_no_permite_alterar_reviewer_pruebas_ni_resultados(
    campo: str,
) -> None:
    datos = fixture()
    datos["explicacion"][campo] = "accept"

    assert not contracts.es_valido(contracts.EXPLANATION_V1, datos["explicacion"])


def test_referencia_debe_coincidir_con_el_hallazgo_original() -> None:
    datos = fixture()
    datos["explicacion"]["referencia_resultado"]["run_id"] = "run-otro"

    with pytest.raises(ContratoInvalido, match="no coincide"):
        validar(datos)


def test_evidencia_de_otro_hallazgo_se_rechaza() -> None:
    datos = fixture()
    datos["evidencias_confiables"]["evidencia-ajena"] = {"origen": "sandbox"}
    datos["explicacion"]["recomendacion"]["evidencia_ids"] = ["evidencia-ajena"]

    with pytest.raises(ContratoInvalido, match="no pertenece"):
        validar(datos)


def test_ubicacion_absoluta_se_rechaza() -> None:
    datos = fixture()
    datos["explicacion"]["ubicacion"]["archivo"] = "C:/proyecto/precios.ts"

    with pytest.raises(ContratoInvalido, match="ruta relativa segura"):
        validar(datos)


def test_origen_ia_exige_modelo() -> None:
    datos = fixture()
    datos["explicacion"].update(origen="ia", modelo=None)

    assert not contracts.es_valido(contracts.EXPLANATION_V1, datos["explicacion"])


def test_version_desconocida_se_rechaza() -> None:
    datos = fixture()
    datos["explicacion"]["version"] = "2"

    with pytest.raises(ContratoInvalido) as error:
        contracts.validar_versionado(
            contracts.FAMILIA_EXPLANATION, datos["explicacion"]
        )

    assert error.value.errores[0].startswith("version:")


def test_serializacion_preserva_referencias() -> None:
    datos = fixture()
    original = datos["explicacion"]
    recuperada = json.loads(json.dumps(original, ensure_ascii=False))

    assert recuperada == original
    assert validar(datos, recuperada)


def test_caso_g_no_interfiere_con_contratos_existentes() -> None:
    planner = ejemplo(contracts.PLANNER_V3)
    review = ejemplo(contracts.REVIEW_RESULT)

    assert contracts.validar_versionado(contracts.FAMILIA_PLANNER, planner)
    assert contracts.validar(contracts.REVIEW_RESULT, review)
    assert "explanation" not in planner and "explanation" not in review
