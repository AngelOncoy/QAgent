import json
import sys

sys.path[:0] = ["src", "tests/orchestrator", "tests/storage"]

from fakes import MODULO
from test_registro import correr

from pyagent.contracts import RUN_LOG, validar
from pyagent.llm import cargar_precios
from pyagent.storage import escribir_corrida

precios = cargar_precios()  # precios reales de config.toml
tracker, resultado = correr(precios, decisiones=["retry", "accept"])
rutas = escribir_corrida(".", resultado, tracker, precios, perfil="deep")

log = json.loads(rutas.log.read_text(encoding="utf-8"))
results = json.loads(rutas.results.read_text(encoding="utf-8"))
validar(RUN_LOG, log)
validar(RUN_LOG, results)

print(f"Corrida guardada en: {rutas.carpeta}")
print("log.json y results.json validan contra run_log.schema.json\n")
print(f"{'Agente':<10} {'Llamadas':>8} {'Prompt':>8} {'Compl.':>8} {'Costo US$':>12} {'Tokens x precio':>16}")
for agente, t in log["totales_por_agente"].items():
    p = precios[agente]
    esperado = p.costo(t["prompt_tokens"], t["completion_tokens"])
    print(f"{agente:<10} {t['llamadas']:>8} {t['prompt_tokens']:>8} {t['completion_tokens']:>8} "
          f"{t['costo_usd']:>12.6f} {esperado:>16.6f}  {'OK' if abs(esperado - t['costo_usd']) < 1e-9 else 'DIFERENTE'}")
print(f"\nCosto total: US$ {log['total_costo_usd']:.6f}")
m = results["objetivos"][0]["metricas"]
print(f"Métricas de '{results['objetivos'][0]['funcion']}': paso={m['paso']}, "
      f"cobertura={m['cobertura_lineas']}%/{m['cobertura_ramas']}%, iteraciones={m['iteraciones']}, "
      f"mutation_score={m['mutation_score']}")