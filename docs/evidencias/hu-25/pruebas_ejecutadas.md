# HU-25 — Pruebas ejecutadas

Fecha local: 13/10/2026. Todas las rutas personales fueron omitidas de estas evidencias.

| Comando | Resultado real |
|---|---|
| `python test.py --rapido` | 899 passed, 19 deselected en 14.47 s |
| `pytest -q tests/orchestrator/test_hu25_regresion.py` | 10 passed en 2.51 s |
| `pytest -q tests/sandbox/test_hu25_regresion_docker.py -vv` | 2 passed en 41.74 s |
| Pruebas focalizadas de HU-25, almacenamiento y vistas | 57 passed en 2.64 s |
| `ruff check .` | All checks passed |
| `git diff --check` | Sin errores |

## Escenarios reales con Docker

- Corrida normal con IA simulada: 6 objetivos ejecutados; 3 aprobados y 3 bugs detectados.
- Regresión sin cambios: 3 pruebas aprobadas reejecutadas; 3 aprobadas, 0 tokens y US$ 0.00.
- Regresión con cambio directo: 2 pruebas ejecutadas y aprobadas; `es_palindromo` omitida con `requiere_corrida_nueva`, 0 intentos.
- Regresión por cambio indirecto: la huella del objetivo permaneció vigente, la prueba se ejecutó y registró `bug_detectado` al cambiar una dependencia privada.
- El test aprobado incluyó una conexión controlada y confirmó que el contenedor con `network_mode="none"` no tenía salida de red.

La captura visual se realizó en Chrome headless porque no había plugin Browser disponible. Se usó el frontend real y datos generados por las vistas Python reales. No sustituye una comprobación manual de humo en la ventana nativa pywebview.
