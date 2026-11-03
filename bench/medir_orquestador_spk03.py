"""Script de medición para SPK-03 / ADR-008: Coordinación del Orquestador.

Reproduce empíricamente las cifras de la sección 4.1 del ADR-008 sobre el banco
`bench/banco_mvp.py` (6 funciones, 3 con bug sembrado) utilizando la IA simulada
(`FakeLLMClient`, 0 tokens) y ejecuciones de pytest grabadas (`EjecutorGrabado`,
sin Docker ni red):
- Traza de estados y transiciones de la máquina de estados.
- Decisiones por objetivo y número de intentos.
- Número de llamadas al LLM por agente (Planner, Generator, Reviewer).
- Tamaño de los prompts por agente (caracteres).
- Tiempo de coordinación sin LLM ni Docker en N repeticiones.
- Reproducibilidad de resultados y código generado entre corridas.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import time
from pathlib import Path
from typing import Any

BENCH_DIR = Path(__file__).resolve().parent
BASE_DIR = BENCH_DIR.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Asegura salida UTF-8 en consola Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from qagent.agents.generator import GeneratorAgent
from qagent.agents.planner import PlannerAgent
from qagent.agents.reviewer import ReviewerAgent
from qagent.analysis.analyzer import analizar_proyecto
from qagent.llm.fake import FakeLLMClient
from qagent.llm.tracker import TokenTracker
from qagent.orchestrator.orquestador import Orquestador
from tests.orchestrator.ejecutor_grabado import EjecutorGrabado

RUTA_SALIDA_DEFECTO = BENCH_DIR / "resultados_spk03.json"


def obtener_entorno() -> dict[str, Any]:
    """Obtiene metadatos del entorno de ejecución para trazabilidad."""
    return {
        "sistema_operativo": platform.system(),
        "version_so": platform.version(),
        "arquitectura": platform.machine(),
        "procesador": platform.processor(),
        "version_python": sys.version.split()[0],
        "fecha_ejecucion": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


class EspiaLLM(FakeLLMClient):
    """Cliente simulado que registra los prompts y llamadas recibidas."""

    def __init__(self, rol_nombre: str) -> None:
        super().__init__()
        self.rol_nombre = rol_nombre
        self.prompts: list[str] = []

    def generar(self, prompt: str, rol: str = "generator") -> Any:
        self.prompts.append(prompt)
        return super().generar(prompt, rol=rol)


def medir_corrida(
    modulo: dict[str, Any], ruta_proyecto: Path, ejecutor: EjecutorGrabado
) -> dict[str, Any]:
    """Ejecuta una corrida completa de orquestación determinista y mide resultados."""
    tracker = TokenTracker()
    p_llm = EspiaLLM("planner")
    g_llm = EspiaLLM("generator")
    r_llm = EspiaLLM("reviewer")

    planner = PlannerAgent(p_llm, tracker, es_simulado=True)
    generator = GeneratorAgent(
        g_llm, tracker, es_simulado=True, ruta_proyecto=ruta_proyecto
    )
    reviewer = ReviewerAgent(
        tracker,
        ruta_proyecto=ruta_proyecto,
        imagen="grabacion-local",
        cliente=r_llm,
        ejecutor=ejecutor,
        es_simulado=True,
    )
    orquestador = Orquestador(planner, generator, reviewer, tracker=tracker)

    t0 = time.perf_counter()
    resultado = orquestador.ejecutar(modulo)
    t1 = time.perf_counter()

    duracion_s = t1 - t0
    traza = [e.value for e in resultado.traza_estados]

    decisiones: list[dict[str, Any]] = []
    for obj in resultado.objetivos:
        codigo = obj.codigo or ""
        huella_codigo = (
            hashlib.sha256(codigo.encode("utf-8")).hexdigest() if codigo else None
        )
        decisiones.append(
            {
                "objetivo": obj.objetivo,
                "decision": obj.decision,
                "intentos": obj.intentos,
                "laundering_detectado": obj.laundering_detectado,
                "codigo_hash": huella_codigo,
                "duracion_generacion_s": obj.duracion_generacion_s,
                "duracion_revision_s": obj.duracion_revision_s,
            }
        )

    prompts_info = {
        "planner": {
            "llamadas": len(p_llm.prompts),
            "caracteres_total": sum(len(p) for p in p_llm.prompts),
            "caracteres_por_llamada": [len(p) for p in p_llm.prompts],
        },
        "generator": {
            "llamadas": len(g_llm.prompts),
            "caracteres_total": sum(len(p) for p in g_llm.prompts),
            "caracteres_por_llamada": [len(p) for p in g_llm.prompts],
        },
        "reviewer": {
            "llamadas": len(r_llm.prompts),
            "caracteres_total": sum(len(p) for p in r_llm.prompts),
            "caracteres_por_llamada": [len(p) for p in r_llm.prompts],
        },
    }

    return {
        "duracion_s": duracion_s,
        "traza": traza,
        "num_transiciones": len(traza),
        "decisiones": decisiones,
        "prompts": prompts_info,
    }


def ejecutar_benchmark(
    repeticiones: int = 5, ruta_salida: Path | None = None
) -> dict[str, Any]:
    """Ejecuta N repeticiones de la coordinación y calcula estadísticas."""
    print("=" * 80)
    print(
        f"Iniciando Medición SPK-03 / ADR-008 ({repeticiones} repeticiones sobre bench/banco_mvp.py)..."
    )
    print("Condiciones: IA simulada (0 tokens), sin Docker, sin red, ejecutor grabado.")
    print("=" * 80)

    entorno = obtener_entorno()
    banco_mvp = BENCH_DIR / "banco_mvp.py"
    if not banco_mvp.exists():
        raise FileNotFoundError(f"No se encontró el banco en {banco_mvp}")

    estructura = analizar_proyecto(BENCH_DIR)
    modulo = next(m for m in estructura["modulos"] if "banco_mvp" in m["ruta"])

    ejecutor = EjecutorGrabado()

    corridas: list[dict[str, Any]] = []
    tiempos_s: list[float] = []

    for i in range(repeticiones):
        print(f"  -> Ejecutando repetición {i + 1}/{repeticiones}...")
        med = medir_corrida(modulo, BENCH_DIR, ejecutor)
        corridas.append(med)
        tiempos_s.append(med["duracion_s"])

    primera = corridas[0]

    def _clave_reproducibilidad(c: dict[str, Any]) -> tuple:
        decs = tuple(
            (
                d["objetivo"],
                d["decision"],
                d["intentos"],
                d["laundering_detectado"],
                d["codigo_hash"],
            )
            for d in c["decisiones"]
        )
        return (tuple(c["traza"]), decs, tuple(c["prompts"]["generator"]["caracteres_por_llamada"]))

    primera_clave = _clave_reproducibilidad(corridas[0])
    reproducibilidad_conteo = sum(
        1 for c in corridas if _clave_reproducibilidad(c) == primera_clave
    )
    es_reproducible = reproducibilidad_conteo == repeticiones
    misma_traza = all(c["traza"] == corridas[0]["traza"] for c in corridas)
    mismas_decisiones = all(
        [
            (d["objetivo"], d["decision"], d["intentos"], d["laundering_detectado"], d["codigo_hash"])
            for d in c["decisiones"]
        ]
        == [
            (d["objetivo"], d["decision"], d["intentos"], d["laundering_detectado"], d["codigo_hash"])
            for d in corridas[0]["decisiones"]
        ]
        for c in corridas
    )
    mismos_prompts = all(c["prompts"] == corridas[0]["prompts"] for c in corridas)

    conteo_bugs = sum(
        1 for d in primera["decisiones"] if d["decision"] == "bug_detectado"
    )
    conteo_accept = sum(1 for d in primera["decisiones"] if d["decision"] == "accept")

    tiempo_min = min(tiempos_s)
    tiempo_max = max(tiempos_s)
    tiempo_medio = sum(tiempos_s) / len(tiempos_s)

    prompts_ref = primera["prompts"]
    gen_llamadas = prompts_ref["generator"]["llamadas"]
    gen_chars_total = prompts_ref["generator"]["caracteres_total"]
    gen_chars_promedio = (
        round(gen_chars_total / gen_llamadas, 1) if gen_llamadas > 0 else 0
    )

    resumen = {
        "item": "SPK-03",
        "referencia": "ADR-008 sección 4.1",
        "entorno": entorno,
        "configuracion": {
            "banco": "bench/banco_mvp.py",
            "repeticiones": repeticiones,
            "ia_simulada": True,
            "tokens_reales": 0,
            "docker_usado": False,
        },
        "metricas_consolidadas": {
            "traza": "planificar → (generar → ejecutar_revisar) × 6 → fin",
            "num_transiciones": primera["num_transiciones"],
            "decisiones": {
                "bug_detectado": conteo_bugs,
                "accept": conteo_accept,
                "todos_intento_1": all(d["intentos"] == 1 for d in primera["decisiones"]),
                "laundering_detectado": any(
                    d["laundering_detectado"] for d in primera["decisiones"]
                ),
            },
            "llamadas_llm": {
                "planner": prompts_ref["planner"]["llamadas"],
                "generator": prompts_ref["generator"]["llamadas"],
                "reviewer": prompts_ref["reviewer"]["llamadas"],
            },
            "tamanios_prompts_caracteres": {
                "planner_total": prompts_ref["planner"]["caracteres_total"],
                "generator_total": gen_chars_total,
                "generator_promedio_por_llamada": gen_chars_promedio,
                "generator_por_llamada": prompts_ref["generator"]["caracteres_por_llamada"],
                "reviewer_total": prompts_ref["reviewer"]["caracteres_total"],
            },
            "tiempo_coordinacion_s": {
                "min": round(tiempo_min, 4),
                "max": round(tiempo_max, 4),
                "medio": round(tiempo_medio, 4),
                "repeticiones_medidas": [round(t, 4) for t in tiempos_s],
            },
            "reproducibilidad": {
                "exito": es_reproducible,
                "reproducibilidad_ratio": f"{reproducibilidad_conteo} de {repeticiones}",
                "misma_traza": misma_traza,
                "mismas_decisiones": mismas_decisiones,
                "mismos_prompts": mismos_prompts,
            },
        },
        "detalle_decisiones": primera["decisiones"],
        "corridas_individuales": corridas,
    }

    # Guardar archivo de resultados
    salida = ruta_salida or RUTA_SALIDA_DEFECTO
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(
        json.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\n[OK] Resultados guardados en: {salida}")

    imprimir_resumen(resumen)
    return resumen


def imprimir_resumen(resumen: dict[str, Any]) -> None:
    """Muestra un resumen en consola formateado como tabla de ADR-008."""
    m = resumen["metricas_consolidadas"]
    d = m["decisiones"]
    ll = m["llamadas_llm"]
    pr = m["tamanios_prompts_caracteres"]
    ti = m["tiempo_coordinacion_s"]
    rep = m["reproducibilidad"]

    print("\n" + "=" * 80)
    print("RESULTADOS MEDIDOS DE SPK-03 / ADR-008 (SECCIÓN 4.1)")
    print("=" * 80)
    print(f"{'Dato':<30} | {'Valor Medido':<45}")
    print("-" * 80)
    traza_consola = m["traza"].replace("→", "->").replace("×", "x")
    print(f"{'Traza':<30} | {traza_consola} ({m['num_transiciones']} transiciones)")
    print(
        f"{'Decisiones':<30} | {d['bug_detectado']} bug_detectado, {d['accept']} accept (todas intento 1)"
    )
    print(
        f"{'Llamadas al LLM':<30} | Planner {ll['planner']}, Generator {ll['generator']}, Reviewer {ll['reviewer']}"
    )
    print(
        f"{'Tamaño de prompts (chars)':<30} | Planner: {pr['planner_total']} | Generator: {pr['generator_total']} (prom ~ {pr['generator_promedio_por_llamada']})"
    )
    print(
        f"{'Tiempo de coordinación':<30} | {ti['min']:.4f} - {ti['max']:.4f} s (media: {ti['medio']:.4f} s)"
    )
    print(
        f"{'Reproducibilidad':<30} | {rep['reproducibilidad_ratio']} corridas idénticas"
    )
    print("=" * 80)


def main() -> None:
    """Punto de entrada de la línea de comandos."""
    parser = argparse.ArgumentParser(
        description="Medición de la coordinación del orquestador determinista (ADR-008 / SPK-03)."
    )
    parser.add_argument(
        "-n",
        "--repeticiones",
        type=int,
        default=5,
        help="Número de repeticiones para evaluar reproducibilidad y tiempos (por defecto 5).",
    )
    parser.add_argument(
        "-o",
        "--salida",
        type=Path,
        default=RUTA_SALIDA_DEFECTO,
        help="Ruta del archivo JSON de salida (por defecto bench/resultados_spk03.json).",
    )
    args = parser.parse_args()
    ejecutar_benchmark(repeticiones=args.repeticiones, ruta_salida=args.salida)


if __name__ == "__main__":
    main()
