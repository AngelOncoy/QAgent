# EN-15 — Generator de tests con TestClient y banco de la API

> Informe acumulativo. Fecha de la validación local: 13 de octubre de 2026.
> Rama: `feat/en-15-generator-testclient`. No se realizaron commit, push ni Pull Request.

## 1. Ítem EN-15 del backlog

| Campo | Valor |
|---|---|
| Ítem | EN-15 — Generator de tests con TestClient y banco de la API |
| Tipo | Habilitador (EN) |
| Épica | 9 |
| Sprint | 1 |
| Prioridad | Alta |
| Estado en Notion informado al iniciar | Doing |
| Estado técnico de este informe | Terminado dentro del alcance de EN-15: CA-01 a CA-06 verificados |

## 2. Objetivo y descripción

Extender el Generator de QAgent para crear una prueba pytest con `TestClient` por endpoint FastAPI, basándose únicamente en el contrato. Para endpoints con `Depends`, la prueba debe instalar y restaurar `app.dependency_overrides`. El código generado debe validarse con `ast.parse`, utilizar la IA simulada con cero tokens reales y ejecutarse dentro del sandbox Docker sin red.

El alcance conserva la generación existente para funciones Python. No se modificó la interfaz visual ni se integró un modelo LLM real.

## 3. Criterios de aceptación originales

- **CA-01:** el Generator escribe un test con TestClient por endpoint, con aserciones y, cuando el contrato lo trae, sobre JSON, usando valores del contrato.
- **CA-02:** reemplaza cada `Depends` con `app.dependency_overrides`, lo limpia al terminar cada test y nunca reemplaza la ruta ni sus modelos.
- **CA-03:** el código generado pasa `ast.parse`; los reintentos usan feedback del Reviewer y se limitan a tres.
- **CA-04:** la IA simulada ofrece una plantilla TestClient y grabaciones `api_mvp.py::<MÉTODO> <ruta>`, con cero tokens reales.
- **CA-05:** existe un banco con seis endpoints —tres correctos y tres con bug—, `requirements.txt` solo con FastAPI y `bugs.md`.
- **CA-06:** los tests generados corren en el sandbox sin red y los tres endpoints defectuosos fallan exactamente como indica `bugs.md`.

Estos son los criterios entregados para EN-15; no son criterios añadidos durante la implementación.

## 4. Estado inicial del Generator

Al iniciar, `GeneratorAgent` generaba pruebas de funciones a partir de contratos y retiraba cercos Markdown, pero no diferenciaba contratos de endpoint ni validaba su salida directamente mediante `ast.parse`. El Reviewer sí efectuaba una comprobación sintáctica posterior.

La IA simulada solo producía tests de funciones. El esquema de Planner ya describía casos HTTP de forma parcial, pero no exigía el símbolo de la aplicación ni el reemplazo de cada dependencia.

## 5. Diagnóstico y dependencias

### Confirmado antes de cambiar código

- El analizador de EN-14 ya descubre endpoints y entrega método, ruta, manejador, firma, parámetros y dependencias mediante análisis AST.
- El sandbox existente instala las dependencias del proyecto al preparar la imagen y ejecuta pytest con `network_mode="none"`.
- La imagen base contiene pytest, coverage y httpx; el banco solo necesita declarar FastAPI.
- El Orquestador ya admite `plan_reutilizado`, feedback y un máximo contractual de tres intentos.
- El Planner y `ejecutar_corrida()` siguen recorriendo únicamente `modulo["funciones"]`; todavía no convierten automáticamente `modulo["endpoints"]` en contratos ni los seleccionan desde la aplicación.

### Decisión de alcance

No se reescribieron Planner ni corrida porque pertenecen a la integración de descubrimiento/planificación y exceden el cambio focal del Generator. Para validar EN-15, la prueba de integración combina la salida real del analizador con grabaciones deterministas, valida los contratos y los entrega al Orquestador como `plan_reutilizado`.

## 6. Diseño técnico de la solución

El flujo validado es:

1. Analizar estáticamente `bench_api/api_mvp.py`.
2. Construir un contrato de endpoint con aplicación, dependencias y casos grabados.
3. Validar el contrato JSON.
4. Generar una prueba TestClient determinista.
5. Ejecutar `ast.parse` dentro del Generator.
6. Entregar el candidato al Reviewer.
7. Ejecutar pytest y cobertura en Docker con red deshabilitada.
8. Aceptar endpoints correctos o registrar `bug_detectado` cuando el resultado real contradice el contrato.

## 7. Implementación de tests TestClient

El Generator ahora incluye instrucciones específicas para contratos `tipo="endpoint"`. La salida simulada:

- importa `fastapi.testclient.TestClient` y la aplicación declarada;
- usa `client.request()` con el método y ruta del contrato;
- envía query, path, body o headers cuando el caso los contiene;
- comprueba `response.status_code`;
- compara `response.json()` de forma exacta o por contenido según el contrato;
- no calcula el valor esperado a partir de la implementación defectuosa.

La generación previa para contratos de función permanece disponible y la suite rápida la cubre.

## 8. Implementación de dependency_overrides

Para cada dependencia declarada, la prueba importa la función original y su reemplazo controlado. Una fixture:

1. copia los overrides anteriores;
2. instala los reemplazos;
3. entrega `TestClient(app, raise_server_exceptions=False)`;
4. en `finally`, limpia el diccionario y restaura la copia original.

No se sustituye el manejador de la ruta ni un modelo Pydantic. La prueba Docker adicional verificó el estado global en el mismo contenedor después de:

- un test exitoso: `2 passed` (test generado y verificador de limpieza);
- un test que detectó un bug: `1 failed, 1 passed`; el segundo fue el verificador `app.dependency_overrides == {}`.

## 9. Validación AST y reintentos

`GeneratorAgent.generar()` ejecuta `ast.parse` después de limpiar la respuesta. Una salida vacía o con `SyntaxError` produce `ErrorRespuestaGenerator` y conserva el candidato rechazado para diagnóstico.

El Orquestador entrega ese candidato al Reviewer únicamente para obtener feedback estructurado; el Reviewer lo bloquea antes del sandbox. El siguiente intento recibe ese feedback. Se mantiene `MAX_INTENTOS_CONTRATO = 3`, y las pruebas existentes verifican corrección en el segundo intento, agotamiento y rechazo de una configuración mayor que tres.

## 10. Implementación de IA simulada

`FakeLLMClient` distingue contratos de función y endpoint. Las seis claves añadidas a `bench/ia_simulada.json` siguen exactamente el patrón requerido:

- `api_mvp.py::GET /salud`
- `api_mvp.py::POST /items`
- `api_mvp.py::GET /items`
- `api_mvp.py::GET /items/{item_id}`
- `api_mvp.py::DELETE /items/{item_id}`
- `api_mvp.py::GET /descuento`

La generación fue determinista. El `TokenTracker` registró **0 tokens** y **US$0.00**; esto solo prueba el modo simulado, no el comportamiento de un LLM real.

## 11. Banco API de seis endpoints

| Endpoint | Tipo | Resultado esperado del test |
|---|---|---|
| `GET /salud` | Correcto | 200 y JSON de salud |
| `POST /items` | Correcto | 201 y elemento creado |
| `GET /items` | Correcto | 200 y lista vacía inicial |
| `GET /items/{item_id}` | Bug 1 | Debía devolver 404; devuelve 500 |
| `DELETE /items/{item_id}` | Bug 2 | Debía devolver 404; devuelve 200 para un id inexistente |
| `GET /descuento` | Bug 3 | Debía devolver precio final 80.0; devuelve 20.0 |

`Repositorio` es local y se usa como reemplazo de `obtener_repositorio`; no llama a bases de datos ni servicios externos. `bench_api/requirements.txt` contiene una única dependencia fijada: `fastapi==0.143.0`.

## 12. Archivos agregados y modificados

### Código y contratos

| Archivo | Cambio |
|---|---|
| `src/pyagent/agents/generator.py` | Rama de prompt HTTP, validación AST y error con candidato rechazado. |
| `src/pyagent/agents/reviewer.py` | Oráculo HTTP/JSON, cobertura del manejador y permiso para `try/finally` sin `except`. |
| `src/pyagent/llm/fake.py` | Generador determinista de TestClient y fixtures de overrides. |
| `src/pyagent/orchestrator/orquestador.py` | Convierte el rechazo sintáctico en feedback del Reviewer sin ejecutar el candidato. |
| `contracts/planner_contract.v2.schema.json` | Aplicación y reemplazos de dependencias requeridos para endpoints. |
| `contracts/ejemplos/planner_contract.endpoint.json` | Ejemplo actualizado. |
| `bench/ia_simulada.json` | Seis grabaciones HTTP. |
| `bench_api/api_mvp.py` | Banco de seis endpoints y tres defectos deterministas. |
| `bench_api/requirements.txt` | Solo FastAPI, con versión reproducible. |
| `bench_api/bugs.md` | Resultado correcto y defecto sembrado por endpoint. |

### Pruebas y evidencias

| Archivo o carpeta | Contenido |
|---|---|
| `tests/orchestrator/test_en15_banco_api.py` | Generación de seis tests, ejecución Docker y limpieza de overrides. |
| `tests/agents/test_generator.py` | Contrato endpoint, prompt y rechazo AST. |
| `tests/agents/test_reviewer.py` | Oráculo HTTP/JSON. |
| `tests/llm/test_fake_llm.py` | Plantilla, claves y cero tokens. |
| `tests/test_contracts.py` | Requisitos nuevos del contrato. |
| `tests/almacenamiento/test_proyecto.py` | Fixture compatible con el esquema. |
| `tests-generados/` | Seis copias saneadas y normalizadas de los tests generados. |
| `resultado_banco_sandbox.json` | Resultado estructurado de la ejecución real. |
| `validacion_tests_generados.json` | Sintaxis y hashes SHA-256. |
| `pruebas_ejecutadas.md` | Comandos, resultados e incidencias. |

## 13. Explicación de cada cambio

Los cambios del Generator y del simulador implementan la producción de pruebas HTTP. El esquema evita que un endpoint llegue sin el símbolo de la aplicación o sin un reemplazo identificable. El Reviewer interpreta el resultado esperado como HTTP/JSON y mide cobertura sobre el manejador. El ajuste del Orquestador conserva el ciclo de feedback aun cuando el Generator detecta el error antes del sandbox. El banco y sus grabaciones proporcionan una entrada reproducible sin red ni tokens.

No se añadieron dependencias al producto. La advertencia de compatibilidad observada entre Starlette y httpx se registra en Riesgos.

## 14. Pruebas unitarias

```text
pytest focalizado sin Docker:
111 passed, 1 deselected in 0.65s

suite rápida general final:
726 passed, 17 deselected in 9.00s

ruff check .:
All checks passed!
```

La suite cubrió compatibilidad con funciones, contratos, AST válido e inválido, uso de feedback, límite de intentos y generación simulada.

## 15. Pruebas de integración

`test_genera_un_testclient_valido_por_cada_endpoint_con_cero_tokens` construye seis contratos a partir del análisis real del banco, los valida y genera exactamente seis módulos con TestClient. Cada módulo pasa `ast.parse`, realiza una petición y contiene aserción de estado. Tokens y costo permanecen en cero.

La integración con el Orquestador real usa `plan_reutilizado`. Esto satisface el alcance del Generator y no sustituye una prueba futura de selección automática desde `ejecutar_corrida()`, funcionalidad que no forma parte del texto de CA-06.

## 16. Pruebas reales en sandbox

Comando final:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/orchestrator/test_en15_banco_api.py -m docker tests/sandbox/test_hu13_aislamiento.py::test_rn02_una_prueba_que_abre_una_conexion_de_red_falla -vv
```

Resultado: **4 passed, 1 deselected in 22.72s**.

Se utilizó Docker Engine 29.7.2, Python 3.11.17 dentro de la imagen y `network_mode="none"`. La prueba explícita de conexión aprobó porque la apertura del socket fue rechazada. Después de la ejecución había cero contenedores con la etiqueta `pyagent=sandbox`.

## 17. Resultados del banco

| Objetivo | Decisión del Reviewer | Intentos | Evidencia del defecto |
|---|---|---:|---|
| `GET /salud` | `accept` | 1 | Test aprobado |
| `POST /items` | `accept` | 1 | Test aprobado |
| `GET /items` | `accept` | 1 | Test aprobado |
| `GET /items/{item_id}` | `bug_detectado` | 1 | Estado real 500, esperado 404 |
| `DELETE /items/{item_id}` | `bug_detectado` | 1 | Estado real 200, esperado 404 |
| `GET /descuento` | `bug_detectado` | 1 | `precio_final` real 20.0, esperado 80.0 |

Resultado global: **3 endpoints correctos aceptados y 3 defectos intencionales detectados**, sin errores técnicos ni timeouts.

## 18. Errores encontrados y correcciones

1. **`try/finally` rechazado como evasión.** La primera ejecución dejó seis objetivos `stalled` porque el Reviewer bloqueaba todo nodo `try`. Se restringió la regla a bloques con `except`; `finally` queda permitido para limpiar overrides.
2. **La validación temprana cortaba el reintento.** Al mover `ast.parse` al Generator, una regresión existente no podía recibir feedback. El candidato inválido ahora llega solo al Reviewer, que lo rechaza antes de Docker y devuelve el diagnóstico.
3. **Fixture de contrato desactualizada.** La suite general detectó un endpoint de prueba sin `aplicacion` ni `dependencias`; se actualizó la fixture.
4. **Docker Desktop no estaba activo.** Se inició localmente antes de las verificaciones Docker.
5. **Advertencia de Starlette/httpx.** No alteró resultados; permanece como riesgo técnico.

Los primeros intentos fallidos no se ocultan ni se cuentan como evidencia aprobada.

## 19. Evidencias y capturas

Evidencia textual conservada:

- [`pruebas_ejecutadas.md`](pruebas_ejecutadas.md)
- [`resultado_banco_sandbox.json`](resultado_banco_sandbox.json)
- [`validacion_tests_generados.json`](validacion_tests_generados.json)
- [`tests-generados/`](tests-generados/)

No se fabricaron capturas ni terminales simuladas. Las siguientes imágenes proceden de comandos ejecutados manualmente en la terminal local y se copiaron sin edición desde `Pictures/Screenshots`. CAP-07 no aplica porque EN-15 no modificó ni ejecutó una vista con métricas.

### CAP-01 — TestClient y aserciones contractuales

Fuente: contenido real de `tests-generados/test_crear_item.py`.

![CAP-01 — TestClient y aserciones](img/CAP-01-testclient-aserciones.png)

### CAP-02 — dependency_overrides y limpieza defensiva

Fuente: contenido real de `tests-generados/test_item_inexistente.py`; muestra copia, instalación y restauración de overrides mediante `finally`.

![CAP-02 — dependency_overrides](img/CAP-02-dependency-overrides.png)

### CAP-03 — Validación AST, feedback y máximo de reintentos

Fuente: pytest focalizado de Generator, HU-11 y HU-14. Resultado visible: 4 pruebas aprobadas.

![CAP-03 — AST y reintentos](img/CAP-03-ast-reintentos.png)

### CAP-04 — Grabaciones de IA simulada

Fuente: lectura de `bench/ia_simulada.json`; aparecen las seis claves `api_mvp.py::<MÉTODO> <ruta>`.

![CAP-04 — IA simulada](img/CAP-04-ia-simulada.png)

### CAP-05 — Banco FastAPI

Fuente: inspección de los seis decoradores, la única dependencia declarada y los tres bugs documentados.

![CAP-05 — Banco de seis endpoints](img/CAP-05-banco-api.png)

### CAP-06A — Ejecución real en Docker

Fuente: comando pytest con los tests EN-15 marcados `docker` y la prueba explícita de aislamiento. Resultado visible: 4 aprobadas y 1 excluida en 23.22 s.

![CAP-06A — Ejecución Docker](img/CAP-06a-ejecucion-docker.png)

### CAP-06B — Resultado 3 correctos y 3 bugs

Fuente: representación tabular de `resultado_banco_sandbox.json`; muestra tres `accept`, tres `bug_detectado`, cero errores técnicos, cero timeouts y cero tokens reales.

![CAP-06B — Resultado 3 y 3](img/CAP-06b-resultados-3-y-3.png)

## 20. Matriz de cumplimiento CA-01 a CA-06

| CA | Estado | Prueba y resultado | Evidencia |
|---|---|---|---|
| CA-01 | Cumplido | Se generan seis tests TestClient válidos con estado y JSON según contrato. | `test_genera_un_testclient_valido_por_cada_endpoint_con_cero_tokens`; `tests-generados/` |
| CA-02 | Cumplido | Overrides aplicados y restaurados tras éxito y fallo; verificadores posteriores aprobaron dentro del mismo contenedor. | `test_dependency_overrides_se_restauran_despues_del_test_en_sandbox`; resultado Docker |
| CA-03 | Cumplido | AST previo, feedback en reintento y máximo tres; suite rápida aprobada. | Tests de Generator, HU-11 y HU-14; `726 passed` |
| CA-04 | Cumplido | Seis claves exactas, salida determinista, 0 tokens y US$0.00. | `bench/ia_simulada.json`; JSON de resultado |
| CA-05 | Cumplido | Seis endpoints exactos, tres bugs deterministas, FastAPI como única dependencia. | `bench_api/`; prueba de grabaciones |
| CA-06 | Cumplido | Los seis tests proceden de `GeneratorAgent`; `ReviewerAgent` los ejecutó con el ejecutor Docker real y `network_mode="none"`. Se obtuvieron 3 `accept` y 3 `bug_detectado`, exactamente por las diferencias de `bugs.md`. | `test_banco_api_generado_detecta_exactamente_los_tres_bugs`; `test_rn02_una_prueba_que_abre_una_conexion_de_red_falla`; `resultado_banco_sandbox.json` |

**Resultado de la auditoría final:** EN-15 puede declararse terminada dentro de su alcance. El criterio CA-06 no exige que Planner o `ejecutar_corrida()` descubran y seleccionen los endpoints automáticamente; exige que las pruebas generadas se ejecuten en el sandbox sin red y detecten los tres bugs documentados, lo cual quedó verificado.

## 21. Riesgos y limitaciones

- Planner y `ejecutar_corrida()` todavía ignoran `modulo["endpoints"]`. Es una integración de otra historia o tarea y requiere coordinación; no es una carencia del criterio CA-06 de EN-15.
- La evidencia usa la IA simulada. No evalúa calidad, latencia ni costo de un modelo real.
- FastAPI 0.143.0 con Starlette 1.7.0 emitió una advertencia de deprecación sobre la integración actual de `httpx`; debe vigilarse una migración futura a httpx2 sin cambiar dependencias de forma improvisada.
- `network_mode="none"` bloquea la red del contenedor, pero no reemplaza otros controles del sandbox. Continúan vigentes límites de CPU, memoria, procesos, capacidades y sistema de archivos.
- Las evidencias viven bajo `docs/evidencias/`, ruta ignorada globalmente. Al preparar un futuro commit deberán añadirse explícitamente; en esta actividad no se alteró el índice.

## 22. Conclusiones

El Generator ya puede producir tests TestClient verificables y compatibles con los contratos de QAgent. Los overrides se restauraron en ejecuciones reales tanto después de éxito como de fallo. El banco confirmó que las pruebas generadas distinguen tres endpoints correctos y detectan exactamente tres defectos sembrados dentro del sandbox sin red, con cero tokens reales.

EN-15 queda terminada dentro de su alcance: generación, revisión y ejecución aislada del banco están verificadas. El flujo completo de aplicación aún necesita que Planner/corrida incorporen endpoints, pero ese cambio debe coordinarse como integración separada para no invadir otra historia.

## 23. Resumen breve para Notion

| Descripción / Historia de Usuario / Objetivo | Criterios de Aceptación / Detalles Clave |
|---|---|
| EN-15 amplía el Generator para crear pruebas pytest de endpoints FastAPI con TestClient, aserciones contractuales y sustitución segura de Depends. Incluye un banco local de seis endpoints y ejecución Docker sin red. | CA-01 a CA-06 cumplidos. La ruta analizador → contratos validados → Generator → Reviewer → Docker produjo 3 aceptados y 3 bugs detectados. La selección automática desde Planner/corrida pertenece a otra integración. |

**Avance para compartir:** EN-15 quedó terminada dentro de su alcance. Se implementó la generación TestClient y la IA simulada con seis grabaciones. La suite rápida terminó con 726 pruebas aprobadas y la prueba Docker final con 4 aprobadas. El banco produjo exactamente tres `accept` y tres `bug_detectado`, sin tokens reales, timeouts ni contenedores residuales. El recorrido automático de endpoints en Planner/corrida se gestionará como integración separada.
