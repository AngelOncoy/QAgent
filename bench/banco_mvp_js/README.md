# Banco JS/TS con bugs sembrados (#176)

Equivalente de `bench/banco_mvp.py` para JavaScript y TypeScript: las mismas seis
funciones, con el mismo comportamiento documentado y los mismos tres bugs. Lo usa
`tests/lenguajes/test_banco_js.py` para comprobar, sin Docker ni Node.js, que el
análisis encuentra las funciones y que el Planner emite `planner_contract.v3`
válidos cuyos valores esperados salen del JSDoc y de los tipos, nunca del código.

| Archivo | Formato | Función | ¿Bug? | Lo detecta el `@example` |
|---|---|---|:---:|---|
| `src/precios.ts` | TS, ESM | `calcularDescuento` | **Sí** (Bug 1): devuelve el descuento, no el precio final | `calcularDescuento(100, 20) // => 80` |
| `src/personas.mjs` | JS, ESM | `clasificarEdad` | **Sí** (Bug 2): `<= 18` en lugar de `< 18` | `clasificarEdad(18) // => "adulto"` |
| `src/listas.cjs` | JS, CommonJS | `buscarElementoMayor` | **Sí** (Bug 3): empieza en 0 y falla con negativos | `buscarElementoMayor([-10, -5, -20]) // => -5` |
| `src/texto.ts` | TS, ESM | `esPalindromo` | No | — |
| `src/texto.ts` | TS, ESM (flecha) | `invertirPalabras` | No | — |
| `src/texto.ts` | TS, método | `Formateador.moneda` | No | — |
| `src/texto.ts` | TS, tipo literal | `versionFormato` | No | el tipo `"v1"` fija el valor |
| `src/sin_documentar.js` | JS, ESM | `mezclar`, `promedio` | — | ninguno: quedan «sin resultado esperado verificable» |

El oráculo es estricto (ver `docs/contratos/oraculos-js-ts.md`): un valor esperado
solo vale si coincide con un `@example`, un `@throws` o un tipo de retorno literal.
`promedio` tiene JSDoc, pero su `@returns` en prosa no fija ningún valor.
