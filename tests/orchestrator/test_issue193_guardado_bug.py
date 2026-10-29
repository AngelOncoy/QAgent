"""#193: el orquestador guarda bugs sin alterar la regresión HU-25."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from qagent import contracts
from qagent.almacenamiento import AlmacenProyecto
from qagent.config import cargar_configuracion
from qagent.config.carga import RUTA_CONFIG
from qagent.orchestrator.corrida import ejecutar_corrida
from qagent.orchestrator.regresion import huellas_de_objetivos, objetivos_repetibles
from tests.orchestrator.test_corrida import BANCO, ejecutor_simulado


def test_corrida_guarda_cada_bug_con_spec_firma_y_run(tmp_path: Path) -> None:
    raiz = tmp_path / "banco"
    shutil.copytree(
        BANCO, raiz, ignore=shutil.ignore_patterns("*.md", "*.json", ".qagent")
    )
    almacen = AlmacenProyecto(raiz)
    almacen.inicializar()
    run_id = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
    config = cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config

    resumen = ejecutar_corrida(
        raiz,
        "deep",
        config,
        None,
        simulado=True,
        run_id=run_id,
        preparar_imagen=lambda _ruta: "imagen-prueba",
        ejecutor=ejecutor_simulado,
    )

    evidencias = almacen.listar_evidencias_bug(run_id)
    assert resumen.bugs_detectados == 3
    assert len(evidencias) == 3
    assert {e["objetivo"]["nombre"] for e in evidencias} == {
        "calcular_descuento",
        "clasificar_edad",
        "buscar_elemento_mayor",
    }
    assert all(e["run_id"] == run_id for e in evidencias)
    assert all(e["firma"] == e["spec"]["firma"] for e in evidencias)
    assert all(e["decision"] == "bug_detectado" for e in evidencias)
    assert len(almacen.listar_pruebas_aprobadas()) == 3


def test_hu25_ignora_evidencia_bug_y_solo_repite_accept(tmp_path: Path) -> None:
    (tmp_path / "modulo.py").write_text(
        "def duplicar(x: int) -> int:\n    return x * 2\n", encoding="utf-8"
    )
    almacen = AlmacenProyecto(tmp_path)
    run_id = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
    contrato = json.loads(
        (contracts.DIR_CONTRATOS / "ejemplos" / "planner_contract.v2.json").read_text(
            encoding="utf-8"
        )
    )
    contrato.update(
        modulo="modulo.py",
        objetivo="duplicar",
        firma="(x: int) -> int",
        huella="0" * 64,
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
    codigo = "def test_duplicar():\n    assert duplicar(2) == 4\n"
    huella = huellas_de_objetivos(tmp_path)[("modulo.py", "duplicar")]

    almacen.guardar_evidencia_bug(contrato, codigo, run_id)
    almacen.guardar_spec(contrato, run_id, huella_objetivo=huella)

    assert almacen.listar_pruebas_aprobadas() == []
    assert objetivos_repetibles(tmp_path) == []

    archivo = "test_modulo_py__duplicar.py"
    almacen.guardar_prueba_aprobada(archivo, codigo)
    almacen.guardar_spec(
        contrato, run_id, archivo_prueba=archivo, huella_objetivo=huella
    )

    assert objetivos_repetibles(tmp_path) == [
        {"modulo": "modulo.py", "objetivo": "duplicar"}
    ]
