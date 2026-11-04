# Medición del Agente Recomendador (SPK #201)

Fecha: 2026-11-04 09:35 · repeticiones: 3 · tiempo máximo: 30 s.

Línea base: las reglas del paso 1 (0 tokens, sin red, determinista).

## deepseek/deepseek-flash

[MEDIDO] Llamadas: 9 · usadas: 9 · descartes: ninguno.

| Proyecto | Llamadas | Usadas | Tokens (ent./sal.) | Costo (US$) | Latencia p50 / p95 | Cambia orden | Omite tipos | Cambia motivo |
|---|---|---|---|---|---|---|---|---|
| fastapi | 3 | 3 | 1833 / 1053 | 0.001814 | 3.056 s / 4.141 s | 0 | 0 | 3 |
| mixto | 3 | 3 | 1929 / 1904 | 0.002864 | 4.458 s / 5.644 s | 0 | 0 | 3 |
| solo_funciones | 3 | 3 | 1683 / 986 | 0.001688 | 2.771 s / 3.026 s | 0 | 0 | 3 |

Costo total: US$ 0.006365 · por llamada: US$ 0.000707 · latencia p50 / p95: 3.056 s / 5.249 s.

## Pendiente

- Revisión a ciegas de una persona del equipo (`revision/planilla.csv`).
- Conclusión sobre el modo por defecto, anotada en ADR-011.
