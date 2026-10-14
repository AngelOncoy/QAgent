"""EN-07: Almacenamiento del proyecto (.pyagent/) — Criterios de Aceptación.

Verifica formalmente los 4 criterios de aceptación del PBI EN-07:
1. Estructura: .pyagent/runs/<run_id>/, .pyagent/specs/ y .pyagent/tests/.
2. Guarda y lee specs, pruebas aprobadas e historial; los datos persisten entre sesiones.
3. Proyectos recientes en ~/.pyagent/recientes.json.
4. Evidencia de aceptación: tras cerrar y reabrir la aplicación, las corridas, specs
   y pruebas aprobadas siguen en .pyagent/ y los proyectos recientes en ~/.pyagent/recientes.json.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pyagent import contracts
from pyagent.almacenamiento import AlmacenProyecto, id_de_spec, nombre_prueba, recientes
from pyagent.app.desktop import DesktopAPI
from pyagent.llm import cargar_precios
from pyagent.storage import escribir_corrida
from tests.storage.test_registro import correr

MOMENTO = datetime(2026, 10, 20, 10, 0, 0, tzinfo=timezone.utc)
CONTRATO_PLANNER = json.loads(
    (contracts.DIR_CONTRATOS / "ejemplos" / "planner_contract.v2.json").read_text(
        encoding="utf-8"
    )
)
METAS = {
    "pass_rate_min": 60.0,
    "cobertura_lineas_min": 60.0,
    "iteraciones_promedio_max": 2.0,
    "tope_por_corrida_usd": 10.0,
}


@pytest.fixture
def carpeta_proyecto(tmp_path: Path) -> Path:
    proyecto = tmp_path / "proyecto_demo"
    proyecto.mkdir()
    return proyecto


@pytest.fixture
def archivo_recientes(tmp_path: Path) -> Path:
    archivo = tmp_path / "home" / ".pyagent" / "recientes.json"
    archivo.parent.mkdir(parents=True, exist_ok=True)
    return archivo


def test_criterio_1_estructura_directorios(carpeta_proyecto: Path) -> None:
    """Criterio 1: Estructura .pyagent/runs/<run_id>/, .pyagent/specs/ y .pyagent/tests/."""
    almacen = AlmacenProyecto(carpeta_proyecto)
    assert not almacen.existe()

    # Inicializar genera las 3 subcarpetas y .gitignore
    almacen.inicializar()
    assert almacen.existe()
    assert almacen.carpeta.is_dir()
    assert almacen.carpeta_runs.is_dir()
    assert almacen.carpeta_specs.is_dir()
    assert almacen.carpeta_tests.is_dir()

    gitignore = almacen.carpeta / ".gitignore"
    assert gitignore.is_file()
    assert "runs/" in gitignore.read_text(encoding="utf-8")

    # Al crear una corrida se genera la estructura .pyagent/runs/<run_id>/ con run.json
    run = almacen.crear_run(tipos_prueba=["funcion"], ahora=MOMENTO)
    run_id = run["run_id"]
    carpeta_run = almacen.carpeta_run(run_id)
    assert carpeta_run.is_dir()
    assert (carpeta_run / "run.json").is_file()

    # Al guardar spec se almacena en .pyagent/specs/<spec_id>.json
    spec = almacen.guardar_spec(CONTRATO_PLANNER, run_origen=run_id, ahora=MOMENTO)
    ruta_spec = almacen.carpeta_specs / f"{spec['id']}.json"
    assert ruta_spec.is_file()

    # Al guardar prueba aprobada se almacena en .pyagent/tests/test_*.py
    nombre_archivo = nombre_prueba(spec["id"])
    codigo_prueba = "def test_calcular():\n    assert True\n"
    ruta_prueba = almacen.guardar_prueba_aprobada(nombre_archivo, codigo_prueba)
    assert ruta_prueba.is_file()
    assert ruta_prueba.parent == almacen.carpeta_tests


def test_criterio_2_guarda_y_lee_specs_pruebas_e_historial(
    carpeta_proyecto: Path,
) -> None:
    """Criterio 2: Guarda y lee specs, pruebas aprobadas e historial; persistencia garantizada."""
    almacen = AlmacenProyecto(carpeta_proyecto)

    # 1. Historial (corridas)
    run = almacen.crear_run(tipos_prueba=["funcion", "endpoint"], ahora=MOMENTO)
    almacen.finalizar_run(run["run_id"], estado="fin", pasaron=5, fallaron=0)

    runs = almacen.listar_runs()
    assert len(runs) == 1
    assert runs[0]["run_id"] == run["run_id"]
    assert runs[0]["estado"] == "fin"
    assert runs[0]["resumen"] == {"pasaron": 5, "fallaron": 0}

    # 2. Specs
    spec_guardada = almacen.guardar_spec(
        CONTRATO_PLANNER, run_origen=run["run_id"], ahora=MOMENTO
    )
    spec_leida = almacen.leer_spec(spec_guardada["id"])
    assert spec_leida["id"] == spec_guardada["id"]
    assert spec_leida["contrato"]["modulo"] == CONTRATO_PLANNER["modulo"]
    assert len(almacen.listar_specs()) == 1

    # 3. Pruebas aprobadas
    nombre_test = nombre_prueba(spec_guardada["id"])
    codigo = "def test_sumar():\n    assert 1 + 1 == 2\n"
    almacen.guardar_prueba_aprobada(nombre_test, codigo)

    assert almacen.leer_prueba_aprobada(nombre_test) == codigo
    pruebas = almacen.listar_pruebas_aprobadas()
    assert len(pruebas) == 1
    assert pruebas[0].name == nombre_test


def test_criterio_3_proyectos_recientes_en_home(archivo_recientes: Path) -> None:
    """Criterio 3: Proyectos recientes en ~/.pyagent/recientes.json."""
    # Comprobar la convención de ruta por defecto
    ruta_default = recientes.ruta_por_defecto()
    assert ruta_default == Path.home() / ".pyagent" / "recientes.json"

    # Registrar proyectos en archivo destino
    recientes.registrar(
        nombre="Proyecto Alpha",
        origen="local",
        ruta="/proyectos/alpha",
        archivo=archivo_recientes,
        ahora=MOMENTO,
    )
    recientes.registrar(
        nombre="Proyecto Beta",
        origen="git",
        ruta="/proyectos/beta",
        url="https://github.com/org/beta.git",
        archivo=archivo_recientes,
        ahora=MOMENTO,
    )

    entradas = recientes.cargar(archivo_recientes)
    assert len(entradas) == 2
    # El más reciente primero
    assert entradas[0]["nombre"] == "Proyecto Beta"
    assert entradas[0]["origen"] == "git"
    assert entradas[0]["url"] == "https://github.com/org/beta.git"
    assert entradas[1]["nombre"] == "Proyecto Alpha"

    # Registrar corrida en un reciente
    recientes.registrar_corrida("/proyectos/alpha", MOMENTO, archivo=archivo_recientes)
    actualizados = recientes.cargar(archivo_recientes)
    alpha = next(e for e in actualizados if e["ruta"] == "/proyectos/alpha")
    assert alpha.get("ultima_corrida") == MOMENTO.isoformat(timespec="seconds")


def test_criterio_4_evidencia_persistencia_tras_reinicio_sesion(
    carpeta_proyecto: Path, archivo_recientes: Path
) -> None:
    """Criterio 4: Evidencia de aceptación tras cerrar y reabrir la aplicación.

    Las corridas, specs y pruebas aprobadas siguen en .pyagent/ y los proyectos
    recientes en ~/.pyagent/recientes.json sin ninguna pérdida.
    """
    # === SESIÓN 1 (Antes de cerrar la aplicación) ===
    almacen_sesion1 = AlmacenProyecto(carpeta_proyecto)
    almacen_sesion1.inicializar()

    # Registrar en recientes
    recientes.registrar(
        nombre="Proyecto Persistente",
        origen="local",
        ruta=str(carpeta_proyecto),
        archivo=archivo_recientes,
        ahora=MOMENTO,
    )

    # Crear corrida completa con almacenamiento EN-05 (results y log)
    precios = cargar_precios()
    tracker, resultado = correr(precios, decisiones=("accept",))
    rutas = escribir_corrida(
        carpeta_proyecto, resultado, tracker, precios, "deep", metas=METAS
    )
    run_id = rutas.run_id

    run = {
        "run_id": run_id,
        "inicio": "2026-10-20T10:00:00+00:00",
        "fin": "2026-10-20T10:01:00+00:00",
        "tipos_prueba": ["funcion"],
        "imagen_docker": "pyagent-sandbox:base",
        "estado": "fin",
        "resumen": {"pasaron": 1, "fallaron": 0},
    }
    almacen_sesion1.guardar_run(run)

    # Guardar spec y prueba aprobada
    spec1 = almacen_sesion1.guardar_spec(
        CONTRATO_PLANNER, run_origen=run_id, ahora=MOMENTO
    )
    nombre_archivo_test = nombre_prueba(spec1["id"])
    codigo_test = "def test_sumar_aprobado():\n    assert 2 + 2 == 4\n"
    almacen_sesion1.guardar_prueba_aprobada(nombre_archivo_test, codigo_test)

    # SIMULAR CIERRE COMPLETO DE LA APLICACIÓN (destrucción de referencias)
    del almacen_sesion1

    # === SESIÓN 2 (Reabrir la aplicación con instancias nuevas) ===
    # 1. Proyectos recientes leídos por la interfaz de inicio
    recientes_sesion2 = recientes.cargar(archivo_recientes)
    assert len(recientes_sesion2) == 1
    assert recientes_sesion2[0]["nombre"] == "Proyecto Persistente"
    assert recientes_sesion2[0]["ruta"] == str(carpeta_proyecto)

    # 2. Almacén del proyecto recargado en frío desde disco
    almacen_sesion2 = AlmacenProyecto(carpeta_proyecto)
    assert almacen_sesion2.existe()

    # Verificar corridas intactas
    corridas = almacen_sesion2.listar_runs()
    assert len(corridas) == 1
    assert corridas[0]["run_id"] == run_id
    assert corridas[0]["estado"] == "fin"
    assert corridas[0]["resumen"] == {"pasaron": 1, "fallaron": 0}

    # Verificar specs intactas
    specs = almacen_sesion2.listar_specs()
    assert len(specs) == 1
    assert specs[0]["id"] == id_de_spec(
        CONTRATO_PLANNER["modulo"], CONTRATO_PLANNER["objetivo"]
    )
    assert specs[0]["run_origen"] == run_id

    # Verificar pruebas aprobadas intactas
    pruebas = almacen_sesion2.listar_pruebas_aprobadas()
    assert len(pruebas) == 1
    assert pruebas[0].name == nombre_archivo_test
    assert almacen_sesion2.leer_prueba_aprobada(nombre_archivo_test) == codigo_test

    # 3. Interfaz DesktopAPI (puente pywebview)
    api = DesktopAPI()
    historial_api = api.obtener_historial(str(carpeta_proyecto))
    assert historial_api.get("ok") is True
    assert len(historial_api.get("corridas", [])) == 1
    assert historial_api["corridas"][0]["run_id"] == run_id

    reporte_api = api.obtener_reporte(str(carpeta_proyecto), run_id)
    assert reporte_api.get("ok") is True
    assert reporte_api.get("indicadores", {}).get("pass_rate", {}).get("valor") == 100.0
