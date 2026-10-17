"""#75: corrida Humo con la IA simulada y sin Docker (el ejecutor siempre aprueba)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from qagent.almacenamiento import AlmacenProyecto
from qagent.config import cargar_configuracion
from qagent.config.carga import RUTA_CONFIG
from qagent.orchestrator.corrida import ejecutar_corrida
from tests.orchestrator.test_en09_mutacion_corrida import ejecutor_exitoso

RAIZ = Path(__file__).resolve().parents[2]
BANCO = RAIZ / "bench" / "banco_mvp.py"
BANCO_API = RAIZ / "bench_api" / "api_mvp.py"


@pytest.fixture
def config():
    return cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config


def preparar(tmp_path: Path, *archivos: Path) -> AlmacenProyecto:
    for archivo in archivos:
        shutil.copy(archivo, tmp_path / archivo.name)
    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()
    return almacen


def correr(almacen: AlmacenProyecto, config, perfil: str, eventos=None):
    run_id = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
    resumen = ejecutar_corrida(
        almacen.raiz,
        perfil,
        config,
        None,
        simulado=True,
        run_id=run_id,
        preparar_imagen=lambda _ruta: "imagen-prueba",
        ejecutor=ejecutor_exitoso,
        al_evento=eventos.append if eventos is not None else None,
        mutador=lambda *_a, **_k: None,
    )
    results = json.loads(
        (almacen.carpeta_run(resumen.run_id) / "results.json").read_text(
            encoding="utf-8"
        )
    )
    return resumen, results


def plan_de(almacen: AlmacenProyecto, modulo: str) -> dict:
    return almacen.leer_plan_modulo(modulo)


def llamadas_planner(almacen: AlmacenProyecto, run_id: str) -> list[dict]:
    log = json.loads(
        (almacen.carpeta_run(run_id) / "log.json").read_text(encoding="utf-8")
    )
    return [c for c in log["llamadas"] if c["agente"] == "planner"]


def specs_por_objetivo(almacen: AlmacenProyecto) -> dict[str, dict]:
    return {s["contrato"]["objetivo"]: s for s in almacen.listar_specs()}


def test_humo_planifica_un_caso_normal_por_funcion_y_endpoint(
    tmp_path: Path, config
) -> None:
    almacen = preparar(tmp_path, BANCO, BANCO_API)
    eventos: list[dict] = []

    resumen, results = correr(almacen, config, "humo", eventos)

    assert results["perfil"] == "humo"
    assert resumen.aceptadas == resumen.total_funciones == 12
    for modulo in ("banco_mvp.py", "api_mvp.py"):
        plan = plan_de(almacen, modulo)
        assert set(plan["perfiles"].values()) == {"humo"}
        for contrato in plan["contratos"]:
            [caso] = contrato["casos"]
            if contrato["tipo"] == "funcion":
                assert "valor_esperado" in caso and "excepcion" not in caso
            else:
                assert 200 <= caso["valor_esperado"]["status_code"] < 300
    assert {s["perfil"] for s in specs_por_objetivo(almacen).values()} == {"humo"}
    # Cada prueba aprobada tiene una sola función de prueba.
    for archivo in almacen.listar_pruebas_aprobadas():
        assert archivo.read_text(encoding="utf-8").count("def test_") == 1
    # La IA simulada devuelve varios casos: se conserva uno y queda el aviso.
    avisos = [e["mensaje"] for e in eventos if "Humo usa un solo caso" in e["mensaje"]]
    assert any("calcular_descuento" in a for a in avisos)
    assert any("POST /items" in a for a in avisos)


def test_una_spec_de_humo_no_se_reutiliza_en_estandar(tmp_path: Path, config) -> None:
    almacen = preparar(tmp_path, BANCO)
    correr(almacen, config, "humo")
    eventos: list[dict] = []

    resumen, _ = correr(almacen, config, "std", eventos)

    run = almacen.leer_run(resumen.run_id)
    assert {s["modulo"]: s["estado"] for s in run["specs"]} == {
        "banco_mvp.py": "regenerado"
    }
    assert len(llamadas_planner(almacen, resumen.run_id)) == 1
    assert any("se creó con Humo" in e["mensaje"] for e in eventos)
    plan = plan_de(almacen, "banco_mvp.py")
    assert set(plan["perfiles"].values()) == {"std"}
    casos = {c["objetivo"]: len(c["casos"]) for c in plan["contratos"]}
    assert casos["calcular_descuento"] == 4
    assert specs_por_objetivo(almacen)["calcular_descuento"]["perfil"] == "std"


def test_una_spec_estandar_en_humo_usa_su_primer_caso_normal(
    tmp_path: Path, config
) -> None:
    almacen = preparar(tmp_path, BANCO)
    correr(almacen, config, "std")
    completa = plan_de(almacen, "banco_mvp.py")

    resumen, results = correr(almacen, config, "humo")

    run = almacen.leer_run(resumen.run_id)
    assert {s["modulo"]: s["estado"] for s in run["specs"]} == {
        "banco_mvp.py": "reutilizado"
    }
    assert llamadas_planner(almacen, resumen.run_id) == []
    assert results["perfil"] == "humo"
    # Se probó solo el primer caso normal de cada función...
    for archivo in almacen.listar_pruebas_aprobadas():
        assert archivo.read_text(encoding="utf-8").count("def test_") == 1
    # ...pero la spec guardada sigue completa y con el perfil con que se creó.
    plan = plan_de(almacen, "banco_mvp.py")
    assert plan["contratos"] == completa["contratos"]
    assert set(plan["perfiles"].values()) == {"std"}
    spec = specs_por_objetivo(almacen)["calcular_descuento"]
    assert spec["perfil"] == "std"
    assert len(spec["contrato"]["casos"]) == 4


def test_estandar_sigue_reutilizando_su_propia_spec(tmp_path: Path, config) -> None:
    almacen = preparar(tmp_path, BANCO)
    correr(almacen, config, "std")

    resumen, _ = correr(almacen, config, "deep")

    run = almacen.leer_run(resumen.run_id)
    assert run["specs"][0]["estado"] == "reutilizado"
    assert llamadas_planner(almacen, resumen.run_id) == []
