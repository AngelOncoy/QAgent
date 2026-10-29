"""El Explicador con IA dentro de la corrida (#166): tokens en log.json y respaldo.

Usa la IA simulada y el ejecutor simulado de `test_corrida`: no ejecuta código ni
llama a una API real.
"""

from __future__ import annotations

import dataclasses
import logging
import shutil
from pathlib import Path

import pytest

from qagent import contracts
from qagent.almacenamiento import AlmacenProyecto
from qagent.config import cargar_configuracion
from qagent.config.carga import RUTA_CONFIG, Explicador
from qagent.llm import PrecioAgente
from qagent.storage.registro import ARCHIVO_EXPLICACIONES
from tests.orchestrator.test_corrida import BANCO, CON_BUG
from tests.orchestrator.test_hu32_explicador_corrida import _leer, correr

PRECIO = PrecioAgente("explicador", "openai", "modelo-explicador", 0.10, 0.50)


@pytest.fixture
def proyecto(tmp_path: Path) -> AlmacenProyecto:
    carpeta = tmp_path / "banco"
    shutil.copytree(
        BANCO, carpeta, ignore=shutil.ignore_patterns("*.md", "*.json", ".qagent")
    )
    almacen = AlmacenProyecto(carpeta)
    almacen.inicializar()
    return almacen


@pytest.fixture
def config():
    return cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config


@pytest.fixture
def config_ia(config):
    return dataclasses.replace(
        config, explicador=Explicador(modo="ia", precio=PRECIO, tiempo_maximo_s=5)
    )


def test_modo_ia_explica_con_la_ia_y_registra_al_explicador(proyecto, config_ia):
    resumen, carpeta = correr(proyecto, config_ia)

    assert resumen.estado == "fin", resumen.motivo
    results = _leer(carpeta, "results.json")
    datos = _leer(carpeta, ARCHIVO_EXPLICACIONES)
    contracts.validar_explicaciones(datos, results_confiables=results)
    assert sorted(e["objetivo"] for e in datos["explicaciones"]) == sorted(CON_BUG)
    assert all(e["origen"] == "ia" for e in datos["explicaciones"])
    assert all(e["modelo"] == "modelo-explicador" for e in datos["explicaciones"])

    log = _leer(carpeta, "log.json")
    contracts.validar(contracts.RUN_LOG, log)
    explicador = log["totales_por_agente"]["explicador"]
    assert explicador["llamadas"] == len(CON_BUG)
    assert [ll["funcion"] for ll in log["llamadas"] if ll["agente"] == "explicador"]
    assert results["resumen"]["por_agente"] == log["totales_por_agente"]
    assert resumen.tokens == log["total_tokens"]
    assert resumen.costo_usd == log["total_costo_usd"]


def test_modo_ia_no_cambia_los_veredictos(proyecto, config, config_ia):
    _, con_plantilla = correr(proyecto, config)
    _, con_ia = correr(proyecto, config_ia)

    def veredictos(carpeta):
        return [
            (o["funcion"], o["decision"], o["laundering_detectado"], o["metricas"])
            for o in _leer(carpeta, "results.json")["objetivos"]
        ]

    assert veredictos(con_ia) == veredictos(con_plantilla)


def test_sin_clave_usa_la_plantilla_y_lo_registra(
    proyecto, config_ia, monkeypatch, caplog
):
    from qagent.llm.fabrica import ConfiguracionLLMIncompleta
    from qagent.orchestrator import corrida

    original = corrida.crear_cliente

    def sin_clave_para_el_explicador(precio, *args, **kwargs):
        if precio.agente == "explicador":
            raise ConfiguracionLLMIncompleta(
                "Falta la clave OPENAI_API_KEY_EXPLICADOR en .env para el explicador."
            )
        return original(precio, *args, **kwargs)

    monkeypatch.setattr(corrida, "crear_cliente", sin_clave_para_el_explicador)

    with caplog.at_level(logging.WARNING, logger="qagent.corrida"):
        resumen, carpeta = correr(proyecto, config_ia)

    assert resumen.estado == "fin", resumen.motivo
    datos = _leer(carpeta, ARCHIVO_EXPLICACIONES)
    assert all(e["origen"] == "plantilla" for e in datos["explicaciones"])
    assert "explicador" not in _leer(carpeta, "log.json")["totales_por_agente"]
    assert "El Explicador usa la plantilla" in caplog.text


def test_error_del_llm_se_registra_y_la_corrida_termina(
    proyecto, config_ia, monkeypatch, caplog
):
    from qagent.llm.fake import FakeLLMClient

    original = FakeLLMClient.generar

    def falla_como_explicador(self, prompt, rol="generator"):
        if rol == "explicador":
            raise TimeoutError("el proveedor no respondió")
        return original(self, prompt, rol)

    monkeypatch.setattr(FakeLLMClient, "generar", falla_como_explicador)

    with caplog.at_level(logging.WARNING, logger="qagent.corrida"):
        resumen, carpeta = correr(proyecto, config_ia)

    assert resumen.estado == "fin", resumen.motivo
    assert proyecto.leer_run(resumen.run_id)["estado"] == "fin"
    datos = _leer(carpeta, ARCHIVO_EXPLICACIONES)
    assert all(e["origen"] == "plantilla" for e in datos["explicaciones"])
    assert "Explicación con plantilla" in caplog.text
    assert "TimeoutError" in caplog.text


def test_presupuesto_agotado_usa_la_plantilla(proyecto, config_ia):
    presupuesto = dataclasses.replace(config_ia.presupuesto, max_tokens_por_corrida=10)
    _, carpeta = correr(
        proyecto, dataclasses.replace(config_ia, presupuesto=presupuesto)
    )

    datos = _leer(carpeta, ARCHIVO_EXPLICACIONES)
    assert all(e["origen"] == "plantilla" for e in datos["explicaciones"])
    assert "explicador" not in _leer(carpeta, "log.json")["totales_por_agente"]
