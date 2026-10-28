# ADR-008: Orquestador determinista y Agente Explicador como etapa posterior al veredicto

- **Estado:** Propuesto (pendiente de aprobación del equipo)
- **Fecha:** 2026-10-25
- **Ítem:** SPK-03 — Evaluación de la arquitectura del orquestador y el Agente Explicador
- **Responsable de la investigación:** Sanchez Vargas, Adrián Olaf
- **Relacionado:** ADR-001 (modelos y costos), ADR-007 (adaptadores por lenguaje, EN-17), ADR-009 (parser por lenguaje, SPK-04), ADR-010 (arquitectura del Sprint 2), EN-04 (orquestador), HU-14, HU-16, HU-21, EP-10 (Agente Explicador)

> **Sobre las cifras.** Lo marcado **[MEDIDO]** se obtuvo con la IA simulada y ejecuciones de pytest grabadas, sin Docker, sin red y con 0 tokens reales. Lo marcado **[ESTIMADO]** es un cálculo teórico. Las pruebas con un LLM real de la sección 4.4 son **observaciones cualitativas**: no dejaron cifras registradas, así que este ADR no afirma ningún costo, latencia ni consumo de tokens medido con un modelo real.

---

## 1. Contexto

El orquestador de QAgent es una máquina de estados determinista: recorre el plan, valida cada contrato, aplica el tope de 3 intentos, corta reintentos por hash repetido, controla el presupuesto de tokens y atiende la cancelación. Los agentes (Planner, Generator y Reviewer) no se llaman entre sí.

El Sprint 2 agrega un Agente Explicador que traduzca los hallazgos técnicos a un lenguaje comprensible. También se planteó convertir el orquestador en un agente LLM que dirija la corrida y explique. Hay que decidir dónde vive la coordinación y dónde entra el Explicador sin duplicar al Reviewer ni alterar los resultados de las pruebas.

## 2. Pregunta

¿Conviene mantener el orquestador determinista, reemplazarlo por un LLM o combinar ambos? ¿Dónde se integra el Explicador para que aporte valor sin comprometer la reproducibilidad, la seguridad, los reintentos ni el presupuesto?

## 3. Opciones evaluadas

| Opción | Cómo funciona |
|---|---|
| **A. Orquestador determinista + Explicador independiente** | La máquina de estados no cambia; el Explicador es una etapa nueva que corre al final, sobre los veredictos ya cerrados. |
| **B. Orquestador basado en LLM** | Un LLM decide en cada paso qué agente llamar (bucle de *tool use*) y redacta el reporte. |
| **C. Híbrida** | El orquestador sigue siendo determinista, pero consulta a un LLM en decisiones ambiguas. |

## 4. Evidencia

### 4.1 Flujo actual [MEDIDO]

Banco `bench/banco_mvp.py` (6 funciones, 3 con bug sembrado), IA simulada y ejecuciones grabadas (`tests/orchestrator/ejecutor_grabado.py`):

| Dato | Valor |
|---|---|
| Traza | `planificar → (generar → ejecutar_revisar) × 6 → fin`: 14 transiciones |
| Decisiones | 3 `bug_detectado` y 3 `accept`, todas en el intento 1 |
| Llamadas al LLM | Planner 1, Generator 6, Reviewer 0 (las reglas resolvieron todo sin el LLM) |
| Tamaño de los prompts | Planner 4 537 caracteres; Generator 8 867 en total (≈ 1 478 por llamada) |
| Tiempo de coordinación, sin LLM ni Docker | 0,058 – 0,069 s por corrida (5 repeticiones) |
| Reproducibilidad | 5 de 5 corridas con la misma traza y los mismos resultados (decisión, intentos, laundering y código del test) |

Los cinco escenarios evaluados (ejecución normal, fallo recuperable, reintento, cancelación y límite de tokens) ya tienen pruebas en el repositorio: `tests/orchestrator/test_orquestador.py`, `test_hu14_dejar_de_insistir.py`, `test_limite_tokens.py`, `test_tiempo_agotado.py`, `test_fallo_objetivo_planner.py`, `test_en17_banco_grabado.py` y `tests/agents/test_reviewer.py`. En la fecha del spike pasaron 108 pruebas **[MEDIDO]**.

### 4.2 Matriz comparativa

Escala: 1 = mejor, 3 = peor.

| Criterio | A | B | C |
|---|:---:|:---:|:---:|
| Complejidad de integración | 1 | 3 | 2 |
| Reproducibilidad | 1 | 3 | 2 |
| Tope de 3 intentos y corte por hash | 1 | 3 | 1 |
| Límite de presupuesto | 1 | 3 | 2 |
| Tolerancia a errores | 1 | 3 | 2 |
| Seguridad (superficie de *prompt injection*) | 1 | 3 | 2 |
| Mantenimiento | 1 | 3 | 2 |

| Costo adicional por módulo del banco | A | B | C |
|---|---|---|---|
| Llamadas al LLM | 0 a 3 [ESTIMADO] | 7 a 19 [ESTIMADO] | ≈ 0 en el banco [ESTIMADO] |
| Tokens | ≈ 2 700 de entrada y 750 de salida [ESTIMADO] | ≈ 8 400–22 800 de entrada y 700–1 900 de salida [ESTIMADO] | ≈ 0 en el banco [ESTIMADO] |
| Costo | ≈ US$ 0,0006–0,0018 [ESTIMADO] | ≈ US$ 0,004–0,012 [ESTIMADO] | ≈ US$ 0 [ESTIMADO] |

Los tokens se estimaron como caracteres / 4 sobre los tamaños de prompt **medidos**, con los precios de `src/qagent/config/config.toml` y sin caché. En las tres opciones el costo es pequeño frente al tope de US$ 1,00 por corrida: **la decisión la determinan la reproducibilidad, la seguridad y la tolerancia a errores, no el costo.**

### 4.3 Hallazgos del análisis

- **B no tiene nada que decidir.** Todas las decisiones de flujo ya tienen regla: `decidir_corte`, `validar_transicion`, el tope de 3 y el presupuesto. En B esas reglas tendrían que seguir como guardas por encima del LLM, así que el LLM solo agrega costo, latencia, resultados no repetibles y superficie de ataque, porque el código del usuario y la salida de pytest entrarían al contexto que decide el flujo.
- **C ya existe donde tiene sentido.** `ReviewerAgent._clasificar_con_llm` consulta al LLM solo cuando fallan todas las reglas, responde un enum cerrado (`error_test` o `bug_codigo`) y, si responde otra cosa, la regla de respaldo deja el objetivo en `stalled`. No se encontró ningún punto del orquestador sin una regla clara.
- **El Explicador sí cubre un hueco.** El `feedback` del Reviewer está escrito para el Generator; `_explicacion()` (`storage/informe_pdf.py`) lo muestra tal cual, y `_salud_proyecto()` (`storage/exportar_informe.py`) usa el mismo texto de plantilla para cualquier bug. Nada explica, para una función concreta y en palabras de quien no programa, qué prometía y qué hizo, ni por qué quedó estancada. Parte de ese valor se logra **sin IA**, con plantillas que usen el esperado y el obtenido de `ejecucion.casos`.

### 4.4 Pruebas con un LLM real (cualitativas)

Después del análisis se probaron dos prototipos con claves de acceso gratuito:

| Prototipo | Qué se observó |
|---|---|
| **Orquestador con LLM** (opción B) | Consumió más tokens que el orquestador determinista y no mejoró de forma apreciable los resultados de la ejecución. |
| **«Redactor»** (primer prototipo del Explicador) | Resume los errores en lenguaje simple, pero solo a partir del **último** error del objetivo; no recorre los intentos anteriores. |

Conclusiones del equipo de investigación:

- Se confirma mantener el orquestador determinista.
- El Explicador **sí sirve a QAgent**, sobre todo a usuarios con poca experiencia en desarrollo (por ejemplo, quienes programan con asistentes de IA). Para usuarios técnicos, como ingenieros de software o de sistemas, desarrolladores, programadores o docentes que leen código, la traza técnica actual ya es suficiente y la explicación aporta menos.

Estas pruebas no dejaron cifras registradas (tokens, costo ni latencia); quedan como observaciones y no reemplazan la medición del paso 5 de la decisión.

## 5. Decisión

1. **Se mantiene el orquestador determinista** sin cambios en la máquina de estados.
2. **Se descarta el orquestador basado en LLM** (opción B).
3. **No se agregan puntos híbridos al orquestador** (opción C). El único punto híbrido autorizado sigue siendo `_clasificar_con_llm`, dentro del Reviewer.
4. **Se incorpora el Explicador como etapa posterior al veredicto** (opción A), en dos pasos:
   - **Paso 1, 0 tokens:** plantillas deterministas con el esperado, el obtenido y el motivo de estancamiento. Siempre disponible.
   - **Paso 2, opcional:** un LLM con su propio contrato validado con JSON Schema, que usa el paso 1 como respaldo. Debe leer **toda la traza de intentos** del objetivo, no solo el último error (lo que se observó en el prototipo «Redactor»).
5. **Antes de activar el paso 2 por defecto** se mide con un LLM real en el banco: tokens, costo, latencia y calidad de las explicaciones, revisada por el equipo.
6. **El Explicador se puede desactivar** y está pensado ante todo para usuarios no técnicos. Está desactivado en el perfil Humo; la configuración por defecto para los demás perfiles se decide con la medición del paso 5.

### 5.1 Punto de integración

- En `src/qagent/orchestrator/corrida.py`, **después de escribir `results.json`** (`escribir_corrida`) y antes de cerrar `run.json`. No va dentro del `Orquestador`: no agrega estados a la máquina ni toca `ResultadoObjetivo`.
- Los veredictos se guardan primero: si el Explicador falla, se cuelga o se cancela, los resultados ya están a salvo.
- Lo invoca el código de la corrida, no otro agente.
- Se omite si la corrida se canceló o si se alcanzó el límite de tokens o el tope en USD. Tiene su propio tiempo máximo.
- Registra sus tokens como agente `explicador` en el mismo `TokenTracker` y tiene su sección `[agentes.explicador]` en `config.toml` (ADR-001).

### 5.2 Entradas y salidas

**Entradas (solo lectura), por cada objetivo cuya decisión no es `accept`:**

- objetivo, tipo y módulo;
- decisión, motivos, intentos y `laundering_detectado`;
- casos y docstring del contrato del Planner;
- `tipo_fallo`, el `feedback` recortado de cada intento y el esperado y el obtenido del primer caso fallido;
- cobertura.

Todo pasa por `sanitizar_secretos` antes de enviarse. No recibe claves, rutas absolutas, el proyecto completo ni la posibilidad de ejecutar nada.

**Salida:** un contrato nuevo con `version`, `objetivo`, `decision`, `resumen`, `que_se_esperaba`, `que_paso`, `que_hacer`, `origen` (`ia` o `plantilla`) y `modelo`.

- `decision` es un eco: si no coincide con `results.json`, la explicación se descarta.
- Se guarda en `.qagent/runs/<run_id>/explicaciones.json`, validado contra `explicaciones.schema.json`, nunca dentro de `results.json`.
- Los informes lo leen si existe y es válido, y muestran «Explicación generada por IA» cuando corresponde.

### 5.3 Restricciones de responsabilidad

| El Explicador puede | El Explicador no puede |
|---|---|
| Reformular en lenguaje simple lo que ya decidió el Reviewer | Cambiar, sugerir cambiar o reinterpretar una decisión, un intento, la cobertura o `laundering_detectado` |
| Relacionar lo que promete el docstring con lo observado | Proponer relajar una aserción o cambiar el valor esperado (la explicación se descarta) |
| Resumir la traza de intentos de un objetivo estancado | Clasificar fallos: eso es del Reviewer |
| Fallar sin consecuencias para la corrida | Ejecutar código, pedir otro intento o llamar a otro agente |

## 6. Consecuencias

### Positivas

- Las métricas siguen siendo reproducibles y las reglas de seguridad no dependen de un LLM.
- El Explicador se integra con un paso al final de la corrida, un contrato y una sección de configuración; la máquina de estados no se toca.
- Si el Explicador falla o se desactiva, los informes siguen como hoy.

### Pendientes

- **Nombre y forma del contrato (Resuelto):** se acordó mantener el nombre `explanation.v1` y ajustar su contrato directamente en lugar de crear `explanation.v2`, dado que el borrador preliminar de EN-18 no tenía ningún consumidor fuera de sus pruebas unitarias (crear una v2 habría dejado código huérfano y deuda técnica innecesaria). El contrato adopta la forma definitiva alineada con la sección 5.2: `version`, `objetivo`, `decision` (eco estricto de `results.json`), `resumen`, `que_se_esperaba`, `que_paso`, `que_hacer`, `origen` (`plantilla` o `ia`) y `modelo` (obligatorio si `origen` es `ia`). Los campos `hallazgo_id` y `evidencia_ids` se eliminan porque `results.json` no los genera y el nombre del objetivo ya identifica unívocamente el resultado. La corrida persiste las explicaciones en `.qagent/runs/<run_id>/explicaciones.json` validado con su propio schema (`explicaciones.schema.json`).
- **Verificación de parches:** se mantiene fuera del alcance del Explicador hasta que se formule y apruebe un ADR específico de parches; el contrato `explanation.v1` no admite `verificacion.estado = 'verificada'`.
- **Sin medir:** la frecuencia real de `_clasificar_con_llm` con un modelo real, el consumo de tokens de los prototipos y la calidad de las explicaciones. Se miden en el paso 5 de la decisión.
- **Reproducibilidad de las cifras:** el script y los datos de medición del spike no están en el repositorio. Para repetir las cifras [MEDIDO] desde el código hay que versionarlos en `bench/`.
