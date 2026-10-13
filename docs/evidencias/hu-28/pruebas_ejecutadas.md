# HU-28 — Pruebas ejecutadas

Fecha local: 2026-10-13. Rama: `feat/hu-28-endpoints-ejecucion-reporte`.

## Suite focalizada

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/orchestrator/test_corrida.py tests/orchestrator/test_orquestador.py tests/storage/test_vista_ejecucion.py tests/storage/test_vista_reporte.py tests/app/test_monitor_eventos.py tests/app/test_desktop_vista_previa.py tests/frontend/test_estructura.py tests/frontend/test_hu28_endpoints.py
```

Resultado: `106 passed in 1.56s`.

## Suite rápida

```powershell
.\.venv\Scripts\python.exe test.py --rapido
```

Resultado: `880 passed, 17 deselected in 13.66s`. Los 17 omitidos son pruebas marcadas `docker` o `red`, conforme al comportamiento documentado de `--rapido`.

## Lint

```powershell
.\.venv\Scripts\python.exe -m ruff check <archivos Python modificados y pruebas HU-28>
```

Resultado: `All checks passed!`.

## Sintaxis JavaScript

Se ejecutó `node --check` sobre los cuatro controladores modificados: Vista previa, Monitor, Ejecución e Informe. Resultado: código de salida 0 en los cuatro archivos.

## Prueba Docker del banco API

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests\orchestrator\test_en15_banco_api.py::test_banco_api_generado_detecta_exactamente_los_tres_bugs -vv
```

Resultado: `1 passed in 14.77s`. Ejecutó los seis tests generados dentro del sandbox Docker con `network_mode="none"`: tres endpoints correctos fueron aceptados y los tres bugs sembrados fueron detectados.

## Corrida real usada como evidencia

Se ejecutó `ejecutar_corrida()` sobre una copia temporal de `bench_api`, con `GeneratorAgent`, `ReviewerAgent`, IA simulada y sandbox Docker real. Resultado:

- corrida `20261013-101522-eb90`;
- estado `fin`, sin motivo de fallo;
- 6 endpoints procesados;
- 3 aceptados y 3 bugs detectados;
- 0 estancados y 0 sin veredicto;
- 13.154 s;
- 0 tokens reales y US$0.00;
- progreso corregido a 6 objetivos desde el evento del plan real.

La copia del proyecto se creó en el directorio temporal del sistema y no se versiona. Los artefactos conservados fueron saneados para retirar la ruta personal.

## Prueba visual

Se abrió el frontend real mediante un servidor HTTP local y Microsoft Edge headless por CDP. Se probaron 960 × 600, 1400 × 900 y 1920 × 1080. No se registraron excepciones ni mensajes de consola. El plugin Browser no estaba disponible, por lo que se usó esta alternativa local. Véanse `qa_visual.json` y `img/`.

CAP-01 a CAP-07 usan datos reales de la corrida o del análisis estático del banco. CAP-08 usa exclusivamente una entrada hostil controlada para demostrar que HTML se representa como texto y no se ejecuta.
