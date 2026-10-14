"""HU-25: regresion de aprobadas en Docker, sin llamadas LLM."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from pyagent.almacenamiento import AlmacenProyecto
from pyagent.config import cargar_configuracion
from pyagent.config.carga import RUTA_CONFIG
from pyagent.orchestrator.corrida import ejecutar_corrida
from pyagent.orchestrator.regresion import huellas_de_objetivos
from pyagent.sandbox import ResultadoSandbox

BANCO = Path(__file__).resolve().parents[2] / "bench"
COBERTURA = {
    "totals": {"percent_covered": 100.0, "num_branches": 0, "covered_branches": 0}
}
BUGS = ("calcular_descuento", "clasificar_edad", "buscar_elemento_mayor")


@pytest.fixture
def config():
    return cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config


def _ejecutor_generacion(imagen, proyecto, tests, modulo):
    codigo = next(Path(tests).glob("test_*.py")).read_text(encoding="utf-8")
    fallo = any(f"import {nombre}" in codigo for nombre in BUGS)
    return ResultadoSandbox(
        1 if fallo else 0,
        "FAILED assert 1 == 2" if fallo else "1 passed",
        "",
        COBERTURA,
    )


@pytest.fixture
def preparado(tmp_path: Path):
    raiz = tmp_path / "banco"
    shutil.copytree(BANCO, raiz, ignore=shutil.ignore_patterns("*.md", "*.json"))
    almacen = AlmacenProyecto(raiz)
    almacen.inicializar()
    config = cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config
    run_id = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
    primero = ejecutar_corrida(
        raiz,
        "deep",
        config,
        None,
        simulado=True,
        run_id=run_id,
        preparar_imagen=lambda ruta: "imagen",
        ejecutor=_ejecutor_generacion,
    )
    assert primero.aceptadas == 3
    return raiz, almacen, config


def _regresion(preparado, monkeypatch, llamadas):
    raiz, almacen, config = preparado

    def ejecutor(imagen, proyecto, tests, modulo):
        llamadas.append(next(Path(tests).glob("test_*.py")).name)
        return ResultadoSandbox(0, "1 passed", "", COBERTURA)

    def prohibida(*args, **kwargs):
        raise AssertionError("Regresion no debe crear clientes LLM")

    monkeypatch.setattr("pyagent.orchestrator.corrida.crear_cliente", prohibida)
    run_id = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
    resumen = ejecutar_corrida(
        raiz,
        "reg",
        config,
        None,
        simulado=False,
        run_id=run_id,
        preparar_imagen=lambda ruta: "imagen",
        ejecutor=ejecutor,
    )
    results = json.loads(
        (almacen.carpeta_run(run_id) / "results.json").read_text(encoding="utf-8")
    )
    log = json.loads(
        (almacen.carpeta_run(run_id) / "log.json").read_text(encoding="utf-8")
    )
    return resumen, results, log


def test_escenario_a_reutiliza_aprobadas_y_costo_cero(preparado, monkeypatch):
    llamadas = []
    resumen, results, log = _regresion(preparado, monkeypatch, llamadas)
    assert resumen.estado == "fin"
    assert (resumen.aceptadas, resumen.tokens, resumen.costo_usd) == (3, 0, 0.0)
    assert len(llamadas) == 3
    assert log["llamadas"] == []
    assert results["resumen"]["costo_total_usd"] == 0
    assert all(o["reutilizada"] for o in results["objetivos"])


def test_escenario_b_funcion_modificada_requiere_corrida_nueva(
    preparado, monkeypatch
):
    raiz, _, _ = preparado
    archivo = raiz / "banco_mvp.py"
    archivo.write_text(
        archivo.read_text(encoding="utf-8").replace(
            "return limpio == limpio[::-1]",
            "return limpio.lower() == limpio[::-1].lower()",
        ),
        encoding="utf-8",
    )
    llamadas = []
    resumen, results, _ = _regresion(preparado, monkeypatch, llamadas)
    cambiados = [
        o for o in results["objetivos"] if o["decision"] == "requiere_corrida_nueva"
    ]
    assert resumen.requieren_corrida_nueva == 1
    assert len(llamadas) == 2
    assert cambiados[0]["funcion"] == "es_palindromo"
    assert cambiados[0]["motivo_regresion"] == "huella_distinta"


def test_escenario_c_funcion_eliminada_no_se_ejecuta(preparado, monkeypatch):
    raiz, _, _ = preparado
    archivo = raiz / "banco_mvp.py"
    fuente = archivo.read_text(encoding="utf-8")
    inicio = fuente.index("\ndef es_palindromo(")
    fin = fuente.index("\ndef ", inicio + 2)
    fuente = fuente[:inicio] + fuente[fin:]
    archivo.write_text(fuente, encoding="utf-8")
    llamadas = []
    resumen, results, _ = _regresion(preparado, monkeypatch, llamadas)
    ausente = next(o for o in results["objetivos"] if o["funcion"] == "es_palindromo")
    assert resumen.requieren_corrida_nueva == 1
    assert ausente["motivo_regresion"] == "objetivo_ausente"
    assert len(llamadas) == 2


def test_funcion_renombrada_no_se_ejecuta(preparado, monkeypatch):
    raiz, _, _ = preparado
    archivo = raiz / "banco_mvp.py"
    archivo.write_text(
        archivo.read_text(encoding="utf-8").replace(
            "def es_palindromo(", "def es_palindromo_v2("
        ),
        encoding="utf-8",
    )
    llamadas = []
    resumen, results, _ = _regresion(preparado, monkeypatch, llamadas)
    ausente = next(o for o in results["objetivos"] if o["funcion"] == "es_palindromo")
    assert resumen.requieren_corrida_nueva == 1
    assert ausente["motivo_regresion"] == "objetivo_ausente"
    assert len(llamadas) == 2


def test_modulo_movido_bloquea_sus_pruebas(preparado, monkeypatch):
    raiz, _, _ = preparado
    (raiz / "banco_mvp.py").rename(raiz / "banco_movido.py")
    llamadas = []
    resumen, results, _ = _regresion(preparado, monkeypatch, llamadas)
    assert resumen.requieren_corrida_nueva == 3
    assert llamadas == []
    assert {o["motivo_regresion"] for o in results["objetivos"]} == {
        "objetivo_ausente"
    }


def test_escenario_d_rechazadas_no_se_guardan_ni_reutilizan(preparado, monkeypatch):
    _, almacen, _ = preparado
    assert len(almacen.listar_specs()) == 6
    assert len(almacen.listar_pruebas_aprobadas()) == 3
    llamadas = []
    _regresion(preparado, monkeypatch, llamadas)
    assert len(llamadas) == 3
    assert all(not any(nombre in prueba for nombre in BUGS) for prueba in llamadas)


@pytest.mark.parametrize(
    ("valor", "motivo"),
    [(None, "huella_ausente"), ("hash-corrupto", "metadatos_corruptos")],
)
def test_huella_ausente_o_corrupta_se_bloquea(
    preparado, monkeypatch, valor, motivo
):
    _, almacen, _ = preparado
    ruta = next(
        p
        for p in almacen.carpeta_specs.glob("*.json")
        if not p.name.endswith(".spec.json")
        and json.loads(p.read_text(encoding="utf-8")).get("archivo_prueba")
    )
    spec = json.loads(ruta.read_text(encoding="utf-8"))
    if valor is None:
        spec.pop("huella_objetivo")
    else:
        spec["huella_objetivo"] = valor
    ruta.write_text(json.dumps(spec), encoding="utf-8")
    llamadas = []
    resumen, results, _ = _regresion(preparado, monkeypatch, llamadas)
    bloqueada = next(
        o for o in results["objetivos"] if o["decision"] == "requiere_corrida_nueva"
    )
    assert resumen.requieren_corrida_nueva == 1
    assert bloqueada["motivo_regresion"] == motivo
    assert len(llamadas) == 2


def test_identidad_incluye_modulo_si_hay_nombres_duplicados(tmp_path: Path):
    (tmp_path / "uno.py").write_text("def calcular():\n    return 1\n", encoding="utf-8")
    (tmp_path / "dos.py").write_text("def calcular():\n    return 2\n", encoding="utf-8")
    huellas = huellas_de_objetivos(tmp_path)
    assert ("uno.py", "calcular") in huellas
    assert ("dos.py", "calcular") in huellas
    assert huellas[("uno.py", "calcular")] != huellas[("dos.py", "calcular")]


def test_proyecto_sin_pruebas_aprobadas_falla_controladamente(tmp_path, config):
    (tmp_path / "modulo.py").write_text("def funcion():\n    return 1\n", encoding="utf-8")
    almacen = AlmacenProyecto(tmp_path)
    almacen.inicializar()
    run_id = almacen.crear_run()["run_id"]
    resumen = ejecutar_corrida(
        tmp_path, "reg", config, None, simulado=False, run_id=run_id
    )
    assert resumen.estado == "fallo_controlado"
    assert resumen.tokens == 0
    assert "No hay pruebas aprobadas" in resumen.motivo
