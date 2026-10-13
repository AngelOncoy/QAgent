"""Prueba funcional HU-25 con Docker real y red deshabilitada."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from pyagent import contracts
from pyagent.almacenamiento import AlmacenProyecto, id_de_spec, nombre_prueba
from pyagent.config import cargar_configuracion
from pyagent.config.carga import RUTA_CONFIG
from pyagent.orchestrator.corrida import ejecutar_corrida
from pyagent.orchestrator.regresion import huellas_de_objetivos

pytestmark = pytest.mark.docker
BANCO = Path(__file__).resolve().parents[2] / "bench"


def _contrato() -> dict:
    dato = json.loads(
        (contracts.DIR_CONTRATOS / "ejemplos" / "planner_contract.v2.json").read_text(
            encoding="utf-8"
        )
    )
    dato.update(
        modulo="calc.py",
        objetivo="valor",
        firma="() -> int",
        critical=False,
        casos=[
            {
                "id": "valor_actual",
                "descripcion": "Devuelve el valor calculado",
                "entrada": {},
                "valor_esperado": 2,
                "origen": "docstring",
            }
        ],
    )
    return dato


def test_regresion_real_sin_ia_sin_red_y_fallo_posterior(
    tmp_path: Path, imagen_base
):
    raiz = tmp_path / "proyecto"
    raiz.mkdir()
    modulo = (
        "def _fuente() -> int:\n"
        "    return 2\n\n"
        "def valor() -> int:\n"
        "    return _fuente()\n"
    )
    (raiz / "calc.py").write_text(modulo, encoding="utf-8")
    almacen = AlmacenProyecto(raiz)
    almacen.inicializar()
    contrato = _contrato()
    codigo = (
        "import socket\n"
        "import pytest\n"
        "from calc import valor\n\n"
        "def test_valor_y_red_bloqueada():\n"
        "    assert valor() == 2\n"
        "    with pytest.raises(OSError):\n"
        "        socket.create_connection(('1.1.1.1', 53), timeout=1)\n"
    )
    inicial = almacen.crear_run(tipos_prueba=["funcion"])
    prueba = nombre_prueba(id_de_spec("calc.py", "valor"))
    almacen.guardar_prueba_aprobada(prueba, codigo)
    almacen.guardar_spec(
        contrato,
        inicial["run_id"],
        prueba,
        huella_objetivo=huellas_de_objetivos(raiz)[("calc.py", "valor")],
    )
    almacen.finalizar_run(inicial["run_id"], "fin", 1, 0)
    config = cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config

    run_ok = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
    ok = ejecutar_corrida(
        raiz,
        "reg",
        config,
        None,
        simulado=False,
        run_id=run_ok,
        preparar_imagen=lambda ruta: imagen_base,
    )
    artefacto_ok = json.loads(
        (almacen.carpeta_run(run_ok) / "results.json").read_text(encoding="utf-8")
    )
    log_ok = json.loads(
        (almacen.carpeta_run(run_ok) / "log.json").read_text(encoding="utf-8")
    )
    assert (ok.aceptadas, ok.tokens, ok.costo_usd) == (1, 0, 0.0)
    assert artefacto_ok["objetivos"][0]["decision"] == "accept"
    assert log_ok["llamadas"] == []

    # Cambia una dependencia privada, no el AST de la funcion objetivo: la prueba
    # sigue siendo elegible y debe detectar la regresion real.
    (raiz / "calc.py").write_text(modulo.replace("return 2", "return 3"), encoding="utf-8")
    run_fallo = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
    fallo = ejecutar_corrida(
        raiz,
        "reg",
        config,
        None,
        simulado=False,
        run_id=run_fallo,
        preparar_imagen=lambda ruta: imagen_base,
    )
    artefacto_fallo = json.loads(
        (almacen.carpeta_run(run_fallo) / "results.json").read_text(encoding="utf-8")
    )
    assert fallo.bugs_detectados == 1
    assert artefacto_fallo["objetivos"][0]["decision"] == "bug_detectado"
    assert len(almacen.listar_runs()) == 3


def test_flujo_real_generacion_regresion_y_funcion_modificada(
    tmp_path: Path, imagen_base, monkeypatch
):
    """Escenarios A-C completos: Generator simulado y todas las ejecuciones en Docker."""
    raiz = tmp_path / "banco"
    shutil.copytree(BANCO, raiz, ignore=shutil.ignore_patterns("*.md", "*.json"))
    almacen = AlmacenProyecto(raiz)
    almacen.inicializar()
    config = cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config

    run_base = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
    base = ejecutar_corrida(
        raiz,
        "deep",
        config,
        None,
        simulado=True,
        run_id=run_base,
        preparar_imagen=lambda ruta: imagen_base,
    )
    assert (base.aceptadas, base.bugs_detectados) == (3, 3)
    assert len(almacen.listar_pruebas_aprobadas()) == 3

    def ia_prohibida(*args, **kwargs):
        raise AssertionError("Regresion intento construir un cliente LLM")

    monkeypatch.setattr("pyagent.orchestrator.corrida.crear_cliente", ia_prohibida)
    run_reg = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
    reg = ejecutar_corrida(
        raiz,
        "reg",
        config,
        None,
        simulado=False,
        run_id=run_reg,
        preparar_imagen=lambda ruta: imagen_base,
    )
    assert (reg.aceptadas, reg.tokens, reg.costo_usd) == (3, 0, 0.0)

    modulo = raiz / "banco_mvp.py"
    fuente = modulo.read_text(encoding="utf-8")
    modulo.write_text(
        fuente.replace(
            "return limpio == limpio[::-1]",
            "return limpio.lower() == limpio[::-1].lower()",
        ),
        encoding="utf-8",
    )
    run_cambio = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
    cambio = ejecutar_corrida(
        raiz,
        "reg",
        config,
        None,
        simulado=False,
        run_id=run_cambio,
        preparar_imagen=lambda ruta: imagen_base,
    )
    results = json.loads(
        (almacen.carpeta_run(run_cambio) / "results.json").read_text(
            encoding="utf-8"
        )
    )
    obsoleto = next(o for o in results["objetivos"] if o["funcion"] == "es_palindromo")
    assert cambio.requieren_corrida_nueva == 1
    assert cambio.aceptadas == 2
    assert obsoleto["decision"] == "requiere_corrida_nueva"
    assert obsoleto["metricas"]["iteraciones"] == 0
    assert len(almacen.listar_runs()) == 3
