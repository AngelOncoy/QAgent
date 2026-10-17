"""#70: «Repetir pruebas guardadas + profundizar» (`reg_deep`), sin IA y sin Docker.

El sandbox y mutmut se reemplazan por funciones que devuelven resultados conocidos.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from qagent.almacenamiento import AlmacenProyecto
from qagent.config import cargar_configuracion
from qagent.config.carga import RUTA_CONFIG
from qagent.orchestrator.corrida import ejecutar_corrida
from qagent.sandbox import MutacionFuncion, ResultadoMutacion, ResultadoSandbox

BANCO = Path(__file__).resolve().parents[2] / "bench"
COBERTURA = {
    "totals": {"percent_covered": 100.0, "num_branches": 0, "covered_branches": 0}
}
BUGS = ("calcular_descuento", "clasificar_edad", "buscar_elemento_mayor")
TODAS = [
    "calcular_descuento",
    "clasificar_edad",
    "buscar_elemento_mayor",
    "es_palindromo",
    "invertir_palabras",
    "formatear_moneda",
]


def ejecutor_generacion(_imagen, _proyecto, tests, _modulo):
    codigo = next(Path(tests).glob("test_*.py")).read_text(encoding="utf-8")
    fallo = any(f"import {nombre}" in codigo for nombre in BUGS)
    return ResultadoSandbox(
        1 if fallo else 0,
        "FAILED assert 1 == 2" if fallo else "1 passed",
        "",
        COBERTURA,
    )


def ejecutor_aprueba(_imagen, _proyecto, _tests, _modulo):
    return ResultadoSandbox(0, "1 passed", "", COBERTURA)


class MutadorGrabado:
    def __init__(self, puntuacion: float = 75.0) -> None:
        self.llamadas: list[list[str]] = []
        self.puntuacion = puntuacion

    def __call__(self, _imagen, _proyecto, _tests, modulo, funciones, _limites, **_):
        self.llamadas.append(list(funciones))
        return ResultadoMutacion(
            modulo,
            {n: MutacionFuncion(n, "ok", self.puntuacion, 3) for n in funciones},
        )


def seleccion(criticas: list[str]) -> list[dict]:
    return [
        {
            "ruta": "banco_mvp.py",
            "funciones": TODAS,
            "endpoints": [],
            "criticas": criticas,
        }
    ]


@pytest.fixture
def preparado(tmp_path: Path, monkeypatch):
    """Banco con tres pruebas aprobadas guardadas (Estándar, sin mutación)."""
    raiz = tmp_path / "banco"
    shutil.copytree(BANCO, raiz, ignore=shutil.ignore_patterns("*.md", "*.json"))
    almacen = AlmacenProyecto(raiz)
    almacen.inicializar()
    config = cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config
    run_id = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
    primero = ejecutar_corrida(
        raiz,
        "std",
        config,
        None,
        simulado=True,
        run_id=run_id,
        preparar_imagen=lambda _ruta: "imagen",
        ejecutor=ejecutor_generacion,
    )
    assert primero.aceptadas == 3
    return raiz, almacen, config


def repetir(
    preparado, monkeypatch, mutador, perfil="reg_deep", criticas=(), eventos=None
):
    raiz, almacen, config = preparado

    def prohibida(*_args, **_kwargs):
        raise AssertionError("Repetir pruebas guardadas no debe crear clientes LLM")

    monkeypatch.setattr("qagent.orchestrator.corrida.crear_cliente", prohibida)
    run_id = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
    resumen = ejecutar_corrida(
        raiz,
        perfil,
        config,
        None,
        simulado=False,
        run_id=run_id,
        preparar_imagen=lambda _ruta: "imagen",
        ejecutor=ejecutor_aprueba,
        seleccion=seleccion(list(criticas)),
        mutador=mutador,
        al_evento=eventos.append if eventos is not None else None,
    )
    carpeta = almacen.carpeta_run(run_id)
    results = json.loads((carpeta / "results.json").read_text(encoding="utf-8"))
    log = json.loads((carpeta / "log.json").read_text(encoding="utf-8"))
    return resumen, {o["funcion"]: o for o in results["objetivos"]}, log, run_id


def test_reg_deep_muta_solo_las_criticas_con_prueba_vigente_y_sin_ia(
    preparado, monkeypatch
) -> None:
    mutador = MutadorGrabado()

    resumen, objetivos, log, _ = repetir(
        preparado,
        monkeypatch,
        mutador,
        criticas=["es_palindromo", "invertir_palabras"],
    )

    assert mutador.llamadas == [["es_palindromo", "invertir_palabras"]]
    assert (resumen.tokens, resumen.costo_usd) == (0, 0.0)
    assert log["llamadas"] == []
    assert log["perfil"] == "reg_deep"
    for nombre in ("es_palindromo", "invertir_palabras"):
        assert objetivos[nombre]["critical"] is True
        assert objetivos[nombre]["metricas"]["mutation_score"] == 75.0
        assert objetivos[nombre]["mutacion"]["estado"] == "ok"
    assert objetivos["formatear_moneda"]["critical"] is False
    assert "mutacion" not in objetivos["formatear_moneda"]


def test_repetir_sin_profundizar_no_muta(preparado, monkeypatch) -> None:
    mutador = MutadorGrabado()

    _, objetivos, _, _ = repetir(
        preparado, monkeypatch, mutador, perfil="reg", criticas=["es_palindromo"]
    )

    assert mutador.llamadas == []
    assert objetivos["es_palindromo"]["metricas"]["mutation_score"] is None


def test_sin_cambios_reutiliza_el_resultado_guardado(preparado, monkeypatch) -> None:
    mutador = MutadorGrabado()
    eventos: list[dict] = []
    _, _, _, primera = repetir(
        preparado, monkeypatch, mutador, criticas=["es_palindromo"]
    )

    _, objetivos, _, _ = repetir(
        preparado, monkeypatch, mutador, criticas=["es_palindromo"], eventos=eventos
    )

    assert mutador.llamadas == [["es_palindromo"]]  # solo la primera vez
    mutacion = objetivos["es_palindromo"]["mutacion"]
    assert mutacion["reutilizada"] is True
    assert mutacion["run_origen"] == primera
    assert objetivos["es_palindromo"]["metricas"]["mutation_score"] == 75.0
    assert any("reutilizado de la corrida" in e["mensaje"] for e in eventos)


def test_si_cambia_otra_prueba_del_modulo_se_vuelve_a_mutar(
    preparado, monkeypatch
) -> None:
    _, almacen, _ = preparado
    mutador = MutadorGrabado()
    repetir(preparado, monkeypatch, mutador, criticas=["es_palindromo"])
    otra = next(almacen.carpeta_tests.glob("*invertir_palabras*.py"))
    otra.write_text(otra.read_text(encoding="utf-8") + "\n# cambio\n", encoding="utf-8")

    repetir(preparado, monkeypatch, mutador, criticas=["es_palindromo"])

    assert mutador.llamadas == [["es_palindromo"], ["es_palindromo"]]


def test_la_funcion_que_cambio_no_se_muta(preparado, monkeypatch) -> None:
    raiz, _, _ = preparado
    modulo = raiz / "banco_mvp.py"
    modulo.write_text(
        modulo.read_text(encoding="utf-8").replace(
            "return limpio == limpio[::-1]",
            "return limpio.lower() == limpio[::-1].lower()",
        ),
        encoding="utf-8",
    )
    mutador = MutadorGrabado()

    _, objetivos, _, _ = repetir(
        preparado,
        monkeypatch,
        mutador,
        criticas=["es_palindromo", "invertir_palabras"],
    )

    assert objetivos["es_palindromo"]["decision"] == "requiere_corrida_nueva"
    assert "mutacion" not in objetivos["es_palindromo"]
    assert mutador.llamadas == [["invertir_palabras"]]


def test_un_resultado_sin_puntuacion_no_se_guarda(preparado, monkeypatch) -> None:
    llamadas: list[list[str]] = []

    def mutador_lento(_imagen, _proyecto, _tests, modulo, funciones, _limites, **_):
        llamadas.append(list(funciones))
        return ResultadoMutacion(
            modulo,
            {
                n: MutacionFuncion(n, "tiempo_agotado", mensaje="lento")
                for n in funciones
            },
        )

    repetir(preparado, monkeypatch, mutador_lento, criticas=["es_palindromo"])
    _, objetivos, _, _ = repetir(
        preparado, monkeypatch, mutador_lento, criticas=["es_palindromo"]
    )

    assert llamadas == [["es_palindromo"], ["es_palindromo"]]
    assert objetivos["es_palindromo"]["mutacion"]["estado"] == "tiempo_agotado"
    assert "reutilizada" not in objetivos["es_palindromo"]["mutacion"]


def test_objetivos_repetibles_solo_con_prueba_vigente(preparado) -> None:
    from qagent.orchestrator.regresion import objetivos_repetibles

    raiz, almacen, _ = preparado
    aprobadas = {"es_palindromo", "invertir_palabras", "formatear_moneda"}
    assert {o["objetivo"] for o in objetivos_repetibles(raiz)} == aprobadas

    modulo = raiz / "banco_mvp.py"
    modulo.write_text(
        modulo.read_text(encoding="utf-8").replace(
            "return limpio == limpio[::-1]",
            "return limpio.lower() == limpio[::-1].lower()",
        ),
        encoding="utf-8",
    )
    next(almacen.carpeta_tests.glob("*formatear_moneda*.py")).unlink()

    assert objetivos_repetibles(raiz) == [
        {"modulo": "banco_mvp.py", "objetivo": "invertir_palabras"}
    ]


def test_profundo_deja_el_resultado_para_repetir_sin_mutar_de_nuevo(
    tmp_path: Path, monkeypatch
) -> None:
    raiz = tmp_path / "banco"
    shutil.copytree(BANCO, raiz, ignore=shutil.ignore_patterns("*.md", "*.json"))
    almacen = AlmacenProyecto(raiz)
    almacen.inicializar()
    config = cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config
    mutador = MutadorGrabado(puntuacion=80.0)
    run_profundo = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
    ejecutar_corrida(
        raiz,
        "deep",
        config,
        None,
        simulado=True,
        run_id=run_profundo,
        preparar_imagen=lambda _ruta: "imagen",
        ejecutor=ejecutor_generacion,
        seleccion=seleccion(["es_palindromo"]),
        mutador=mutador,
    )

    _, objetivos, _, _ = repetir(
        (raiz, almacen, config), monkeypatch, mutador, criticas=["es_palindromo"]
    )

    assert mutador.llamadas == [["es_palindromo"]]  # solo en Profundo
    mutacion = objetivos["es_palindromo"]["mutacion"]
    assert (mutacion["reutilizada"], mutacion["run_origen"]) == (True, run_profundo)
    assert objetivos["es_palindromo"]["metricas"]["mutation_score"] == 80.0
