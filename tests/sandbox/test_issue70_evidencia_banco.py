"""#70, evidencia: repetir pruebas guardadas con mutación real sobre el banco propio.

Flujo completo con el sandbox Docker real (sin red) y mutmut real:

1. Estándar con la IA simulada: se aprueban `es_palindromo`, `invertir_palabras` y
   `formatear_moneda` (las otras tres tienen bugs sembrados). No hay mutación.
2. Repetir + profundizar (`reg_deep`): sin IA, mutmut sobre las críticas aprobadas.
3. Repetir otra vez sin cambios: se reutiliza el resultado, mutmut no se ejecuta.
4. Se cambia `es_palindromo`: requiere corrida nueva y no se muta; `invertir_palabras`
   se vuelve a mutar porque cambió el conjunto de pruebas del módulo.

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
CRITICAS = ["es_palindromo", "invertir_palabras", "calcular_descuento"]


def test_repetir_con_mutacion_real_reutiliza_y_respeta_los_cambios(
    tmp_path: Path, imagen_base, monkeypatch
):
    raiz = tmp_path / "banco"
    shutil.copytree(
        BANCO, raiz, ignore=shutil.ignore_patterns("*.md", "*.json", ".qagent")
    )
    almacen = AlmacenProyecto(raiz)
    almacen.inicializar()
    config = cargar_configuracion(RUTA_CONFIG, "no-existe.env", simulado=True).config
    llamadas: list[list[str]] = []

    def mutador_real(*args, **kwargs):
        llamadas.append(list(args[4]))
        return ejecutar_mutacion(*args, **kwargs)

    seleccion = [
        {
            "ruta": "banco_mvp.py",
            "funciones": FUNCIONES,
            "endpoints": [],
            "criticas": CRITICAS,
        }
    ]

    def correr(perfil: str, simulado: bool):
        run_id = almacen.crear_run(tipos_prueba=["funcion"])["run_id"]
        resumen = ejecutar_corrida(
            raiz,
            perfil,
            config,
            None,
            simulado=simulado,
            run_id=run_id,
            preparar_imagen=lambda _ruta: imagen_base,
            seleccion=seleccion,
            mutador=mutador_real,
        )
        carpeta = almacen.carpeta_run(run_id)
        results = json.loads((carpeta / "results.json").read_text(encoding="utf-8"))
        log = json.loads((carpeta / "log.json").read_text(encoding="utf-8"))
        contracts.validar(contracts.RUN_LOG, results)
        return run_id, resumen, {o["funcion"]: o for o in results["objetivos"]}, log

    # 1. Pruebas aprobadas con Estándar (IA simulada), sin mutación.
    _, base, _, _ = correr("std", simulado=True)
    assert (base.aceptadas, base.bugs_detectados) == (3, 3)
    assert llamadas == []

    def ia_prohibida(*_args, **_kwargs):
        raise AssertionError("Repetir pruebas guardadas no debe crear clientes LLM")

    monkeypatch.setattr("qagent.orchestrator.corrida.crear_cliente", ia_prohibida)

    # 2. Repetir + profundizar: mutmut real sobre las críticas aprobadas, sin IA.
    run_mutacion, rep, objetivos, log = correr("reg_deep", simulado=False)
    assert (rep.aceptadas, rep.tokens, rep.costo_usd) == (3, 0, 0.0)
    assert log["llamadas"] == []
    assert llamadas == [["es_palindromo", "invertir_palabras"]]
    for nombre in ("es_palindromo", "invertir_palabras"):
        mutacion = objetivos[nombre]["mutacion"]
        assert mutacion["estado"] == "ok", mutacion
        assert "reutilizada" not in mutacion
        assert objetivos[nombre]["metricas"]["mutation_score"] is not None
    assert "calcular_descuento" not in objetivos  # su prueba no se aprobó nunca
    assert "mutacion" not in objetivos["formatear_moneda"]  # no está marcada
    scores = {n: objetivos[n]["metricas"]["mutation_score"] for n in CRITICAS[:2]}

    # 3. Sin cambios: se reutiliza el resultado y mutmut no vuelve a ejecutarse.
    _, _, objetivos, _ = correr("reg_deep", simulado=False)
    assert llamadas == [["es_palindromo", "invertir_palabras"]]
    for nombre, score in scores.items():
        mutacion = objetivos[nombre]["mutacion"]
        assert (mutacion["reutilizada"], mutacion["run_origen"]) == (True, run_mutacion)
        assert objetivos[nombre]["metricas"]["mutation_score"] == score

    # 4. Cambia es_palindromo: no se muta; invertir_palabras se vuelve a mutar porque
    #    ya no se usan las mismas pruebas del módulo.
    modulo = raiz / "banco_mvp.py"
    modulo.write_text(
        modulo.read_text(encoding="utf-8").replace(
            "return limpio == limpio[::-1]",
            "return limpio.lower() == limpio[::-1].lower()",
        ),
        encoding="utf-8",
    )
    _, cambio, objetivos, _ = correr("reg_deep", simulado=False)
    assert cambio.requieren_corrida_nueva == 1
    assert objetivos["es_palindromo"]["decision"] == "requiere_corrida_nueva"
    assert "mutacion" not in objetivos["es_palindromo"]
    assert llamadas[-1] == ["invertir_palabras"]
    assert objetivos["invertir_palabras"]["mutacion"]["estado"] == "ok"
    assert "reutilizada" not in objetivos["invertir_palabras"]["mutacion"]

    # Resumen legible para la evidencia (se ve con `pytest -s`).
    print(f"\nMutation Score en la primera repetición: {scores}")
    print(f"Llamadas a mutmut en las tres repeticiones: {llamadas}")
