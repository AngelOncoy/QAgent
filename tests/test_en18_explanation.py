"""EN-18 (#130) / ADR-008: Contrato explanation.v1 y schema de explicaciones.json."""

from __future__ import annotations

import copy
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


def validar(
    datos: dict[str, Any], explicacion: dict[str, Any] | None = None
) -> dict[str, Any]:
    return contracts.validar_explicacion(
        explicacion or datos["explicacion"],
        results_confiables=datos.get("results_confiables"),
    )


def test_caso_a_explicacion_valida_con_results_json() -> None:
    datos = fixture()

    assert validar(datos) is datos["explicacion"]


@pytest.mark.parametrize(
    "campo",
    [
        "version",
        "objetivo",
        "decision",
        "resumen",
        "que_se_esperaba",
        "que_paso",
        "que_hacer",
        "origen",
    ],
)
def test_caso_b_campo_obligatorio_ausente_da_error_comprensible(campo: str) -> None:
    datos = fixture()
    del datos["explicacion"][campo]

    with pytest.raises(ContratoInvalido) as error:
        validar(datos)

    assert any(campo in e for e in error.value.errores)


def test_caso_c_origen_ia_exige_modelo() -> None:
    datos = fixture()
    datos["explicacion"].update(origen="ia", modelo=None)

    assert not contracts.es_valido(contracts.EXPLANATION_V1, datos["explicacion"])

    datos["explicacion"].update(modelo="mimo-v2.6-pro")
    assert contracts.es_valido(contracts.EXPLANATION_V1, datos["explicacion"])
    assert validar(datos)


def test_caso_d_decision_eco_coincide_con_results_json() -> None:
    datos = fixture()
    # 1. bug_detectado
    assert validar(datos)

    # 2. stalled
    datos["explicacion"].update(
        objetivo="procesarPago",
        decision="stalled",
    )
    assert validar(datos)

    # 3. sin_veredicto / None
    datos["explicacion"].update(
        objetivo="enviarCorreo",
        decision=None,
    )
    assert validar(datos)

    datos["explicacion"].update(decision="sin_veredicto")
    assert validar(datos)


def test_caso_e_decision_mismatch_se_rechaza() -> None:
    datos = fixture()
    # results.json tiene decision="bug_detectado" para calcularDescuento
    datos["explicacion"]["decision"] = "stalled"

    with pytest.raises(ContratoInvalido, match="no coincide"):
        validar(datos)


def test_caso_f_decision_accept_se_rechaza_por_schema_y_validador() -> None:
    datos = fixture()
    # 1. El schema directamente no admite "accept" en decision
    datos["explicacion"]["decision"] = "accept"
    assert not contracts.es_valido(contracts.EXPLANATION_V1, datos["explicacion"])

    # 2. El validador rechaza intentar explicar un objetivo cuyo resultado fue accept
    datos["explicacion"]["objetivo"] = "aplicarImpuesto"
    datos["explicacion"]["decision"] = "bug_detectado"
    with pytest.raises(
        ContratoInvalido,
        match="no se admiten explicaciones para objetivos con decision 'accept'",
    ):
        validar(datos)


def test_caso_g_objetivo_inexistente_en_results_json_se_rechaza() -> None:
    datos = fixture()
    datos["explicacion"]["objetivo"] = "objetivoInexistente"

    with pytest.raises(ContratoInvalido, match="no existe en results.json"):
        validar(datos)


@pytest.mark.parametrize(
    "propuesta_prohibida",
    [
        "Relajar la aserción para que la prueba pase.",
        "Se recomienda relajar el assert de cálculo de descuento.",
        "Debilitar las aserciones del test.",
        "Cambiar el valor esperado a 75.",
        "Modificar el valor esperado del contrato.",
        "Ajustar el valor esperado de la prueba.",
        "Eliminar la aserción que falla.",
        "Quitar el assert para evitar el error.",
        "Bajar el rigor de la aserción.",
        "Ignorar el fallo de la prueba.",
    ],
)
def test_caso_h_propuesta_de_relajar_aserción_o_cambiar_esperado_se_rechaza(
    propuesta_prohibida: str,
) -> None:
    datos = fixture()
    datos["explicacion"]["que_hacer"] = propuesta_prohibida

    with pytest.raises(
        ContratoInvalido,
        match="no se permite proponer relajar una aserción ni cambiar el valor esperado",
    ):
        validar(datos)


def test_caso_i_verificacion_estado_verificada_se_rechaza() -> None:
    datos = fixture()
    datos["explicacion"]["verificacion"] = {"estado": "verificada"}

    # Rechazada tanto por schema como por validador semántico
    assert not contracts.es_valido(contracts.EXPLANATION_V1, datos["explicacion"])
    with pytest.raises(ContratoInvalido, match="verificada"):
        validar(datos)


def test_caso_j_verificacion_propuesta_o_ausente_se_acepta() -> None:
    datos = fixture()
    datos["explicacion"]["verificacion"] = {"estado": "propuesta"}
    assert validar(datos)

    datos["explicacion"]["verificacion"] = {"estado": "pendiente"}
    assert validar(datos)

    del datos["explicacion"]["verificacion"]
    assert validar(datos)


@pytest.mark.parametrize(
    "campo_ajeno",
    ["parche", "codigo_prueba", "veredicto", "hallazgo_id", "evidencia_ids"],
)
def test_caso_k_no_permite_campos_ajenos(campo_ajeno: str) -> None:
    datos = fixture()
    datos["explicacion"][campo_ajeno] = "algo"

    assert not contracts.es_valido(contracts.EXPLANATION_V1, datos["explicacion"])


def test_caso_l_ubicacion_relativa_y_lineas() -> None:
    datos = fixture()
    datos["explicacion"]["ubicacion"]["archivo"] = "C:/proyecto/precios.ts"
    with pytest.raises(ContratoInvalido, match="ruta relativa segura"):
        validar(datos)

    datos["explicacion"]["ubicacion"]["archivo"] = "src/precios.ts"
    datos["explicacion"]["ubicacion"]["linea_inicio"] = 50
    datos["explicacion"]["ubicacion"]["linea_fin"] = 20
    with pytest.raises(ContratoInvalido, match="linea_fin: debe ser >= linea_inicio"):
        validar(datos)


def test_caso_m_schema_explicaciones_json() -> None:
    datos = fixture()
    corrida = datos["explicaciones_corrida"]

    # Objeto con version, tipo, run_id y lista de explicaciones
    assert contracts.validar(contracts.EXPLICACIONES, corrida) is corrida
    assert (
        contracts.validar_explicaciones(
            corrida, results_confiables=datos["results_confiables"]
        )
        is corrida
    )

    # Formato lista directa
    lista = corrida["explicaciones"]
    assert contracts.validar(contracts.EXPLICACIONES, lista) is lista
    assert (
        contracts.validar_explicaciones(
            lista, results_confiables=datos["results_confiables"]
        )
        is lista
    )


def test_caso_m_explicaciones_json_rechaza_elementos_invalidos() -> None:
    datos = fixture()
    corrida = copy.deepcopy(datos["explicaciones_corrida"])
    corrida["explicaciones"][0]["que_hacer"] = "Relajar la aserción para que pase"

    with pytest.raises(ContratoInvalido, match="relajar una aserción"):
        contracts.validar_explicaciones(
            corrida, results_confiables=datos["results_confiables"]
        )


def test_caso_n_version_desconocida_se_rechaza() -> None:
    datos = fixture()
    datos["explicacion"]["version"] = "2"

    with pytest.raises(ContratoInvalido) as error:
        contracts.validar_versionado(
            contracts.FAMILIA_EXPLANATION, datos["explicacion"]
        )

    assert error.value.errores[0].startswith("version:")


def test_caso_o_no_interfiere_con_contratos_existentes() -> None:
    planner = ejemplo(contracts.PLANNER_V3)
    review = ejemplo(contracts.REVIEW_RESULT)

    assert contracts.validar_versionado(contracts.FAMILIA_PLANNER, planner)
    assert contracts.validar(contracts.REVIEW_RESULT, review)
    assert "explanation" not in planner and "explanation" not in review
