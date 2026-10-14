"""Pruebas unitarias para la IA simulada y contabilidad de 0 tokens (EN-11)."""

import json
from pathlib import Path

import pytest

from qagent.llm import (
    FakeLLMClient,
    TokenTracker,
    es_modo_simulado,
    obtener_cliente_llm,
)


def test_modo_simulado_activado(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica que QAGENT_FAKE_LLM=1 activa el modo simulado y retorna FakeLLMClient."""
    monkeypatch.setenv("QAGENT_FAKE_LLM", "1")
    assert es_modo_simulado() is True

    cliente = obtener_cliente_llm(modelo="test-model")
    assert isinstance(cliente, FakeLLMClient)
    assert cliente.modelo == "test-model"


def test_modo_simulado_desactivado(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifica que sin QAGENT_FAKE_LLM=1 no se active la simulación."""
    monkeypatch.setenv("QAGENT_FAKE_LLM", "0")
    assert es_modo_simulado() is False

    with pytest.raises(NotImplementedError):
        obtener_cliente_llm()


def test_respuestas_grabadas_consumen_cero_tokens() -> None:
    """Verifica que las respuestas grabadas reporten estrictamente 0 tokens y costo 0."""
    cliente = FakeLLMClient(modelo="simulado-v1")

    for rol in ["planner", "generator", "reviewer"]:
        respuesta = cliente.generar(prompt="probar función", rol=rol)
        assert len(respuesta.contenido) > 0
        assert respuesta.tokens_entrada == 0
        assert respuesta.tokens_salida == 0
        assert respuesta.costo_usd == 0.0


def test_corrida_completa_registra_cero_tokens_en_log_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Evidencia de aceptación: una corrida completa registra 0 tokens y 0 costo en log.json."""
    monkeypatch.setenv("QAGENT_FAKE_LLM", "1")
    cliente = obtener_cliente_llm(modelo="fake-pipeline")
    tracker = TokenTracker()

    # Simular ciclo de los 3 agentes (Planner -> Generator -> Reviewer)
    roles = ["planner", "generator", "reviewer"]
    for rol in roles:
        res = cliente.generar(prompt=f"tarea de {rol}", rol=rol)
        tracker.registrar(
            agente=rol,
            modelo=res.modelo,
            tokens_entrada=res.tokens_entrada,
            tokens_salida=res.tokens_salida,
            costo_usd=res.costo_usd,
            es_simulado=True,
        )

    # 1. Comprobación en memoria
    assert tracker.total_tokens == 0
    assert tracker.total_costo_usd == 0.0
    assert len(tracker.llamadas) == 3

    # 2. Comprobación en archivo log.json persistido
    ruta_log = tmp_path / "log.json"
    resumen = tracker.guardar_log(ruta_log)

    assert ruta_log.exists()
    assert resumen["total_tokens"] == 0
    assert resumen["total_costo_usd"] == 0.0
    assert resumen["es_simulado"] is True

    # Verificar lectura directa del archivo JSON
    with open(ruta_log, "r", encoding="utf-8") as f:
        datos_disco = json.load(f)

    assert datos_disco["total_tokens"] == 0
    assert datos_disco["total_costo_usd"] == 0.0
    assert datos_disco["total_llamadas"] == 3


CONTRATO_BANCO = {
    "version": "2",
    "modulo": "bench/banco_mvp.py",
    "huella": "0" * 64,
    "tipo": "funcion",
    "objetivo": "calcular_descuento",
    "firma": "(precio: float, porcentaje: float) -> float",
    "critical": False,
    "llama_a": [],
    "casos": [
        {
            "id": "descuento_normal",
            "entrada": {"precio": 100.0, "porcentaje": 20.0},
            "valor_esperado": 80.0,
            "origen": "docstring",
        },
        {
            "id": "precio_negativo",
            "entrada": {"precio": -1.0, "porcentaje": 10.0},
            "excepcion": "ValueError",
            "origen": "docstring",
        },
    ],
}

CONTRATO_ENDPOINT = {
    "version": "2",
    "modulo": "api_mvp.py",
    "huella": "a" * 64,
    "tipo": "endpoint",
    "objetivo": "POST /items",
    "manejador": "crear_item",
    "aplicacion": "app",
    "dependencias": [{"funcion": "obtener_repositorio", "reemplazo": "Repositorio"}],
    "firma": "(datos: ItemEntrada, repo=Depends(obtener_repositorio)) -> Item",
    "critical": False,
    "llama_a": [],
    "casos": [
        {
            "id": "crear_item",
            "entrada": {
                "metodo": "POST",
                "ruta": "/items",
                "json": {"nombre": "lapiz", "precio": 2.5},
            },
            "valor_esperado": {
                "status_code": 201,
                "json_contiene": {"nombre": "lapiz", "precio": 2.5},
            },
            "origen": "response_model",
        }
    ],
}


def test_planner_simulado_usa_los_casos_grabados_del_modulo() -> None:
    grabados = [CONTRATO_BANCO["casos"][0]]
    cliente = FakeLLMClient(grabaciones={"banco_mvp.py::calcular_descuento": grabados})
    prompt = (
        "MODULO: bench/banco_mvp.py\n"
        'OBJETIVOS_JSON: [{"nombre": "calcular_descuento"}, {"nombre": "sin_grabar"}]'
    )

    plan = json.loads(cliente.generar(prompt, rol="planner").contenido)

    assert plan == [{"objetivo": "calcular_descuento", "casos": grabados}]


def test_generator_simulado_arma_el_test_desde_el_contrato() -> None:
    import ast

    cliente = FakeLLMClient(grabaciones={})
    prompt = "Escribe...\nCONTRATO_JSON: " + json.dumps(CONTRATO_BANCO)

    codigo = cliente.generar(prompt, rol="generator").contenido

    ast.parse(codigo)
    assert "from bench.banco_mvp import calcular_descuento" in codigo
    assert (
        "assert calcular_descuento(precio=100.0, porcentaje=20.0) "
        "== pytest.approx(80.0)" in codigo
    )
    assert "with pytest.raises(ValueError):" in codigo


def test_generator_simulado_arma_testclient_y_restaura_overrides() -> None:
    import ast

    prompt = "Escribe...\nCONTRATO_JSON: " + json.dumps(CONTRATO_ENDPOINT)

    respuesta = FakeLLMClient(grabaciones={}).generar(prompt, rol="generator")
    codigo = respuesta.contenido

    ast.parse(codigo)
    assert "from fastapi.testclient import TestClient" in codigo
    assert "from api_mvp import app, obtener_repositorio, Repositorio" in codigo
    assert "doble_obtener_repositorio = Repositorio()" in codigo
    assert (
        "app.dependency_overrides[obtener_repositorio] = "
        "lambda: doble_obtener_repositorio" in codigo
    )
    assert "try:" in codigo and "finally:" in codigo
    assert "app.dependency_overrides.clear()" in codigo
    assert "app.dependency_overrides.update(overrides_anteriores)" in codigo
    assert "client.request('POST', '/items'" in codigo
    assert "assert response.status_code == 201" in codigo
    assert "assert cuerpo['nombre'] == 'lapiz'" in codigo
    assert respuesta.tokens_entrada == respuesta.tokens_salida == 0
    assert respuesta.costo_usd == 0.0


def test_generator_simulado_prepara_el_estado_de_la_dependencia() -> None:
    contrato = json.loads(json.dumps(CONTRATO_ENDPOINT))
    contrato["casos"][0]["entrada"]["preparacion"] = [
        {
            "dependencia": "obtener_repositorio",
            "metodo": "crear",
            "modelo": "ItemEntrada",
            "argumentos": {"nombre": "lapiz", "precio": 2.5},
        }
    ]
    prompt = "Escribe...\nCONTRATO_JSON: " + json.dumps(contrato)

    codigo = FakeLLMClient(grabaciones={}).generar(prompt, rol="generator").contenido

    assert "ItemEntrada" in codigo
    assert (
        "doble_obtener_repositorio.crear("
        "ItemEntrada(nombre='lapiz', precio=2.5))" in codigo
    )


def test_planner_simulado_reconoce_clave_de_endpoint() -> None:
    casos = CONTRATO_ENDPOINT["casos"]
    cliente = FakeLLMClient(grabaciones={"api_mvp.py::POST /items": casos})
    prompt = 'MODULO: api_mvp.py\nOBJETIVOS_JSON: [{"objetivo": "POST /items"}]'

    plan = json.loads(cliente.generar(prompt, rol="planner").contenido)

    assert plan == [{"objetivo": "POST /items", "casos": casos}]


def test_el_banco_tiene_casos_grabados_para_todas_sus_funciones() -> None:
    from qagent.analysis.analyzer import analizar_proyecto
    from qagent.llm.fake import RUTA_GRABACIONES, cargar_grabaciones

    grabaciones = cargar_grabaciones(RUTA_GRABACIONES)
    banco = Path(__file__).resolve().parents[2] / "bench"
    [modulo] = analizar_proyecto(banco)["modulos"]

    for funcion in modulo["funciones"]:
        assert grabaciones.get(f"banco_mvp.py::{funcion['nombre']}"), funcion["nombre"]


def test_el_banco_api_tiene_grabacion_para_cada_endpoint() -> None:
    from qagent.analysis.analyzer import analizar_proyecto
    from qagent.llm.fake import RUTA_GRABACIONES, cargar_grabaciones

    raiz = Path(__file__).resolve().parents[2]
    grabaciones = cargar_grabaciones(RUTA_GRABACIONES)
    [modulo] = analizar_proyecto(raiz / "bench_api")["modulos"]

    for endpoint in modulo["endpoints"]:
        clave = f"api_mvp.py::{endpoint['objetivo']}"
        assert grabaciones.get(clave), clave
