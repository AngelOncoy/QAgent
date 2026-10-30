"""#199: contrato versionado del futuro Agente Recomendador."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from qagent import contracts


def recomendacion() -> dict[str, Any]:
    """Devuelve una copia del ejemplo oficial de ``recommendation.v1``."""
    ruta = contracts.DIR_CONTRATOS / "ejemplos" / f"{contracts.RECOMMENDATION_V1}.json"
    return json.loads(ruta.read_text(encoding="utf-8"))


def test_recomendacion_de_reglas_valida_y_conserva_el_orden() -> None:
    dato = recomendacion()

    assert contracts.validar(contracts.RECOMMENDATION_V1, dato) is dato
    assert [r["tipo_prueba"] for r in dato["recomendaciones"]] == [
        "endpoint",
        "funcion",
        "mutacion",
    ]


def test_recomendacion_de_ia_valida() -> None:
    dato = recomendacion()
    dato["origen"] = "ia"

    assert contracts.validar(contracts.RECOMMENDATION_V1, dato) is dato


def test_lista_vacia_es_valida_cuando_no_hay_capacidades_elegibles() -> None:
    dato = recomendacion()
    dato["recomendaciones"] = []

    assert contracts.es_valido(contracts.RECOMMENDATION_V1, dato)


def test_serializacion_y_deserializacion_conservan_el_contrato() -> None:
    dato = recomendacion()
    recuperado = json.loads(json.dumps(dato, ensure_ascii=False))

    assert recuperado == dato
    assert (
        contracts.validar_versionado(contracts.FAMILIA_RECOMMENDATION, recuperado)
        is recuperado
    )


def test_vocabulario_del_schema_coincide_con_la_constante_publica() -> None:
    schema = contracts.cargar_schema(contracts.RECOMMENDATION_V1)
    tipos = schema["properties"]["recomendaciones"]["items"]["properties"][
        "tipo_prueba"
    ]["enum"]

    assert tuple(tipos) == contracts.TIPOS_PRUEBA_RECOMENDABLES


@pytest.mark.parametrize("origen", ["plantilla", "modelo", "", 1, None])
def test_rechaza_origen_desconocido(origen: Any) -> None:
    dato = recomendacion()
    dato["origen"] = origen

    assert not contracts.es_valido(contracts.RECOMMENDATION_V1, dato)


@pytest.mark.parametrize("campo", ["version", "origen", "recomendaciones"])
def test_rechaza_campo_raiz_obligatorio_ausente(campo: str) -> None:
    dato = recomendacion()
    del dato[campo]

    with pytest.raises(contracts.ContratoInvalido):
        contracts.validar(contracts.RECOMMENDATION_V1, dato)


def test_rechaza_version_no_soportada_por_validar_y_por_familia() -> None:
    dato = recomendacion()
    dato["version"] = "2"

    assert not contracts.es_valido(contracts.RECOMMENDATION_V1, dato)
    with pytest.raises(contracts.ContratoInvalido):
        contracts.validar_versionado(contracts.FAMILIA_RECOMMENDATION, dato)


@pytest.mark.parametrize("recomendaciones", [None, {}, "funcion", ["funcion"]])
def test_rechaza_lista_de_recomendaciones_malformada(
    recomendaciones: Any,
) -> None:
    dato = recomendacion()
    dato["recomendaciones"] = recomendaciones

    assert not contracts.es_valido(contracts.RECOMMENDATION_V1, dato)


@pytest.mark.parametrize("campo", ["tipo_prueba", "motivo"])
def test_rechaza_campo_obligatorio_de_una_recomendacion_ausente(campo: str) -> None:
    dato = recomendacion()
    del dato["recomendaciones"][0][campo]

    assert not contracts.es_valido(contracts.RECOMMENDATION_V1, dato)


@pytest.mark.parametrize("motivo", ["", " ", "\t\n", None, 3])
def test_rechaza_motivo_vacio_o_de_tipo_incorrecto(motivo: Any) -> None:
    dato = recomendacion()
    dato["recomendaciones"][0]["motivo"] = motivo

    assert not contracts.es_valido(contracts.RECOMMENDATION_V1, dato)


@pytest.mark.parametrize("tipo_prueba", ["unitaria", "integracion", "e2e", "", None, 3])
def test_rechaza_tipo_de_prueba_fuera_del_vocabulario(tipo_prueba: Any) -> None:
    dato = recomendacion()
    dato["recomendaciones"][0]["tipo_prueba"] = tipo_prueba

    assert not contracts.es_valido(contracts.RECOMMENDATION_V1, dato)


@pytest.mark.parametrize(
    ("nivel", "campo", "valor"),
    [
        ("raiz", "start_run", True),
        ("raiz", "decision", "accept"),
        ("raiz", "api_key", "secreto"),
        ("recomendacion", "codigo", "def test(): pass"),
        ("recomendacion", "ejecutar", True),
        ("recomendacion", "ruta_absoluta", "C:/privado/proyecto"),
        ("recomendacion", "veredicto", "accept"),
    ],
)
def test_rechaza_campos_de_accion_veredicto_o_codigo(
    nivel: str, campo: str, valor: Any
) -> None:
    dato = recomendacion()
    destino = dato if nivel == "raiz" else dato["recomendaciones"][0]
    destino[campo] = valor

    assert not contracts.es_valido(contracts.RECOMMENDATION_V1, dato)


def test_rechaza_un_mismo_tipo_recomendado_dos_veces() -> None:
    dato = recomendacion()
    duplicada = copy.deepcopy(dato["recomendaciones"][0])
    duplicada["motivo"] = "Otro motivo para el mismo tipo."
    dato["recomendaciones"].append(duplicada)

    assert not contracts.es_valido(contracts.RECOMMENDATION_V1, dato)


def test_schema_y_ejemplo_se_cargan_como_recursos_del_paquete() -> None:
    assert contracts.ruta_schema(contracts.RECOMMENDATION_V1).is_file()
    assert recomendacion()["version"] == "1"


def test_ejemplo_no_contiene_secretos_rutas_absolutas_ni_codigo() -> None:
    texto = json.dumps(recomendacion(), ensure_ascii=False).lower()

    assert not any(
        prohibido in texto
        for prohibido in ("api_key", "password", "token", ".env", "c:/", "c:\\\\")
    )
    assert "def test" not in texto
