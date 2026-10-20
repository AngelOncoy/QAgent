# Evidencia textual de pruebas — EN-15

Fecha local: 13 de octubre de 2026.
Base integrada: `origin/develop@3127132` (HU-27 y EN-16).

## Rebase y adaptación

Se creó primero el commit local de respaldo `2fb38b5` sin hacer push. Después se rebasó la rama sobre `origin/develop`; el commit reescrito quedó como `d2b9539`.

La primera prueba de compatibilidad posterior al rebase detectó que el contrato de EN-15 exigía `aplicacion` y `dependencias`, mientras el Planner actualizado de HU-27 todavía no los emitía. Ese resultado fallido no se contabiliza como aprobación. Se adaptó el Planner mediante análisis estático y se añadió preparación contractual para los casos que necesitan un elemento existente.

## Prueba focalizada posterior al rebase

```text
Comando: .\.venv\Scripts\python.exe -m pytest -q tests/agents/test_planner_endpoints.py tests/agents/test_reviewer_endpoints.py tests/agents/test_generator.py tests/llm/test_fake_llm.py tests/test_contracts.py tests/orchestrator/test_en15_banco_api.py -m "not docker"
Resultado: 130 passed, 3 deselected in 1.17s
```

Incluye `test_corrida_de_la_api_de_prueba_con_generator_real`, que ejecuta la corrida con `PlannerAgent`, `GeneratorAgent` y `ReviewerAgent`. La antigua clase auxiliar `GeneratorAMano` fue retirada.

## Suite rápida

```text
Comando: .\.venv\Scripts\python.exe test.py --rapido
Resultado: 780 passed, 17 deselected in 14.11s
Resumen del runner: OK (14.6s)
```

Antes de la suite se ejecutó `ruff check .`: `All checks passed!`.

## Banco generado en Docker y aislamiento de red

```text
Comando: .\.venv\Scripts\python.exe -m pytest -q tests/orchestrator/test_en15_banco_api.py -m docker tests/sandbox/test_hu13_aislamiento.py::test_rn02_una_prueba_que_abre_una_conexion_de_red_falla -vv
Resultado: 4 passed, 1 deselected in 21.24s
```

El banco usa contratos producidos por el Planner real, tests producidos por `GeneratorAgent` y el ejecutor Docker real del Reviewer. La prueba de aislamiento aprobó porque la conexión de red falló bajo `network_mode="none"`.

Resultados observados:

- `GET /salud`, `POST /items` y `GET /items`: `accept`.
- `GET /items/{item_id}`: estado 500 frente a 404 esperado.
- `DELETE /items/{item_id}`: estado 200 frente a 204 esperado.
- `GET /descuento`: `precio_final=20.0` frente a 80.0 esperado.
- Cero errores técnicos, timeouts y contenedores residuales.
- Cero tokens reales y costo LLM real de US$0.00, porque se usó IA simulada.

## Limpieza de dependency_overrides

Los módulos de endpoints con `Depends` instalan un reemplazo controlado, preparan el estado indicado por el contrato y restauran los overrides mediante `try/finally`:

- módulo correcto `POST /items`: 4 pruebas aprobadas;
- módulos con defecto: 1 prueba fallida esperada y 3 pruebas aprobadas, incluida la comprobación posterior de limpieza.

## Capturas

Las capturas CAP-01 a CAP-06 ya conservadas en `img/` son capturas reales de la primera validación de EN-15. Permanecen como evidencia histórica y no se usan para atribuirles los conteos posteriores al rebase. Los resultados vigentes y reproducibles están en este archivo, `resultado_banco_sandbox.json`, `validacion_tests_generados.json` y los tests automatizados.

No se utilizaron APIs LLM reales ni se registraron credenciales.

En la verificación final, una primera invocación omitió las cuatro pruebas porque Docker Desktop estaba detenido. Se inició el motor, se confirmó Docker Engine 29.7.2 y se repitió el mismo comando con el resultado aprobado registrado arriba.
