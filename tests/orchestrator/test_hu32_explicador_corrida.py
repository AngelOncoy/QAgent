"""El Explicador dentro de la corrida (HU-32): después de results.json, sin tocarlo.

Usa la IA simulada y el ejecutor simulado de `test_corrida`: no ejecuta código.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import shutil
from pathlib import Path

import pytest

from qagent import contracts
from qagent.almacenamiento import AlmacenProyecto
from qagent.config import cargar_configuracion
from qagent.config.carga import RUTA_CONFIG, Explicador
from qagent.orchestrator import corrida
from qagent.orchestrator.corrida import ejecutar_corrida
from qagent.storage.registro import ARCHIVO_EXPLICACIONES
from tests.orchestrator.test_corrida import BANCO, CON_BUG, ejecutor_simulado


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


def correr(almacen, config, perfil="deep", **opciones):
    run_id = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
    resumen = ejecutar_corrida(
        almacen.raiz,
        perfil,
        config,
        None,
        simulado=True,
        run_id=run_id,
        preparar_imagen=lambda ruta: "imagen-prueba",
        ejecutor=ejecutor_simulado,
        **opciones,
    )
    return resumen, almacen.carpeta_run(resumen.run_id)


def _leer(carpeta: Path, archivo: str):
    return json.loads((carpeta / archivo).read_text(encoding="utf-8"))


def test_explica_cada_objetivo_no_aceptado(proyecto, config) -> None:
    resumen, carpeta = correr(proyecto, config)

    assert resumen.estado == "fin", resumen.motivo
    results = _leer(carpeta, "results.json")
    datos = _leer(carpeta, ARCHIVO_EXPLICACIONES)
    contracts.validar_explicaciones(datos, results_confiables=results)
    assert datos["run_id"] == resumen.run_id
    assert sorted(e["objetivo"] for e in datos["explicaciones"]) == sorted(CON_BUG)
    assert all(e["decision"] == "bug_detectado" for e in datos["explicaciones"])
    assert all(e["origen"] == "plantilla" for e in datos["explicaciones"])
    # Nunca dentro de results.json.
    assert "explicacion" not in json.dumps(results)
    assert proyecto.leer_run(resumen.run_id)["estado"] == "fin"


def test_results_json_queda_identico_con_explicador(proyecto, config, monkeypatch):
    escritos: dict[str, bytes] = {}
    original = corrida.escribir_corrida

    def escribir_y_copiar(*args, **kwargs):
        rutas = original(*args, **kwargs)
        escritos["results"] = rutas.results.read_bytes()
        escritos["detalle"] = rutas.detalle.read_bytes()
        return rutas

    monkeypatch.setattr(corrida, "escribir_corrida", escribir_y_copiar)

    _, carpeta = correr(proyecto, config)

    assert (carpeta / ARCHIVO_EXPLICACIONES).is_file()
    assert (carpeta / "results.json").read_bytes() == escritos["results"]
    assert (carpeta / "detalle.json").read_bytes() == escritos["detalle"]


def test_veredictos_iguales_con_y_sin_explicador(proyecto, config) -> None:
    apagado = dataclasses.replace(config, explicador=Explicador(activo=False))

    _, con = correr(proyecto, config)
    _, sin = correr(proyecto, apagado)

    def veredictos(carpeta):
        results = _leer(carpeta, "results.json")
        return [
            (o["funcion"], o["decision"], o["laundering_detectado"])
            for o in results["objetivos"]
        ], results["resumen"]["bugs_detectados"]

    assert veredictos(con) == veredictos(sin)
    assert set(_leer(con, "results.json")) == set(_leer(sin, "results.json"))


def test_desactivado_no_escribe_explicaciones(proyecto, config) -> None:
    apagado = dataclasses.replace(config, explicador=Explicador(activo=False))

    resumen, carpeta = correr(proyecto, apagado)

    assert resumen.bugs_detectados == 3
    assert not (carpeta / ARCHIVO_EXPLICACIONES).exists()


def test_se_omite_en_el_perfil_humo(proyecto, config) -> None:
    resumen, carpeta = correr(proyecto, config, perfil="humo")

    assert (carpeta / "results.json").is_file(), resumen.motivo
    assert not (carpeta / ARCHIVO_EXPLICACIONES).exists()


def test_se_omite_si_la_corrida_se_cancelo(proyecto, config) -> None:
    veredictos = 0

    def contar(evento):
        nonlocal veredictos
        veredictos += evento.get("tipo") == "veredicto"

    resumen, carpeta = correr(
        proyecto, config, al_evento=contar, cancelado=lambda: veredictos >= 2
    )

    assert resumen.cancelada is True
    assert (carpeta / "results.json").is_file()
    assert not (carpeta / ARCHIVO_EXPLICACIONES).exists()


def test_una_falla_del_explicador_no_cambia_la_corrida(
    proyecto, config, monkeypatch, caplog
) -> None:
    def falla(*_args, **_kwargs):
        raise RuntimeError("plantilla rota")

    monkeypatch.setattr(corrida, "explicar_corrida", falla)

    with caplog.at_level(logging.WARNING, logger="qagent.corrida"):
        resumen, carpeta = correr(proyecto, config)

    assert resumen.estado == "fin", resumen.motivo
    assert (resumen.aceptadas, resumen.bugs_detectados) == (3, 3)
    assert proyecto.leer_run(resumen.run_id)["estado"] == "fin"
    assert len(proyecto.listar_specs()) == 6
    assert not (carpeta / ARCHIVO_EXPLICACIONES).exists()
    assert "El Explicador falló" in caplog.text
    assert "plantilla rota" in caplog.text


def test_una_salida_invalida_no_se_guarda(proyecto, config, monkeypatch, caplog):
    original = corrida.explicar_corrida

    def con_basura(results, detalle):
        resultado = original(results, detalle)
        resultado.datos["explicaciones"].append({"objetivo": "sin campos"})
        return resultado

    monkeypatch.setattr(corrida, "explicar_corrida", con_basura)

    with caplog.at_level(logging.WARNING, logger="qagent.corrida"):
        resumen, carpeta = correr(proyecto, config)

    assert resumen.estado == "fin"
    assert proyecto.leer_run(resumen.run_id)["estado"] == "fin"
    assert not (carpeta / ARCHIVO_EXPLICACIONES).exists()
    assert "El Explicador falló" in caplog.text
