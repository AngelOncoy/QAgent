"""#193: persistencia separada y segura de pruebas que detectaron bugs."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from qagent import contracts
from qagent.almacenamiento import AlmacenProyecto, DatoCorrupto, ErrorAlmacen

RUN_ID = "20261029-120000-abcd"
MOMENTO = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc)
CODIGO = "def test_descuento():\n    assert calcular_descuento(100, 20) == 80\n"
CONTRATO = json.loads(
    (contracts.DIR_CONTRATOS / "ejemplos" / "planner_contract.v2.json").read_text(
        encoding="utf-8"
    )
)


@pytest.fixture
def almacen(tmp_path: Path) -> AlmacenProyecto:
    resultado = AlmacenProyecto(tmp_path)
    resultado.guardar_run(
        {
            "run_id": RUN_ID,
            "inicio": MOMENTO.isoformat(),
            "fin": None,
            "tipos_prueba": ["funcion"],
            "imagen_docker": None,
            "estado": "en_curso",
            "resumen": None,
        }
    )
    return resultado


def test_guarda_codigo_spec_firma_y_run_en_directorio_separado(almacen) -> None:
    evidencia = almacen.guardar_evidencia_bug(CONTRATO, CODIGO, RUN_ID, ahora=MOMENTO)

    assert evidencia["decision"] == "bug_detectado"
    assert evidencia["categoria"] == "evidencia_bug"
    assert evidencia["codigo_prueba"] == CODIGO
    assert evidencia["spec"] == CONTRATO
    assert evidencia["firma"] == CONTRATO["firma"]
    assert evidencia["run_id"] == RUN_ID
    assert evidencia["huella_prueba"]
    ruta = almacen.carpeta_evidencias_bugs / RUN_ID / f"{evidencia['id']}.json"
    assert ruta.is_file()
    assert ruta.is_relative_to(almacen.carpeta)
    assert almacen.leer_evidencia_bug(RUN_ID, evidencia["id"]) == evidencia


def test_evidencia_no_aparece_como_prueba_aprobada(almacen) -> None:
    almacen.guardar_evidencia_bug(CONTRATO, CODIGO, RUN_ID)

    assert almacen.listar_pruebas_aprobadas() == []
    assert almacen.tiene_pruebas_aprobadas() is False
    assert len(almacen.listar_evidencias_bug()) == 1


def test_mismo_guardado_es_idempotente_y_no_cambia_procedencia(almacen) -> None:
    primera = almacen.guardar_evidencia_bug(CONTRATO, CODIGO, RUN_ID, ahora=MOMENTO)
    segunda = almacen.guardar_evidencia_bug(CONTRATO, CODIGO, RUN_ID)

    assert segunda == primera
    assert len(almacen.listar_evidencias_bug()) == 1


def test_no_sobrescribe_una_evidencia_inmutable(almacen) -> None:
    almacen.guardar_evidencia_bug(CONTRATO, CODIGO, RUN_ID)

    with pytest.raises(ErrorAlmacen, match="no coincide"):
        almacen.guardar_evidencia_bug(CONTRATO, CODIGO + "# cambiado\n", RUN_ID)


@pytest.mark.parametrize(
    ("contrato", "codigo", "run_id"),
    [
        ({**CONTRATO, "firma": ""}, CODIGO, RUN_ID),
        (CONTRATO, "", RUN_ID),
        (CONTRATO, CODIGO, "../../fuera"),
        (CONTRATO, CODIGO, "20261029-130000-bbbb"),
    ],
)
def test_rechaza_evidencia_invalida_sin_escribir(
    almacen, contrato, codigo, run_id
) -> None:
    with pytest.raises((ErrorAlmacen, contracts.ContratoInvalido)):
        almacen.guardar_evidencia_bug(contrato, codigo, run_id)

    assert almacen.listar_evidencias_bug() == []


def test_valida_que_firma_y_objetivo_procedan_de_la_spec(almacen) -> None:
    evidencia = almacen.guardar_evidencia_bug(CONTRATO, CODIGO, RUN_ID)
    ruta = almacen.carpeta_evidencias_bugs / RUN_ID / f"{evidencia['id']}.json"
    alterada = copy.deepcopy(evidencia)
    alterada["firma"] = "(inventada: str) -> str"
    ruta.write_text(json.dumps(alterada), encoding="utf-8")

    with pytest.raises(DatoCorrupto, match="firma"):
        almacen.leer_evidencia_bug(RUN_ID, evidencia["id"])


def test_error_de_disco_no_deja_registro_parcial(almacen, monkeypatch) -> None:
    def falla(*_args, **_kwargs):
        raise OSError("disco lleno")

    monkeypatch.setattr("qagent.almacenamiento.proyecto.escribir_json_atomico", falla)

    with pytest.raises(OSError, match="disco lleno"):
        almacen.guardar_evidencia_bug(CONTRATO, CODIGO, RUN_ID)

    assert almacen.listar_evidencias_bug() == []
