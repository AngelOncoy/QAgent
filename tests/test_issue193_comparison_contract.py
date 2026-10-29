"""#193: schema y validación semántica de comparaciones entre corridas."""

from __future__ import annotations

import copy
import json

import pytest

from qagent import contracts


def comparacion() -> dict:
    ruta = contracts.DIR_CONTRATOS / "ejemplos" / "run_comparison.v1.json"
    return json.loads(ruta.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("resultado", "anterior", "posterior"),
    [
        ("corregido", "bug_detectado", "accept"),
        ("sigue_fallando", "bug_detectado", "bug_detectado"),
        ("regresion", "accept", "bug_detectado"),
    ],
)
def test_acepta_los_tres_estados_concluyentes(resultado, anterior, posterior) -> None:
    dato = comparacion()
    item = dato["comparaciones"][0]
    item["resultado"] = resultado
    item["estado_anterior"]["decision"] = anterior
    item["estado_posterior"]["decision"] = posterior

    assert contracts.validar_comparacion(dato) is dato


def test_no_comparable_exige_motivo() -> None:
    dato = comparacion()
    item = dato["comparaciones"][0]
    item.update(resultado="no_comparable", motivo="La firma cambió.")
    item["firma_verificacion"] = "(precio: float) -> float"

    assert contracts.validar_comparacion(dato) is dato
    item["motivo"] = ""
    with pytest.raises(contracts.ContratoInvalido):
        contracts.validar_comparacion(dato)


@pytest.mark.parametrize(
    "cambio",
    [
        lambda d: d.pop("version"),
        lambda d: d.update(version="2"),
        lambda d: d["comparaciones"][0].update(resultado="inventado"),
        lambda d: d["comparaciones"][0].pop("objetivo"),
        lambda d: d["comparaciones"][0]["prueba"].pop("huella_origen"),
    ],
)
def test_rechaza_estructura_invalida(cambio) -> None:
    dato = comparacion()
    cambio(dato)

    with pytest.raises(contracts.ContratoInvalido):
        contracts.validar_comparacion(dato)


def test_rechaza_resultado_contradictorio() -> None:
    dato = comparacion()
    dato["comparaciones"][0]["estado_posterior"]["decision"] = "bug_detectado"

    with pytest.raises(contracts.ContratoInvalido):
        contracts.validar_comparacion(dato)


@pytest.mark.parametrize("campo", ["firma", "prueba", "referencia"])
def test_comparacion_concluyente_exige_misma_evidencia(campo: str) -> None:
    dato = comparacion()
    item = dato["comparaciones"][0]
    if campo == "firma":
        item["firma_verificacion"] = "(otro: int) -> int"
    elif campo == "prueba":
        item["prueba"]["huella_verificacion"] = "f" * 64
    else:
        item["estado_posterior"]["referencia_resultado"] = "runs/otro/results.json"

    with pytest.raises(contracts.ContratoInvalido):
        contracts.validar_comparacion(dato)


def test_rechaza_runs_iguales_y_objetivos_duplicados() -> None:
    dato = comparacion()
    dato["run_verificacion_id"] = dato["run_origen_id"]
    dato["comparaciones"].append(copy.deepcopy(dato["comparaciones"][0]))

    with pytest.raises(contracts.ContratoInvalido) as error:
        contracts.validar_comparacion(dato)

    assert any("distinto" in mensaje for mensaje in error.value.errores)
    assert any("duplicado" in mensaje for mensaje in error.value.errores)
