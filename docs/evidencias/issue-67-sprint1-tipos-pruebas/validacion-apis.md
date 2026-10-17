# Validación de APIs de IA — issue #67, Fase 3

Fecha de verificación: 2026-10-16.

## 1. Objetivo

Validar, sin solicitudes reales, que QAgent puede configurar Planner con Gemini,
Generator con OpenRouter y Reviewer con Groq; revisar el manejo de fallos y dejar un
procedimiento seguro para una validación real posterior.

## 2. Arquitectura LLM actual

`config.toml` define proveedor, modelo y precios por rol. Un
`config.local.toml` en `~/.qagent/` puede reemplazar cada rol sin modificar la
configuración del equipo. Las claves se leen exclusivamente desde
`~/.qagent/.env`.

`llm/fabrica.py` crea un cliente por rol. `llm/proveedores.py` obtiene URL, modelos y
cabeceras del catálogo `llm/proveedores.toml`. Los tres proveedores de esta fase usan
la interfaz compatible con OpenAI de `ClienteLLMReal`; OpenRouter añade `X-Title:
QAgent`. No se necesita un SDK adicional.

El flujo verificado es: selección y estrategia → Planner → contrato JSON validado →
Generator → pytest → Reviewer/sandbox → registro. Regresión evita completamente la
creación de clientes LLM.

## 3. Proveedores disponibles

El catálogo contiene Anthropic, Xiaomi MiMo, OpenAI, OpenRouter, Gemini y Groq. Para
esta fase se verificaron estructuralmente:

| Rol | Proveedor | Modelo propuesto para la prueba controlada | Endpoint |
|---|---|---|---|
| Planner | Gemini | `gemini-3.8-flash` | API OpenAI-compatible de Gemini |
| Generator | OpenRouter | `google/gemma-4-31b-it:free` | Chat Completions de OpenRouter |
| Reviewer | Groq | `openai/gpt-oss-20b` | Chat Completions de Groq |

Esta distribución es una propuesta de configuración local, no un valor rígido del
código ni un cambio de los valores globales del equipo.

## 4. Configuración propuesta por rol

Ejemplo para `~/.qagent/config.local.toml`:

```toml
[agentes.planner]
proveedor = "gemini"
modelo = "gemini-3.8-flash"
precio_entrada_usd_m = 0
precio_salida_usd_m = 0

[agentes.generator]
proveedor = "openrouter"
modelo = "google/gemma-4-31b-it:free"
precio_entrada_usd_m = 0
precio_salida_usd_m = 0

[agentes.reviewer]
proveedor = "groq"
modelo = "openai/gpt-oss-20b"
precio_entrada_usd_m = 0
precio_salida_usd_m = 0
```

La pantalla Configuración debe ser el medio preferido: prueba la conexión antes de
guardar y escribe los precios del catálogo. El ejemplo no debe copiarse si la ficha
oficial dejó de indicar acceso gratuito.

## 5. Modelos y cuotas verificados

Fuentes oficiales consultadas el 2026-10-16:

- Gemini: [modelos](https://ai.google.dev/gemini-api/docs/models),
  [precios](https://ai.google.dev/gemini-api/docs/pricing) y
  [límites](https://ai.google.dev/gemini-api/docs/rate-limits).
- OpenRouter: [límites](https://openrouter.ai/docs/api_reference/limits),
  [precios](https://openrouter.ai/pricing) y
  [Gemma 4 31B gratis](https://openrouter.ai/google/gemma-4-31b-it%3Afree).
- Groq: [límites](https://console.groq.com/docs/rate-limits) y
  [modelos](https://console.groq.com/docs/models).

Hallazgos:

- Gemini documenta `gemini-3.8-flash` y precio gratuito de entrada/salida en Free
  Tier. Sus límites efectivos ya no son una cifra pública universal: dependen del
  modelo, proyecto, nivel y estado de cuenta, y deben consultarse en AI Studio. Las
  cuotas se aplican por proyecto, no por API key, y un exceso responde 429
  `RESOURCE_EXHAUSTED`. El nivel gratuito no exige activar facturación pagada; sí se
  requiere un proyecto elegible. Una tarjeta no fue verificada como requisito del
  nivel gratuito en la documentación revisada.
- OpenRouter confirma `google/gemma-4-31b-it:free` con precio cero. Los modelos
  gratuitos tienen 20 solicitudes por minuto y 50 por día; el límite diario sube a
  1.000 después de haber comprado al menos USD 10 en créditos. La necesidad de
  tarjeta para una cuenta exclusivamente gratuita no quedó confirmada en las páginas
  oficiales revisadas.
- Groq incluye `openai/gpt-oss-20b` en Free Plan con 30 RPM, 1.000 RPD, 8.000 TPM y
  200.000 TPD. Los límites se aplican a la organización y el primero alcanzado
  bloquea la solicitud; 429 indica exceso. Los valores exactos de la organización se
  consultan en su página Limits. La documentación revisada no confirma que una
  tarjeta sea necesaria para Free Plan.

Los modelos gratuitos y sus cuotas pueden cambiar. El catálogo debe volver a
contrastarse antes de las pruebas reales.

## 6. Variables de entorno

Variables propias verificadas:

- `GEMINI_API_KEY_PLANNER`
- `OPENROUTER_API_KEY_GENERATOR`
- `GROQ_API_KEY_REVIEWER`

Si falta la variable propia, QAgent admite como respaldo `GEMINI_API_KEY`,
`OPENROUTER_API_KEY` o `GROQ_API_KEY`. No existe cambio silencioso de proveedor: el
proveedor se obtiene de la configuración del rol y una clave ausente bloquea la
creación del cliente.

`QAGENT_FAKE_LLM=1` evita la lectura de claves y hace que los tres roles reciban
`FakeLLMClient` con el modelo configurado.

## 7. Pruebas simuladas

No se usaron claves ni conexiones externas. Se añadió una matriz que verifica el rol,
proveedor, modelo, endpoint y variable propia de los tres clientes mediante un
transporte local. También verifica que FakeLLMClient cubra los tres roles sin claves.

Resultados reales:

- Focalizadas de configuración, LLM, agentes, orquestador y estrategias: 369
  aprobadas, 1 excluida por marca.
- Suite rápida: 1.086 aprobadas, 19 excluidas por Docker/red.
- Ninguna solicitud real y cero consumo de cuotas.

Unitarias, límites y humo usan Planner, Generator y Reviewer simulados. Humo mantiene
un caso nominal máximo por objetivo. Regresión reutiliza aprobadas, no crea clientes y
registra cero llamadas LLM.

## 8. Manejo de errores

Cobertura simulada confirmada:

- 401: clave inválida, sin reintento.
- 403: acceso denegado por cuenta/proyecto/modelo, distinguido de 401.
- 404: modelo no disponible.
- 429 y 503: reintentos limitados, `Retry-After` respetado y espera acotada.
- 429 con cuota gratuita `limit: 0`: no reintenta porque el fallo no es transitorio.
- 402 de OpenRouter: crédito insuficiente.
- timeout, error de red, respuesta vacía y JSON inválido: fallo controlado.
- agotamiento: máximo configurado en el cliente; no hay bucle infinito.
- errores: clave redactada y tipo/código/detalle preservados.
- configuración fallida: no se escribe `config.local.toml` ni `.env`.

No existe fallback silencioso hacia otro proveedor o modelo.

## 9. Métricas disponibles

`TokenTracker` registra por llamada: rol, modelo, tokens de entrada y salida, costo
calculado, indicador simulado, función, intento y hora. Agrega total de tokens, costo,
solicitudes y totales por rol. `results.json` registra además proveedor, modelo y
precios configurados por rol.

El consumo real procede de `usage.prompt_tokens` y `usage.completion_tokens`. Si el
proveedor omite `usage`, actualmente ambos valores quedan en cero: significa dato no
disponible, no consumo real cero. FakeLLMClient devuelve cero tokens y se marca como
simulado. El costo es una estimación basada en la configuración, no una factura del
proveedor.

Datos no disponibles actualmente: latencia individual de la API, contador HTTP de
reintentos, llamadas fallidas y una bandera persistida que distinga `usage` ausente de
un consumo real de cero. Incorporarlos requiere ampliar el contrato de telemetría y
no fue necesario para validar esta fase.

## 10. Limitaciones

- No se verificó una cuenta real, elegibilidad regional ni necesidad efectiva de
  tarjeta.
- Los límites de Gemini deben leerse en AI Studio para el proyecto concreto.
- Los modelos gratuitos pueden desaparecer o quedar temporalmente sin capacidad.
- El pipeline normal no envía todavía un límite explícito de tokens de salida; solo
  la llamada de validación limita la salida a 16 tokens.
- Un precio cero del catálogo solo es válido mientras la ficha oficial conserve el
  modelo en el nivel gratuito.

## 11. Procedimiento pendiente para pruebas reales

No ejecutar sin autorización expresa.

1. Revalidar modelos y cuotas en las consolas oficiales el mismo día.
2. Configurar cada rol desde la pantalla, usando `config.local.toml` y `.env` del
   usuario. Nunca pegar claves en chat, commits, capturas o logs.
3. Usar un proyecto sintético local con una función pura documentada; no usar código
   privado ni datos personales.
4. Probar primero únicamente la conexión de cada rol. Son 3 solicitudes previstas,
   con salida limitada a 16 tokens por solicitud.
5. Registrar hora, rol, proveedor, modelo, resultado HTTP y los contadores mostrados
   por cada consola antes y después. Esa diferencia será consumo real; la estimación
   de QAgent se reportará aparte.
6. Cancelar ante 401, 403, 402, modelo no disponible, `limit: 0`, dos fallos de red
   consecutivos o cualquier indicio de facturación no autorizada.
7. Ante 429/503, no insistir manualmente: respetar `Retry-After` y comprobar la cuota
   en la consola.
8. No ejecutar todavía una corrida completa: QAgent no configura un máximo explícito
   de salida para las llamadas normales. Antes debe acordarse ese límite o autorizarse
   el riesgo. Una corrida mínima tendría 3 llamadas lógicas esperadas (un Planner, un
   Generator y un Reviewer); con tres intentos del orquestador puede llegar a 7, y
   cada llamada lógica transitoria admite hasta 3 reintentos HTTP adicionales.

## 12. Conclusiones

Los tres proveedores están soportados por la infraestructura existente y la
distribución solicitada funciona con configuración por rol. No se agregaron SDK ni
valores rígidos. Se corrigió la clasificación de 403 y la pérdida del tipo/código al
propagar errores de ejecución. La validación real permanece pendiente de autorización
y debe comenzar únicamente con las tres comprobaciones mínimas de conexión.
