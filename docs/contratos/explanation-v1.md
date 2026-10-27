# Contrato `explanation.v1`

## Objetivo

`explanation.v1` representa una explicación de solo lectura sobre un hallazgo ya registrado por QAgent. Prepara la salida del futuro Agente Explicador, pero no implementa el agente, no llama a un LLM y no altera el orquestador.

La explicación interpreta evidencia existente. Reviewer conserva en exclusiva el veredicto, la clasificación del fallo, los reintentos y el guardrail contra Assertion Laundering.

## Estructura

| Área | Campos principales |
|---|---|
| Identificación | `version`, `explicacion_id`, `hallazgo_id`. |
| Resultado de origen | `referencia_resultado.run_id`, `objetivo` y `resultado_id` opcional. |
| Ubicación | Archivo relativo, objetivo y rango de líneas opcional. |
| Hallazgo | Tipo, descripción e ids de evidencias. |
| Explicación | Resumen, impacto y limitaciones opcionales. |
| Recomendación | Acción sugerida, justificación e ids de evidencias. |
| Verificación | Estado `propuesta`, `pendiente` o `verificada`; la última exige una ejecución independiente. |
| Procedencia de la redacción | `origen` (`plantilla` o `ia`) y `modelo` obligatorio para `ia`. |

El schema usa `additionalProperties: false` en todos los objetos sensibles. Por ello no admite campos como `decision`, `veredicto`, `codigo_prueba` o `parche` que intenten modificar responsabilidades de Reviewer o el contenido de una prueba.

## Evidencia y contexto confiable

JSON Schema solo puede comprobar que un id tenga la forma correcta. `contracts.validar_explicacion()` recibe tres registros deterministas:

- `hallazgos_confiables`: run, objetivo, tipo, ubicación e ids de evidencia del hallazgo original.
- `evidencias_confiables`: evidencias realmente guardadas por QAgent.
- `verificaciones_confiables`: ejecuciones independientes registradas por el sandbox.

La validación rechaza referencias inexistentes, evidencia perteneciente a otro hallazgo, cambios del tipo original y ubicaciones que contradigan el registro.

## Estados de verificación

| Estado | Significado |
|---|---|
| `propuesta` | Acción sugerida; no se afirma que resuelva el hallazgo. |
| `pendiente` | La acción espera una verificación independiente. |
| `verificada` | Una ejecución confiable del sandbox terminó en `estado_sandbox == "ok"` y `decision == "accept"` para el mismo objetivo. |

No existe un booleano libre `verified`. Para `verificada` se requieren `ejecucion_id` y `run_id`, y ambos se contrastan con el registro recibido. Una entrada cuyo origen sea `llm` se rechaza como prueba aunque contenga `ok` y `accept`.

## Ejemplo válido no verificado

```json
{
  "version": "1",
  "explicacion_id": "exp-run-001-descuento",
  "hallazgo_id": "hallazgo-descuento-001",
  "referencia_resultado": {
    "run_id": "run-001",
    "objetivo": "calcularDescuento"
  },
  "hallazgo": {
    "tipo": "bug_codigo",
    "descripcion": "El resultado no coincide con el contrato.",
    "evidencia_ids": ["evidencia-assert-001"]
  },
  "explicacion": {
    "resumen": "La función devolvió 75 cuando se esperaban 80.",
    "impacto": "El precio final puede ser incorrecto."
  },
  "recomendacion": {
    "accion": "Revisar la regla de porcentaje.",
    "justificacion": "La aserción conserva el oráculo documentado.",
    "evidencia_ids": ["evidencia-assert-001"]
  },
  "verificacion": {"estado": "propuesta"},
  "origen": "plantilla",
  "modelo": null
}
```

## Casos rechazados

- Falta `hallazgo_id` o cualquier campo obligatorio.
- El hallazgo o la evidencia no existen en el contexto confiable.
- La evidencia existe, pero pertenece a otro hallazgo.
- Se declara `verificada` sin una ejecución registrada.
- La supuesta verificación procede de un LLM o no terminó aceptada en el sandbox.
- Se agrega `decision`, `veredicto`, código de prueba o parche.
- La referencia apunta a otra corrida u objetivo.

Los contextos y escenarios reproducibles están en `tests/fixtures/en18/explicaciones.json`.

## Versionado e integración futura

- Schema: `src/qagent/contracts/explanation.v1.schema.json`.
- Ejemplo distribuido: `src/qagent/contracts/ejemplos/explanation.v1.json`.
- Familia versionada: `contracts.FAMILIA_EXPLANATION`.
- Validación contextual: `contracts.validar_explicacion()`.

Según ADR-008, un futuro Explicador se ejecutará después de guardar `results.json` y escribirá un archivo separado. EN-18 solo entrega el contrato y su validación; no crea `ExplicadorAgent`, no persiste `explicaciones.json`, no añade configuración y no realiza llamadas LLM.

## Limitaciones

- La autenticidad de evidencia depende de los registros confiables que entregue el futuro punto de integración.
- La verificación de una propuesta depende de una ejecución independiente que otra issue conectará al sandbox.
- No se propone ni aplica un parche; esa capacidad requiere una decisión arquitectónica separada.
