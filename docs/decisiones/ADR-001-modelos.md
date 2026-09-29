# ADR-001: Modelos por agente

- **Estado:** Aceptado
- **Fecha:** 2026-09-29
- **Ítem:** SPK-01 — Elegir modelos y precios reales
- **Decidido por:** equipo completo (Castillo, Oncoy, Rodríguez, Sanchez)
- **Relacionado:** EN-05 (registro de tokens y costo), EN-06 (configuración), EN-11 (IA simulada), HU-08 (costo antes de iniciar), HU-24 (caché de specs), EV-01, EV-04

## Contexto

Cada agente tiene una tarea distinta:

- **Planner:** lee el módulo completo (AST, firmas, docstrings) y diseña los casos de prueba. Necesita buen razonamiento y contexto amplio.
- **Generator:** escribe el test pytest de **una** función a partir del contrato. La tarea es acotada.
- **Reviewer:** revisa si las aserciones son legítimas (Assertion Laundering) con el resultado del sandbox. Un guardrail determinista hace el trabajo principal.

El presupuesto total de API del semestre es **US$ 25**. El desarrollo diario usa la IA simulada (EN-11), que no gasta tokens.

## Opciones comparadas

Fuente: Artificial Analysis (índice de inteligencia, velocidad de salida y costo promedio por tarea del índice), consultado en septiembre de 2026.

| Modelo | Inteligencia | Velocidad (tok/s) | Costo por tarea (US$) |
|---|---|---|---|
| Claude Opus 5.5 (max) | 58 | 94 | 5.98 |
| Claude Fable 5.1 (max) | 53 | 67 | 7.63 |
| GPT-6 Astra (max) | 53 | 60 | 3.26 |
| Muse Spark 1.3 (max) | 48 | 197 | 1.60 |
| MiMo-V2.6-Pro | 46 | 42 | 0.13 |
| GLM-5.3 (max) | 45 | 87 | 2.01 |
| Gemini 3.8 Flash (high) | 41 | 239 | 1.24 |
| DeepSeek V4.1 Flash (max) | 39 | 217 | 0.27 |
| GPT-6 Luna (max) | 37 | 152 | 0.07 |

> El "costo por tarea" corresponde a las tareas del benchmark, no a nuestros prompts. Sirve para comparar modelos entre sí, no para estimar el gasto real (ver "Estimación de gasto").

## Decisión

| Agente | Modelo | ID en la API directa | ID en OpenRouter | Entrada US$/M | Salida US$/M | Caché (lectura) US$/M | Contexto |
|---|---|---|---|---|---|---|---|
| Planner | Claude Opus 5.5 (max) | `claude-opus-5-5` | `anthropic/claude-opus-5.5` | 4.00 | 20.00 | 0.20 | 1 000 000 |
| Generator | MiMo-V2.6-Pro | *por verificar en la consola de Xiaomi* | `xiaomi/mimo-v2.6-pro` | 0.435 | 0.87 | 0.0036 | 1 050 000 |
| Reviewer | GPT-6 Luna (max) | `gpt-6-luna` *(confirmar)* | `openai/gpt-6-luna` | 0.10 | 0.50 | 0.01 | 1 050 000 |

Notas de precios:

- **Claude Opus 5.5:** sin recargo por contexto largo. Batch API con 50 % de descuento (US$ 2 / US$ 10). Escribir en caché cuesta 1.25× la entrada si dura 5 minutos.
- **GPT-6 Luna:** si la entrada supera **272K tokens**, la **petición completa** pasa a US$ 0.20 / US$ 0.75. Nuestras llamadas al Reviewer son de una sola función, así que no deberían acercarse a ese límite. Batch/Flex a mitad de precio.
- **MiMo-V2.6-Pro:** no documenta tramos por longitud de contexto.
- Los tokens de razonamiento del modo "max" se cobran como **salida**.

### Fase de arranque: MiMo también como Planner

Las **primeras corridas reales** (inicio de EV-01) usan **MiMo-V2.6-Pro también en el Planner**, antes de pasar a Claude Opus 5.5. Objetivos:

1. **Medir el rendimiento real a bajo costo.** Obtener los tokens reales por llamada, el Pass Rate, la cobertura y las iteraciones sobre el banco propio (EN-12) con el modelo más barato de la configuración. Una corrida del banco cuesta unos US$ 0.09 con MiMo como Planner, frente a US$ 0.34 con Opus.
2. **Probar el flujo completo** (contratos, sandbox, registro de tokens) con dinero real sin arriesgar el presupuesto si hay errores de integración.
3. **Tener una línea base.** Al pasar el Planner a Opus 5.5 se compara con las mismas métricas, y así se sabe cuánto mejora el modelo caro y si justifica su costo.

Estas corridas sirven además como la corrida A de EV-04 (los 3 agentes con un modelo económico), siempre que el Reviewer también use MiMo en esa corrida.

**Criterio para pasar a Opus 5.5:** el flujo completo termina sin intervención manual sobre el banco propio y los tokens reales por llamada ya están registrados en `log.json`. Si con MiMo como Planner se alcanzan las metas de la carta (Pass Rate 70–80 %, cobertura de líneas ≥ 60 %, iteraciones promedio < 2), el equipo evalúa mantenerlo y registra el cambio en un nuevo ADR.

## Justificación

- **Planner → Claude Opus 5.5:** tiene el índice de inteligencia más alto (58). Es el único agente que ve el módulo completo y la calidad de sus casos determina la de todo lo demás. Corre **una vez por módulo**, no por función, y su resultado se reutiliza con la caché de specs (HU-24).
- **Generator → MiMo-V2.6-Pro:** índice 46, el más alto entre los modelos baratos, con un costo por tarea de US$ 0.13 (46 veces menos que Opus). La tarea está acotada a una función y a un contrato cerrado.
- **Reviewer → GPT-6 Luna:** el menor costo por tarea (US$ 0.07). El guardrail determinista sobre el AST de las aserciones hace el trabajo principal y el LLM solo resuelve los casos dudosos.

## Estimación de gasto

Fórmula por llamada: `costo = tokens_entrada × precio_entrada + tokens_salida × precio_salida`.

**Supuestos (estimados; se reemplazan con los valores reales de la fase de arranque):**

| Agente | Entrada por llamada | Salida por llamada (incluye razonamiento) | Costo por llamada |
|---|---|---|---|
| Planner con Opus 5.5 | 6 000 | 12 000 | US$ 0.264 |
| Planner con MiMo (arranque) | 6 000 | 12 000 | US$ 0.013 |
| Generator | 2 500 | 3 000 | US$ 0.0037 |
| Reviewer | 3 500 | 4 000 | US$ 0.0024 |

**Por corrida:**

| Escenario | Planner | Generator | Reviewer | Total |
|---|---|---|---|---|
| Banco propio, Planner con MiMo (arranque) | 0.01 | 0.04 | 0.03 | **US$ 0.09** |
| Banco propio (1 módulo, 8 funciones, 1.5 intentos promedio) | 0.26 | 0.04 | 0.03 | **US$ 0.34** |
| Banco propio, peor caso (3 intentos siempre) | 0.26 | 0.09 | 0.06 | **US$ 0.41** |
| Repositorio externo (20 módulos, 100 funciones, 1.5 intentos) | 5.28 | 0.55 | 0.35 | **US$ 6.19** |

**Con Opus 5.5, el Planner representa ~80 % del gasto.** Un repositorio de 20 módulos cuesta unas 18 veces más que el banco propio.

**Plan de gasto del semestre (US$ 25):**

| Uso | Corridas | Estimado |
|---|---|---|
| Arranque: banco propio con MiMo como Planner | 5 | US$ 0.45 |
| EV-01 banco propio con Opus 5.5 (MVP) | 3 | US$ 1.02 |
| EV-04 control multiagente vs. multimodelo (A con MiMo, B normal) | 2 | US$ 0.43 |
| EV-02 repositorio externo | 1 | US$ 6.20 |
| EV-03 corrida final, 2 repositorios | 2 | US$ 12.40 |
| **Total** | | **US$ 20.50** |
| Margen | | US$ 4.50 |

El margen sigue siendo ajustado. Por eso:

1. **Elegir repositorios externos pequeños** (≤ 10 módulos) para EV-02 y EV-03. Eso baja cada corrida a unos US$ 3.
2. **Probar el Planner con menos esfuerzo de razonamiento** en EV-01. Si el razonamiento baja de 12 000 a 4 000 tokens de salida, el costo por módulo con Opus pasa de US$ 0.26 a US$ 0.10.
3. **Usar caché de prompt** en las instrucciones fijas de cada agente (lectura a 5 % del precio de entrada).
4. **Tope por corrida en `config.toml`** (HU-08 lo muestra antes de iniciar): US$ 1.00 para el banco y US$ 7.00 para repositorios externos.

## Consecuencias y riesgos

- **El Planner concentra el gasto.** Mitigación: fase de arranque con MiMo, tope por corrida, caché de specs (HU-24) y medición real antes de correr repositorios externos.
- **MiMo como Planner puede diseñar casos más pobres.** Es esperable y es justamente lo que mide la fase de arranque. Sus resultados no se reportan como resultado final del sistema, salvo en EV-04.
- **El Reviewer tiene el índice más bajo (37).** Mitigación: el guardrail determinista decide primero y el golden set (EN-13) mide si Luna clasifica bien. Si falla, se reemplaza por DeepSeek V4.1 Flash (US$ 0.27 por tarea, índice 39) o MiMo-V2.6-Pro.
- **Tres proveedores implican tres claves en `.env` y tres formatos de `usage` en EN-05.** Alternativa: los tres modelos están disponibles en **OpenRouter** con los mismos precios de lista. Eso da una sola clave, un solo cliente compatible con OpenAI y un solo formato de `usage`. Antes de decidir, revisar la comisión de OpenRouter por compra de créditos.
- **Los precios y los ID pueden cambiar.** Se leen de `config.toml` y los modelos usados quedan registrados en cada `log.json` (EN-05). Este ADR se actualiza si cambian.

## Fuentes

- [Anthropic — Pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- [OpenRouter — Claude Opus 5.5](https://openrouter.ai/anthropic/claude-opus-5.5)
- [OpenRouter — MiMo-V2.6-Pro](https://openrouter.ai/xiaomi/mimo-v2.6-pro)
- [eesel AI — Xiaomi MiMo V2.6 pricing](https://www.eesel.ai/blog/xiaomi-mimo-v2-6-pricing)
- [OpenRouter — GPT-6 Luna](https://openrouter.ai/openai/gpt-6-luna)
- [LinkModel — GPT-6 Luna API pricing (recargo sobre 272K)](https://www.linkmodel.ai/blog/gpt-6-luna-api-pricing)
- Artificial Analysis — Intelligence Index, velocidad y costo por tarea (captura del equipo, septiembre de 2026)