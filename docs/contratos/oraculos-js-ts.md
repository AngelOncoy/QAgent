# Contrato `oracle.v1`: oráculos JavaScript y TypeScript

## Objetivo

`oracle.v1` representa una expectativa verificable para una función JavaScript o TypeScript sin ejecutar el código bajo prueba. El contrato separa dos preguntas:

1. ¿El JSON tiene una forma válida?
2. ¿La fuente registrada demuestra realmente el valor o la excepción esperada?

El schema responde la primera. `contracts.validar_oraculo_js_ts()` responde la segunda al contrastar el contrato con documentación obtenida previamente de un registro confiable.

## Fuentes permitidas

| `fuente` | Uso |
|---|---|
| `contrato_explicito` | Casos de entrada/salida, invariantes, reglas de negocio y pre/postcondiciones declaradas fuera de la implementación. |
| `jsdoc` | `@returns`, `@throws`, `@example` o restricciones que describan un comportamiento concreto. |
| `typescript` | Tipos literales, uniones y especificaciones semánticas asociadas a la firma. |

El campo `caracter` distingue evidencia de comportamiento, tipos literales o uniones, tipos generales, documentación genérica y contradicciones. `number`, `string` o `boolean` solo delimitan un tipo: no justifican por sí mismos un valor concreto.

## Campos

| Campo | Regla |
|---|---|
| `version` | Siempre `"1"`. |
| `lenguaje` | `javascript` o `typescript`, igual que EN-17. |
| `modulo`, `objetivo`, `firma` | Identidad compatible con `planner_contract.v3`. |
| `entrada` | Datos documentados del caso. Puede contener `0`, `false`, `""` o `null`. |
| `comprobacion` | `igualdad`, `identidad`, `contiene` o `excepcion`. |
| `valor_esperado` / `excepcion_esperada` | Exactamente uno cuando la evidencia es verificable. La presencia de la clave, no su valor de verdad, determina si existe. |
| `estado_evidencia` | `verificable`, `insuficiente`, `contradictoria` o `sin_procedencia`. |
| `evidencia` | Id, fuente, carácter, ubicación, referencia y fragmento documental. |
| `motivo` | Obligatorio cuando la evidencia no es verificable. |

## Reglas de suficiencia

- Un resultado verificable necesita una evidencia registrada y una expectativa documentada idéntica.
- La evidencia recibida debe coincidir con la copia del registro confiable; no basta con reutilizar su id.
- Un tipo general, un JSDoc genérico o una contradicción nunca se promueven automáticamente a `verificable`.
- Una contradicción se conserva como `contradictoria`; no se elige arbitrariamente una de sus afirmaciones.
- `sin_procedencia` no puede contener evidencia ni resultado esperado.
- La ubicación debe ser relativa al proyecto y su rango de líneas debe ser coherente.
- No existe una fuente `ejecucion`: observar el comportamiento actual no crea el oráculo.

La validación demuestra que el contrato coincide con una fuente registrada. No demuestra que la documentación original sea verdadera o esté actualizada.

## Ejemplo válido

```json
{
  "version": "1",
  "lenguaje": "javascript",
  "modulo": "src/matematicas.js",
  "objetivo": "sumar",
  "firma": "sumar(a, b)",
  "entrada": {"a": 2, "b": 3},
  "comprobacion": "igualdad",
  "valor_esperado": 5,
  "estado_evidencia": "verificable",
  "evidencia": {
    "id": "ev-sumar-2-3",
    "fuente": "contrato_explicito",
    "caracter": "comportamiento",
    "ubicacion": {"archivo": "docs/matematicas.md", "linea_inicio": 10},
    "referencia": "MAT-SUMA-01",
    "fragmento": "Para a=2 y b=3, sumar devuelve 5."
  }
}
```

El registro confiable correspondiente contiene la misma `evidencia` y `valor_documentado: 5`.

## Ejemplos inválidos o insuficientes

- `calcular(a: number, b: number): number` sin regla funcional: `insuficiente`.
- `@returns valor procesado` sin relación entre entrada y salida: `insuficiente`.
- `@returns Celsius` junto con un ejemplo expresado en Fahrenheit: `contradictoria`.
- Un contrato que declare `valor_esperado: 6` usando la evidencia que documenta `5`: se rechaza.
- Un id de evidencia que no exista en el registro confiable: se rechaza.

Los seis casos completos, con código, documentación y justificación, están en `tests/fixtures/en18/oraculos_js_ts.json`.

## Versionado e integración

- Schema: `src/qagent/contracts/oracle.v1.schema.json`.
- Ejemplo distribuido: `src/qagent/contracts/ejemplos/oracle.v1.json`.
- Familia versionada: `contracts.FAMILIA_ORACLE`.
- Validación estructural: `contracts.validar_versionado()`.
- Validación contextual: `contracts.validar_oraculo_js_ts()`.

EN-18 no cambia `planner_contract.v2`, `planner_contract.v3` ni el flujo Python.

## Uso en el análisis y el Planner (#176)

El analizador JS/TS (`qagent.lenguajes.javascript_oraculo`) construye el registro confiable de cada función exportada y lo guarda en su campo `evidencias`. El oráculo es **estricto**: solo fijan una expectativa

| Fuente | Ejemplo | Fija |
|---|---|---|
| `@example` con llamada y resultado literal | `calcularDescuento(100, 20) // => 80`, `f(-1) // throws RangeError` | el valor o la excepción para esa entrada exacta |
| `@throws {Tipo} condición` | `@throws {RangeError} si la edad es negativa` | la excepción; la entrada la propone el modelo según la condición |
| Tipo de retorno literal (TS o `@returns {…}`) | `function v(): "v1"` | el valor para cualquier entrada |

Un `@returns` en prosa, una unión de literales y un tipo general se registran, pero no bastan: el caso queda `insuficiente`. Dos `@example` con la misma entrada y distinto resultado, o un resultado incompatible con el tipo de retorno, quedan `contradictoria`. Los números se comparan como en JS (`5` y `5.0` son iguales).

El Planner solo pide casos de las funciones con alguna evidencia que fije un resultado; las demás quedan omitidas como «sin resultado esperado verificable». Cada caso propuesto se convierte en un `oracle.v1` con `oraculo_del_caso()` y se valida con `validar_oraculo_js_ts()`; si no es verificable, se descarta con su motivo. El `oracle.v1` no viaja dentro de `planner_contract.v3`: es determinista y la generación puede recalcularlo con el mismo análisis.

## Limitaciones

- Solo se reconocen `@example` de una línea por llamada, con argumentos y resultado literales (sin variables, `undefined` ni `NaN`).
- No se ejecutan Jest o Vitest.
- No se certifica la veracidad material de la documentación; se conserva y contrasta su procedencia.
