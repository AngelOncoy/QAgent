"""EN-09, evidencia de aceptación: mutation testing real sobre el banco propio.

Corrida Profundo sobre `bench/banco_mvp.py` con la IA simulada, el sandbox Docker real
(sin red) y mutmut real. El banco tiene bugs sembrados: con la IA simulada se aprueban
`es_palindromo`, `invertir_palabras` y `formatear_moneda`, y las otras tres terminan en
`bug_detectado`. Se marcan como críticas dos aprobadas y una con bug, y una aprobada se
deja sin marcar, para comprobar que mutmut solo trabaja sobre las críticas aprobadas
(RN-04) y devuelve el Mutation Score y los sobrevivientes por función.

Se omite si Docker no está disponible.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from qagent import contracts
from qagent.almacenamiento import AlmacenProyecto
from qagent.config import cargar_configuracion
from qagent.config.carga import RUTA_CONFIG
from qagent.orchestrator.corrida import ejecutar_corrida
from qagent.sandbox import ejecutar_mutacion
from qagent.sandbox.mutacion import funcion_del_mutante
from qagent.storage.vista_reporte import leer_detalle, vista_reporte

pytestmark = pytest.mark.docker

BANCO = Path(__file__).resolve().parents[2] / "bench"
FUNCIONES = [
    "calcular_descuento",
    "clasificar_edad",
    "buscar_elemento_mayor",
    "es_palindromo",
    "invertir_palabras",
    "formatear_moneda",
]
CRITICAS_APROBADAS = ["es_palindromo", "invertir_palabras"]
CRITICA_CON_BUG = "calcular_descuento"
APROBADA_NO_CRITICA = "formatear_moneda"


def test_mutmut_solo_sobre_criticas_aprobadas_del_banco(tmp_path: Path, imagen_base):
    raiz = tmp_path / "banco"
    shutil.copytree(
        BANCO, raiz, ignore=shutil.ignore_patterns("*.md", "*.json", ".qagent")
    )
    almacen = AlmacenProyecto(raiz)
    almacen.inicializar()
    config = cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config
    llamadas: list[dict] = []
    eventos: list[dict] = []

    def mutador_real(*args, **kwargs):
        resultado = ejecutar_mutacion(*args, **kwargs)
        llamadas.append({"modulo": args[3], "funciones": list(args[4]), "r": resultado})
        return resultado

    run_id = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
    resumen = ejecutar_corrida(
        raiz,
        "deep",
        config,
        None,
        simulado=True,
        run_id=run_id,
        preparar_imagen=lambda _ruta: imagen_base,
        seleccion=[
            {
                "ruta": "banco_mvp.py",
                "funciones": FUNCIONES,
                "endpoints": [],
                "criticas": [*CRITICAS_APROBADAS, CRITICA_CON_BUG],
            }
        ],
        mutador=mutador_real,
        al_evento=eventos.append,
    )

    assert (resumen.aceptadas, resumen.bugs_detectados) == (3, 3)

    # 1. mutmut se llamó una vez y solo con las críticas aprobadas.
    [llamada] = llamadas
    assert llamada["modulo"] == "banco_mvp.py"
    assert llamada["funciones"] == CRITICAS_APROBADAS
    mutados = {
        funcion_del_mutante(s.mutante)
        for f in llamada["r"].funciones.values()
        for s in f.sobrevivientes
    }
    assert mutados <= set(CRITICAS_APROBADAS)

    # 2. results.json: Mutation Score y sobrevivientes solo en las críticas aprobadas.
    results = json.loads(
        (almacen.carpeta_run(run_id) / "results.json").read_text(encoding="utf-8")
    )
    contracts.validar(contracts.RUN_LOG, results)
    objetivos = {o["funcion"]: o for o in results["objetivos"]}
    for nombre in CRITICAS_APROBADAS:
        objetivo = objetivos[nombre]
        assert objetivo["mutacion"]["estado"] == "ok", objetivo["mutacion"]
        score = objetivo["metricas"]["mutation_score"]
        assert score is not None and 0 <= score <= 100
        assert objetivo["controles"]["mutation"] is (score >= 60)
        for sobreviviente in objetivo["mutacion"]["sobrevivientes"]:
            assert funcion_del_mutante(sobreviviente["mutante"]) == nombre
            assert sobreviviente["linea"] is not None and sobreviviente["cambio"]
    for nombre in (CRITICA_CON_BUG, APROBADA_NO_CRITICA):
        assert "mutacion" not in objetivos[nombre]
        assert objetivos[nombre]["metricas"]["mutation_score"] is None

    # 3. El informe explica cada caso.
    funciones = {
        f["funcion"]: f
        for f in vista_reporte(results, leer_detalle(raiz, run_id))["funciones"]
    }
    assert funciones[CRITICA_CON_BUG]["controles"][4]["estado"] == "no_aplica"
    assert "Sin prueba aprobada" in funciones[CRITICA_CON_BUG]["controles"][4]["nota"]
    assert funciones[APROBADA_NO_CRITICA]["controles"][4]["estado"] == "no_aplica"

    # 4. El Monitor anunció la mutación solo de las críticas aprobadas.
    mensajes = [e["mensaje"] for e in eventos]
    assert any(
        "sobre 2 función(es) crítica(s): es_palindromo, invertir_palabras" in m
        for m in mensajes
    )

    # Resumen legible para la evidencia (se ve con `pytest -s`).
    for nombre in CRITICAS_APROBADAS:
        mutacion = objetivos[nombre]["mutacion"]
        print(
            f"\n{nombre}: Mutation Score {mutacion['puntuacion']} % · "
            f"{mutacion['detectados']} detectados · "
            f"{len(mutacion['sobrevivientes'])} sobrevivientes"
        )
        for s in mutacion["sobrevivientes"]:
            print(f"    línea {s['linea']}: {s['cambio']}")
