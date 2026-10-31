"""#194: verificar correcciones con la misma prueba, firma estática y cero IA."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from qagent import contracts
from qagent.almacenamiento import AlmacenProyecto, ErrorAlmacen
from qagent.config import cargar_configuracion
from qagent.config.carga import RUTA_CONFIG
from qagent.orchestrator.verificacion_correccion import (
    ejecutar_verificacion_correccion,
    inspeccionar_verificacion,
)
from qagent.sandbox import ResultadoSandbox

ORIGEN = "20261030-100000-abcd"
VERIFICACION = "20261030-110000-ef01"
CODIGO = (
    "from modulo import calcular\n\ndef test_calcular():\n    assert calcular(2) == 4\n"
)


@pytest.fixture
def config():
    return cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config


def _contrato(firma: str = "(x: int) -> int") -> dict:
    ruta = contracts.DIR_CONTRATOS / "ejemplos" / "planner_contract.v2.json"
    contrato = json.loads(ruta.read_text(encoding="utf-8"))
    contrato.update(
        modulo="modulo.py",
        objetivo="calcular",
        firma=firma,
        huella="1" * 64,
        critical=False,
    )
    contrato["casos"] = [
        {
            "id": "duplica",
            "entrada": {"x": 2},
            "valor_esperado": 4,
            "origen": "docstring",
            "categoria": "normal",
        }
    ]
    return contrato


def _crear_run(almacen: AlmacenProyecto, run_id: str) -> None:
    almacen.guardar_run(
        {
            "run_id": run_id,
            "inicio": "2026-10-30T10:00:00+00:00",
            "fin": None,
            "tipos_prueba": ["funcion"],
            "imagen_docker": None,
            "estado": "en_curso",
            "resumen": None,
        }
    )


def _preparar_origen(
    raiz: Path,
    *,
    decision: str = "bug_detectado",
    codigo: str | None = CODIGO,
    contrato: dict | None = None,
) -> AlmacenProyecto:
    (raiz / "modulo.py").write_text(
        "def calcular(x: int) -> int:\n    return x + x\n", encoding="utf-8"
    )
    almacen = AlmacenProyecto(raiz)
    _crear_run(almacen, ORIGEN)
    contrato = contrato or _contrato()
    objetivo = {
        "modulo": "modulo.py",
        "funcion": "calcular",
        "tipo": "funcion",
        "decision": decision,
    }
    carpeta = almacen.carpeta_run(ORIGEN)
    (carpeta / "results.json").write_text(
        json.dumps({"run_id": ORIGEN, "objetivos": [objetivo]}), encoding="utf-8"
    )
    if decision == "bug_detectado" and codigo is not None:
        almacen.guardar_evidencia_bug(contrato, codigo, ORIGEN)
    (carpeta / "detalle.json").write_text(
        json.dumps(
            {
                "run_id": ORIGEN,
                "funciones": [
                    {
                        "modulo": "modulo.py",
                        "funcion": "calcular",
                        "contrato": contrato,
                        "codigo": codigo,
                        "intentos": [{"decision": decision}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return almacen


def _ejecutar(
    raiz: Path,
    almacen: AlmacenProyecto,
    config,
    salida: ResultadoSandbox,
    llamadas: list[str] | None = None,
):
    _crear_run(almacen, VERIFICACION)

    def ejecutor(_imagen, _proyecto, tests, _modulo):
        texto = next(Path(tests).glob("test_*.py")).read_text(encoding="utf-8")
        if llamadas is not None:
            llamadas.append(texto)
        return salida

    resumen = ejecutar_verificacion_correccion(
        raiz,
        ORIGEN,
        config,
        run_id=VERIFICACION,
        preparar_imagen=lambda _ruta: "imagen",
        ejecutor=ejecutor,
    )
    assert resumen.estado == "fin", resumen.motivo
    return resumen, almacen.leer_comparacion(ORIGEN, VERIFICACION)


def test_cuerpo_modificado_misma_firma_ejecuta_prueba_original(
    tmp_path, config
) -> None:
    almacen = _preparar_origen(tmp_path)
    (tmp_path / "modulo.py").write_text(
        "def calcular(x: int) -> int:\n    return x * 2\n", encoding="utf-8"
    )
    llamadas: list[str] = []

    resumen, comparacion = _ejecutar(
        tmp_path, almacen, config, ResultadoSandbox(0, "1 passed", ""), llamadas
    )

    assert llamadas == [CODIGO]
    assert resumen.tokens == resumen.tokens_reales == resumen.tokens_estimados == 0
    assert comparacion["comparaciones"][0]["resultado"] == "corregido"
    assert comparacion["run_origen_id"] == ORIGEN
    assert comparacion["run_verificacion_id"] == VERIFICACION


def test_bug_persistente_usa_misma_prueba(tmp_path, config) -> None:
    almacen = _preparar_origen(tmp_path)

    _, comparacion = _ejecutar(
        tmp_path, almacen, config, ResultadoSandbox(1, "assert 2 == 4", "")
    )

    assert comparacion["comparaciones"][0]["resultado"] == "sigue_fallando"


def test_prueba_aprobada_que_falla_es_regresion(tmp_path, config) -> None:
    almacen = _preparar_origen(tmp_path, decision="accept")

    _, comparacion = _ejecutar(
        tmp_path, almacen, config, ResultadoSandbox(1, "assert 3 == 4", "")
    )

    assert comparacion["comparaciones"][0]["resultado"] == "regresion"


@pytest.mark.parametrize(
    ("fuente", "texto"),
    [
        ("def calcular(x: int, y: int) -> int:\n    return x + y\n", "firma cambió"),
        ("def otro(x: int) -> int:\n    return x * 2\n", "eliminado o renombrado"),
        ("def calcular(:\n", "determinar la firma"),
    ],
)
def test_firma_incompatible_ausente_o_inanalizable_no_ejecuta(
    tmp_path, config, fuente, texto
) -> None:
    almacen = _preparar_origen(tmp_path)
    (tmp_path / "modulo.py").write_text(fuente, encoding="utf-8")
    llamadas: list[str] = []

    _, comparacion = _ejecutar(
        tmp_path, almacen, config, ResultadoSandbox(0, "", ""), llamadas
    )

    [item] = comparacion["comparaciones"]
    assert llamadas == []
    assert item["resultado"] == "no_comparable"
    assert texto in item["motivo"]
    assert item["estado_posterior"]["referencia_resultado"].endswith("results.json")


def test_prueba_aprobada_ausente_se_registra_no_comparable(tmp_path, config) -> None:
    almacen = _preparar_origen(tmp_path, decision="accept", codigo=None)

    _, comparacion = _ejecutar(tmp_path, almacen, config, ResultadoSandbox(0, "", ""))

    [item] = comparacion["comparaciones"]
    assert item["resultado"] == "no_comparable"
    assert "no conserva el código" in item["motivo"]
    assert item["prueba"]["huella_origen"] is None


def test_evidencia_bug_alterada_respecto_de_su_hash_no_se_ejecuta(
    tmp_path, config
) -> None:
    almacen = _preparar_origen(tmp_path)
    ruta = next(almacen.carpeta_evidencias_bugs.rglob("*.json"))
    evidencia = json.loads(ruta.read_text(encoding="utf-8"))
    evidencia["codigo_prueba"] += "\n# alterada\n"
    ruta.write_text(json.dumps(evidencia), encoding="utf-8")
    llamadas: list[str] = []

    _, comparacion = _ejecutar(
        tmp_path, almacen, config, ResultadoSandbox(0, "", ""), llamadas
    )

    assert llamadas == []
    assert comparacion["comparaciones"][0]["resultado"] == "no_comparable"
    assert "inválida" in comparacion["comparaciones"][0]["motivo"]


@pytest.mark.parametrize(
    ("firma", "fuente"),
    [
        (
            "(x: int=1, *, escala: int=2) -> int",
            (
                "def calcular(x: int = 1, *, escala: int = 2) -> int:\n"
                "    return x * escala\n"
            ),
        ),
        (
            "(x: int, /, y: int=1) -> int",
            "async def calcular(x: int, /, y: int = 1) -> int:\n    return x + y\n",
        ),
    ],
)
def test_firmas_soportadas_con_defaults_keyword_only_posicionales_y_async(
    tmp_path, firma, fuente
) -> None:
    _preparar_origen(tmp_path, contrato=_contrato(firma))
    (tmp_path / "modulo.py").write_text(fuente, encoding="utf-8")

    inspeccion = inspeccionar_verificacion(tmp_path, ORIGEN)

    assert inspeccion["ejecutables"] == 1
    assert inspeccion["no_comparables"] == 0


def test_homonimas_en_modulos_distintos_y_accept_mas_bug_no_se_mezclan(
    tmp_path,
) -> None:
    almacen = _preparar_origen(tmp_path)
    (tmp_path / "otro.py").write_text(
        "def calcular(x: int) -> int:\n    return x * 2\n", encoding="utf-8"
    )
    carpeta = almacen.carpeta_run(ORIGEN)
    resultados = json.loads((carpeta / "results.json").read_text(encoding="utf-8"))
    resultados["objetivos"].append(
        {
            "modulo": "otro.py",
            "funcion": "calcular",
            "tipo": "funcion",
            "decision": "accept",
        }
    )
    (carpeta / "results.json").write_text(json.dumps(resultados), encoding="utf-8")
    detalle = json.loads((carpeta / "detalle.json").read_text(encoding="utf-8"))
    contrato = _contrato()
    contrato["modulo"] = "otro.py"
    detalle["funciones"].append(
        {
            "modulo": "otro.py",
            "funcion": "calcular",
            "contrato": contrato,
            "codigo": CODIGO.replace("from modulo", "from otro"),
            "intentos": [{"decision": "accept"}],
        }
    )
    (carpeta / "detalle.json").write_text(json.dumps(detalle), encoding="utf-8")

    inspeccion = inspeccionar_verificacion(tmp_path, ORIGEN)

    assert inspeccion == {
        "run_origen_id": ORIGEN,
        "total": 2,
        "ejecutables": 2,
        "no_comparables": 0,
        "motivos": [],
    }


def test_error_de_infraestructura_no_declara_bug(tmp_path, config) -> None:
    almacen = _preparar_origen(tmp_path)

    _, comparacion = _ejecutar(
        tmp_path,
        almacen,
        config,
        ResultadoSandbox(124, "", "timeout", timed_out=True),
    )

    [item] = comparacion["comparaciones"]
    assert item["resultado"] == "no_comparable"
    assert item["estado_posterior"]["confiable"] is False


def test_no_crea_clientes_llm_ni_modifica_evidencia(
    tmp_path, config, monkeypatch
) -> None:
    almacen = _preparar_origen(tmp_path)
    evidencia = next(almacen.carpeta_evidencias_bugs.rglob("*.json"))
    antes = evidencia.read_bytes()

    def prohibido(*_args, **_kwargs):
        raise AssertionError("La verificación no puede crear clientes LLM")

    monkeypatch.setattr("qagent.llm.crear_cliente", prohibido)
    resumen, _ = _ejecutar(
        tmp_path, almacen, config, ResultadoSandbox(0, "1 passed", "")
    )

    assert resumen.tokens == 0
    assert evidencia.read_bytes() == antes


def test_solo_recupera_pruebas_de_la_corrida_elegida(tmp_path) -> None:
    almacen = _preparar_origen(tmp_path)
    otro = "20261030-103000-bbbb"
    _crear_run(almacen, otro)
    contrato = _contrato()
    contrato["objetivo"] = "ajena"
    almacen.guardar_evidencia_bug(
        contrato, "def test_ajena():\n    assert True\n", otro
    )

    inspeccion = inspeccionar_verificacion(tmp_path, ORIGEN)

    assert inspeccion["total"] == 1


def test_corrida_inexistente_o_sin_pruebas_no_inicia(tmp_path) -> None:
    almacen = AlmacenProyecto(tmp_path)
    with pytest.raises(ErrorAlmacen):
        inspeccionar_verificacion(tmp_path, ORIGEN)

    _crear_run(almacen, ORIGEN)
    (almacen.carpeta_run(ORIGEN) / "results.json").write_text(
        json.dumps({"run_id": ORIGEN, "objetivos": []}), encoding="utf-8"
    )
    with pytest.raises(ErrorAlmacen, match="no contiene pruebas"):
        inspeccionar_verificacion(tmp_path, ORIGEN)


def test_cancelacion_persiste_no_comparable_sin_ejecutar(tmp_path, config) -> None:
    almacen = _preparar_origen(tmp_path)
    _crear_run(almacen, VERIFICACION)
    llamadas: list[str] = []

    resumen = ejecutar_verificacion_correccion(
        tmp_path,
        ORIGEN,
        config,
        run_id=VERIFICACION,
        preparar_imagen=lambda _ruta: "imagen",
        ejecutor=lambda *_args: llamadas.append("ejecuto"),
        cancelado=lambda: True,
    )

    assert resumen.cancelada is True
    assert llamadas == []
    assert (
        almacen.leer_comparacion(ORIGEN, VERIFICACION)["comparaciones"][0]["resultado"]
        == "no_comparable"
    )


def test_contrato_permita_metadatos_ausentes_solo_en_no_comparable() -> None:
    ruta = contracts.DIR_CONTRATOS / "ejemplos" / "run_comparison.v1.json"
    dato = json.loads(ruta.read_text(encoding="utf-8"))
    item = dato["comparaciones"][0]
    item["resultado"] = "no_comparable"
    item["motivo"] = "La prueba original está ausente."
    item["prueba"]["huella_origen"] = None
    item["prueba"]["huella_verificacion"] = None
    item["firma_origen"] = None
    item["firma_verificacion"] = None
    item["estado_posterior"].update(decision="requiere_corrida_nueva", confiable=False)

    assert contracts.validar_comparacion(dato) == dato

    invalido = copy.deepcopy(dato)
    invalido["comparaciones"][0]["resultado"] = "corregido"
    invalido["comparaciones"][0]["motivo"] = None
    invalido["comparaciones"][0]["estado_posterior"].update(
        decision="accept", confiable=True
    )
    with pytest.raises(contracts.ContratoInvalido):
        contracts.validar_comparacion(invalido)
