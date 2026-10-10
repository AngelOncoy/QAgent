"""EN-07 (criterios 2 a 4): los datos persisten entre sesiones de la aplicación.

Cerrar y reabrir la app se simula de dos formas: con instancias nuevas sobre las mismas
carpetas y, en la última prueba, leyendo desde otro proceso de Python. El home del
usuario es siempre una carpeta temporal: nunca se toca el `~/.pyagent` real.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import pyagent
from pyagent import contracts
from pyagent.almacenamiento import AlmacenProyecto, nombre_prueba, recientes
from pyagent.app import desktop

CONTRATO = json.loads(
    (contracts.DIR_CONTRATOS / "ejemplos" / "planner_contract.v2.json").read_text(
        encoding="utf-8"
    )
)
CODIGO = "from tienda.precios import calcular_descuento\n\n\ndef test_descuento():\n    assert calcular_descuento(100.0, 20.0) == 80.0\n"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Home temporal: `Path.home()` lee estas variables en Windows y en Linux."""
    carpeta = tmp_path / "home"
    carpeta.mkdir()
    monkeypatch.setenv("USERPROFILE", str(carpeta))
    monkeypatch.setenv("HOME", str(carpeta))
    return carpeta


@pytest.fixture
def proyecto(tmp_path: Path) -> Path:
    carpeta = tmp_path / "tienda"
    (carpeta / "tienda").mkdir(parents=True)
    (carpeta / "tienda" / "precios.py").write_text(
        "def calcular_descuento(precio, porcentaje):\n"
        "    return precio * (1 - porcentaje / 100)\n",
        encoding="utf-8",
    )
    return carpeta


def _sesion_con_corrida(proyecto: Path) -> dict:
    """Primera sesión: corrida con una spec y su prueba aprobada."""
    almacen = AlmacenProyecto(proyecto)
    run = almacen.crear_run(["funcion"], "pyagent-sandbox:base")
    spec = almacen.guardar_spec(CONTRATO, run["run_id"])
    archivo = nombre_prueba(spec["id"])
    almacen.guardar_prueba_aprobada(archivo, CODIGO)
    almacen.guardar_spec(CONTRATO, run["run_id"], archivo_prueba=archivo)
    almacen.finalizar_run(run["run_id"], "fin", pasaron=1, fallaron=0)
    return {"run_id": run["run_id"], "spec_id": spec["id"], "archivo": archivo}


def test_una_instancia_nueva_lee_lo_que_guardo_otra(proyecto: Path):
    datos = _sesion_con_corrida(proyecto)

    reabierto = AlmacenProyecto(proyecto)  # "reabrir la app"

    [run] = reabierto.listar_runs()
    assert run["run_id"] == datos["run_id"]
    assert run["estado"] == "fin"
    assert run["resumen"] == {"pasaron": 1, "fallaron": 0}
    spec = reabierto.leer_spec(datos["spec_id"])
    assert spec["contrato"] == CONTRATO
    assert spec["archivo_prueba"] == datos["archivo"]
    assert reabierto.tiene_specs()
    assert [p.name for p in reabierto.listar_pruebas_aprobadas()] == [datos["archivo"]]
    assert reabierto.leer_prueba_aprobada(datos["archivo"]) == CODIGO


def test_varias_sesiones_acumulan_el_historial(proyecto: Path):
    primera = AlmacenProyecto(proyecto).crear_run()
    segunda = AlmacenProyecto(proyecto).crear_run()

    ids = [r["run_id"] for r in AlmacenProyecto(proyecto).listar_runs()]

    assert set(ids) == {primera["run_id"], segunda["run_id"]}
    assert ids == sorted(ids)


def test_reabrir_el_proyecto_no_borra_nada(home: Path, proyecto: Path):
    datos = _sesion_con_corrida(proyecto)
    api = desktop.DesktopAPI()

    assert api.abrir_proyecto(str(proyecto))["ok"]  # inicializa otra vez
    assert api.abrir_reciente(str(proyecto))["ok"]

    almacen = AlmacenProyecto(proyecto)
    assert [r["run_id"] for r in almacen.listar_runs()] == [datos["run_id"]]
    assert almacen.leer_spec(datos["spec_id"])["archivo_prueba"] == datos["archivo"]
    assert len(almacen.listar_pruebas_aprobadas()) == 1


def test_recientes_persisten_en_el_home_entre_sesiones(home: Path, proyecto: Path):
    desktop.DesktopAPI().abrir_proyecto(str(proyecto))

    otra_sesion = desktop.DesktopAPI()

    archivo = home / ".pyagent" / "recientes.json"
    assert recientes.ruta_por_defecto() == archivo
    [entrada] = json.loads(archivo.read_text(encoding="utf-8"))
    assert set(entrada) == {"nombre", "origen", "ruta", "url", "ultima_apertura"}
    assert [p["ruta"] for p in otra_sesion.listar_recientes()] == [str(proyecto)]


def test_un_recientes_json_del_formato_anterior_se_sigue_leyendo(home: Path):
    """El archivo que dejó la HU-01 antes de mover el módulo se lee igual."""
    archivo = home / ".pyagent" / "recientes.json"
    archivo.parent.mkdir()
    anterior = [
        {
            "nombre": "demo",
            "origen": "git",
            "ruta": str(home / "demo"),
            "url": "https://github.com/equipo/demo.git",
            "ultima_apertura": "2026-10-03T09:30:15+00:00",
            "ultima_corrida": "2026-10-03T10:00:00+00:00",
        }
    ]
    archivo.write_text(json.dumps(anterior), encoding="utf-8")

    assert recientes.cargar() == anterior


def test_recientes_json_corrupto_no_tumba_la_app(home: Path, proyecto: Path):
    archivo = home / ".pyagent" / "recientes.json"
    archivo.parent.mkdir()
    archivo.write_text("[{", encoding="utf-8")
    api = desktop.DesktopAPI()

    assert api.listar_recientes() == []
    assert api.abrir_proyecto(str(proyecto))["ok"]  # y se repara al guardar
    assert [p["ruta"] for p in api.listar_recientes()] == [str(proyecto)]


def test_otro_proceso_lee_lo_guardado(home: Path, proyecto: Path):
    """Lo más parecido a cerrar y reabrir la app: un proceso de Python nuevo."""
    datos = _sesion_con_corrida(proyecto)
    desktop.DesktopAPI().abrir_proyecto(str(proyecto))
    lector = (
        "import json, sys\n"
        "from pyagent.almacenamiento import AlmacenProyecto, recientes\n"
        "a = AlmacenProyecto(sys.argv[1])\n"
        "print(json.dumps({\n"
        "    'runs': [r['run_id'] for r in a.listar_runs()],\n"
        "    'specs': [s['id'] for s in a.listar_specs()],\n"
        "    'tests': [p.name for p in a.listar_pruebas_aprobadas()],\n"
        "    'recientes': [e['ruta'] for e in recientes.cargar()],\n"
        "}))\n"
    )
    src = str(Path(pyagent.__file__).resolve().parents[1])  # con o sin pip install -e
    rutas = [src, os.environ.get("PYTHONPATH", "")]
    entorno = {
        **os.environ,
        "PYAGENT_FAKE_LLM": "1",
        "PYTHONPATH": os.pathsep.join(r for r in rutas if r),
    }

    salida = subprocess.run(
        [sys.executable, "-c", lector, str(proyecto)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=entorno,
        check=True,
        timeout=60,
    )

    assert json.loads(salida.stdout) == {
        "runs": [datos["run_id"]],
        "specs": [datos["spec_id"]],
        "tests": [datos["archivo"]],
        "recientes": [str(proyecto)],
    }
