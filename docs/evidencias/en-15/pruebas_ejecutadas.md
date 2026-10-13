# Evidencia textual de pruebas — EN-15

Fecha local: 13 de octubre de 2026.

## Suite rápida

```text
Comando: .\.venv\Scripts\python.exe test.py --rapido
Resultado final: 726 passed, 17 deselected in 9.00s
Resumen del runner: OK
```

Antes de la suite final se ejecutó `ruff check .`: `All checks passed!`. Los dos casos Docker parametrizados añadidos para verificar la limpieza explican el aumento de pruebas excluidas por `--rapido`.

## Prueba focalizada de EN-15 sin Docker

```text
Comando: python -m pytest -q tests/orchestrator/test_en15_banco_api.py -m "not docker" tests/agents/test_generator.py tests/agents/test_reviewer.py tests/llm/test_fake_llm.py tests/test_contracts.py tests/analysis/test_rutas.py
Resultado: 111 passed, 1 deselected in 0.65s
```

## Banco generado en Docker y aislamiento de red

```text
Comando: .\.venv\Scripts\python.exe -m pytest -q tests/orchestrator/test_en15_banco_api.py -m docker tests/sandbox/test_hu13_aislamiento.py::test_rn02_una_prueba_que_abre_una_conexion_de_red_falla -vv
Resultado: 4 passed, 1 deselected in 22.72s
```

La primera prueba generó seis tests con la IA simulada, los ejecutó mediante el Reviewer y verificó exactamente tres decisiones `accept` y tres `bug_detectado`. Dos casos adicionales ejecutaron un test correcto y un test que detecta un bug; después de cada uno, un verificador dentro del mismo contenedor confirmó que `app.dependency_overrides == {}`. La última prueba intentó abrir una conexión desde el mismo ejecutor y aprobó porque la conexión falló bajo `network_mode="none"`.

## Incidencias encontradas durante la validación

1. La primera ejecución del banco dejó los seis objetivos en `stalled`: el Reviewer consideraba cualquier nodo `try` como evasión, aunque la fixture necesita `try/finally`. Se restringió la regla a `try` con manejadores `except`; después, la prueba Docker aprobó.
2. La suite rápida detectó que validar con `ast.parse` dentro del Generator cortaba el reintento existente. El Orquestador ahora entrega el candidato rechazado al Reviewer solo para producir feedback; el Reviewer lo bloquea antes del sandbox. El segundo intento corregido conserva el límite máximo de tres.
3. Docker Desktop estaba detenido. Se inició y se confirmó Docker Engine 29.7.2.
4. FastAPI 0.143.0 muestra una advertencia de deprecación de Starlette sobre `httpx`/`httpx2`; las pruebas siguen siendo deterministas y el banco conserva únicamente FastAPI en `requirements.txt`.

No se utilizaron APIs LLM reales ni se registraron tokens o costos reales.
