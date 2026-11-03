# Medición del Agente Explicador (SPK #167)

- **Fecha:** 2026-10-30T16:17:19-05:00
- **Casos:** 6 hallazgos (assertion_laundering, bug_detectado, estancada, sin_veredicto), 3 repeticiones por modelo
- **Tiempo máximo por explicación:** 60 s
- **IA:** real

> [MEDIDO]: cifras de esta corrida con un LLM real, con los tokens que informó el proveedor. [ESTIMADO]: el proveedor no informó tokens y se calcularon como caracteres / 4. [SIMULADO]: IA simulada, solo comprueba que el script funciona.

## Por explicación

| Modelo | Tokens entrada | Tokens salida | Costo US$ | Latencia p50 / p95 (s) | Descartadas | Etiqueta |
|---|---:|---:|---:|---:|---:|---|
| plantilla | 0 | 0 | 0.000000 | 0.001 / 0.001 | 0.0 % | [MEDIDO] |
| deepseek-flash | 1046 | 863 | 0.001349 | 5.717 / 8.037 | 5.6 % (relaja_asercion: 1) | [MEDIDO] |
| deepseek-v4-pro | 1099 | 1144 | 0.005980 | 9.005 / 14.199 | 11.1 % (relaja_asercion: 2) | [MEDIDO] |

## Por corrida (todos los hallazgos de los casos)

| Modelo | Tokens | Costo US$ | Latencia (s) | % del costo de la corrida | Respeta los topes |
|---|---:|---:|---:|---:|---|
| deepseek-flash | 11454 | 0.008096 | 36.094 | sin --log-corrida | sí |
| deepseek-v4-pro | 13458 | 0.035882 | 59.288 | sin --log-corrida | sí |

## Comprobaciones

- Entrada sin claves ni rutas absolutas: sí, en todos los hallazgos (si no, el script se detiene antes de enviar).
- deepseek-flash, `max_tokens_por_corrida` mínimo: 0 llamadas al LLM, 6 de 6 con plantilla (respeta el tope).
- deepseek-flash, `tope_por_corrida_usd` mínimo: 0 llamadas al LLM, 6 de 6 con plantilla (respeta el tope).
- deepseek-v4-pro, `max_tokens_por_corrida` mínimo: 0 llamadas al LLM, 6 de 6 con plantilla (respeta el tope).
- deepseek-v4-pro, `tope_por_corrida_usd` mínimo: 0 llamadas al LLM, 6 de 6 con plantilla (respeta el tope).

## Respuestas descartadas

Lo que respondió el modelo cuando se descartó por su contenido. En la corrida real se habría mostrado la plantilla.

### deepseek-flash, repetición 1, `total_con_impuesto`: relaja_asercion

Motivo: la respuesta no cumple el contrato: que_hacer: no se permite proponer relajar una aserción ni cambiar el valor esperado

```json
{"decision":"stalled","resumen":"La prueba se quedó estancada tras 3 intentos. No hay veredicto final y eso no prueba que la función tenga un error.","que_se_esperaba":"Que la función total_con_impuesto sumara el precio de los productos del carrito más el impuesto general. Para dos productos de 10.0 con impuesto general de 18 %, el total esperado era 23.6.","que_paso":"En el primer intento faltaba un dato obligatorio del carrito: las tasas. En el segundo y tercer intento se pasaron las tasas vacías, y el carrito respondió que necesita las tasas de su región. La prueba se detuvo al preparar el carrito y no llegó a comprobar el total. El mismo error se repitió.","que_hacer":"Revisar cómo debe prepararse el carrito para que acepte la información de tasas que exige. Volver a ejecutar la misma prueba con el total esperado de 23.6. No cambiar el valor esperado ni quitar la comprobación. Al estar estancada, no dar por hecho que el código está mal."}
```

### deepseek-v4-pro, repetición 1, `clasificar_edad`: relaja_asercion

Motivo: la respuesta no cumple el contrato: que_hacer: no se permite proponer relajar una aserción ni cambiar el valor esperado

```json
{
  "decision": "bug_detectado",
  "resumen": "La función clasificar_edad devolvió 'menor' para una edad de 18 años, cuando la documentación indica que 18 ya debe ser 'adulto'. Por eso la prueba automática terminó mal.",
  "que_se_esperaba": "Que al recibir 18 años la función devolviera 'adulto', igual que para 64. 'menor' solo debe usarse de 0 a 17 y 'adulto mayor' desde 65.",
  "que_paso": "La prueba con 17 pasó, con 64 pasó, con 65 pasó y con -1 pasó. Solo falló la de 18: la función respondió 'menor' en lugar de 'adulto'.",
  "que_hacer": "Revisar la lógica de clasificar_edad, especialmente el límite de 18 años, para que devuelva 'adulto' cuando la edad sea 18. No cambiar el valor esperado: 18 es adulto según la documentación."
}
```

### deepseek-v4-pro, repetición 1, `total_con_impuesto`: relaja_asercion

Motivo: la respuesta no cumple el contrato: que_hacer: no se permite proponer relajar una aserción ni cambiar el valor esperado

```json
{
  "decision": "stalled",
  "resumen": "La comprobación no llegó a ejecutar la función total_con_impuesto porque falló al preparar el carrito. El error se repitió, así que no se pudo verificar el total. Esto no significa que la función tenga un error.",
  "que_se_esperaba": "Crear un carrito con dos productos de 10.0 y una tasa general de 0.18, y que la función devuelva 23.6.",
  "que_paso": "En el primer intento faltó un dato obligatorio para crear el carrito. En los intentos siguientes se usó una tasa vacía, pero el carrito pidió las tasas de su región. El mismo error se repitió y la comprobación no avanzó.",
  "que_hacer": "Revisar cómo se crea un carrito válido, incluir las tasas de la región y la tasa general de 0.18, y volver a intentar comprobar el total sin cambiar el valor esperado."
}
```
