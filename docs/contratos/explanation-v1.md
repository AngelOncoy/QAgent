# Contrato `explanation.v1` y archivo `explicaciones.json`

## Objetivo

`explanation.v1` representa una explicación de solo lectura sobre un objetivo cuyo veredicto no terminó en `accept` (`bug_detectado`, `stalled` o sin veredicto), conforme a lo decidido en el **ADR-008** (SPK-03) y la sección 6.5 de `docs/arquitectura.md`.

Prepara la salida del futuro Agente Explicador, pero no implementa el agente, no altera la máquina de estados del orquestador y no relaja aserciones. Reviewer conserva en exclusiva el veredicto, la clasificación del fallo, los reintentos y el guardrail contra Assertion Laundering.

## Estructura de `explanation.v1`

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `version` | string | Sí | Debe ser `"1"`. |
| `objetivo` | string | Sí | Nombre de la función o endpoint probado (ej. `"calcularDescuento"` o `"GET /items"`). |
| `decision` | string \| null | Sí | Eco estricto del veredicto de `results.json`: `"bug_detectado"`, `"stalled"`, `"sin_veredicto"`, `"requiere_corrida_nueva"` o `null`. Si no coincide con `results.json`, la explicación se descarta. No admite `"accept"`. |
| `resumen` | string | Sí | Resumen en lenguaje claro del resultado. |
| `que_se_esperaba` | string | Sí | Qué prometía la especificación o contrato documentado. |
| `que_paso` | string | Sí | Qué ocurrió realmente en la ejecución del sandbox. |
| `que_hacer` | string | Sí | Recomendación para el usuario. El validador semántico rechaza cualquier recomendación que proponga relajar una aserción o cambiar el valor esperado. |
| `origen` | string | Sí | `"plantilla"` (0 tokens) o `"ia"`. |
| `modelo` | string \| null | Condicional | Obligatorio y no vacío si `origen == "ia"`; `null` si `origen == "plantilla"`. |
| `modulo` | string | No | Módulo al que pertenece el objetivo. |
| `run_id` | string | No | Identificador de la corrida. |
| `explicacion_id` | string | No | Identificador de la explicación. |
| `ubicacion` | object | No | Archivo relativo seguro (`archivo`) y líneas opcionales (`linea_inicio`, `linea_fin`). |
| `verificacion` | object | No | Si está presente, su `estado` solo puede ser `"propuesta"` o `"pendiente"`. El estado `"verificada"` queda excluido hasta que se apruebe un ADR de parches. |

El schema usa `additionalProperties: false`. Por ello no admite campos como `codigo_prueba`, `parche` o `veredicto` que pretendan modificar las responsabilidades del Reviewer o el contenido de los tests.

## Persistencia: `.qagent/runs/<run_id>/explicaciones.json`

Las explicaciones de una corrida se guardan en `.qagent/runs/<run_id>/explicaciones.json`, **nunca dentro de `results.json`**.

El archivo se valida contra el schema `explicaciones.schema.json`, que admite:
1. Un objeto con metadata de corrida:
   ```json
   {
     "version": "1",
     "tipo": "explicaciones",
     "run_id": "20261025-143000-a1b2",
     "explicaciones": [ ... ]
   }
   ```
2. Una lista directa `[ ... ]` de explicaciones `explanation.v1`.

## Validación semántica

`contracts.validar_explicacion()` aplica las siguientes reglas de negocio deterministas:

1. **Eco de decisión:** si se proporciona `results_confiables` o `resultado_confiable`, la `decision` de la explicación debe coincidir exactamente con la registrada en `results.json`. Si el objetivo terminó en `accept`, se rechaza porque el Explicador solo actúa sobre objetivos no aceptados.
2. **Guardrail anti-relajación / anti-laundering:** se analiza el texto de `que_hacer` (y campos explicativos). Si propone relajar una aserción, debilitar asserts, eliminar aserciones o cambiar el valor esperado del oráculo, la explicación se rechaza.
3. **Restricción de parches:** no se admite `verificacion.estado == "verificada"`.
4. **Ubicación segura:** las rutas deben ser relativas y seguras (sin `..` ni rutas absolutas), y `linea_fin >= linea_inicio`.

`contracts.validar_explicaciones()` valida el archivo contenedor completo y cada una de sus explicaciones.

## Ejemplo válido

```json
{
  "version": "1",
  "objetivo": "calcularDescuento",
  "decision": "bug_detectado",
  "resumen": "La función devolvió 75 cuando el contrato esperaba 80.",
  "que_se_esperaba": "Que calcularDescuento(100, 20) devolviera 80 según la documentación.",
  "que_paso": "La función aplicó un descuento del 25% en lugar del 20% y devolvió 75.",
  "que_hacer": "Revisar la regla de cálculo de porcentaje en src/precios.ts para aplicar el porcentaje correcto.",
  "origen": "plantilla",
  "modelo": null
}
```

## Casos rechazados

- Falta cualquier campo obligatorio (`version`, `objetivo`, `decision`, `resumen`, `que_se_esperaba`, `que_paso`, `que_hacer`, `origen`).
- `origen == "ia"` sin especificar un `modelo` no vacío.
- `decision == "accept"` (prohibido tanto por schema como por validador semántico).
- La `decision` no coincide con la registrada en `results.json` para ese objetivo.
- La recomendación propone relajar una aserción o cambiar el valor esperado documentado.
- Se declara `verificacion.estado = "verificada"`.
- Se agregan campos ajenos (`parche`, `codigo_prueba`, `veredicto`, etc.).
- La ruta del archivo es absoluta o insegura.

## Versionado y archivos relacionados

- Schema individual: `src/qagent/contracts/explanation.v1.schema.json`.
- Schema de lista/archivo: `src/qagent/contracts/explicaciones.schema.json`.
- Ejemplo individual: `src/qagent/contracts/ejemplos/explanation.v1.json`.
- Ejemplo de archivo: `src/qagent/contracts/ejemplos/explicaciones.json`.
- Familia versionada: `contracts.FAMILIA_EXPLANATION`.
- Validadores: `contracts.validar_explicacion()` y `contracts.validar_explicaciones()`.
