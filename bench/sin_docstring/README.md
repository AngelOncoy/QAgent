# Banco sin docstrings (#275, ADR-015)

Proyecto mínimo cuyas funciones **no tienen docstring ni tipos**. Mide si el contrato
inferido (leyendo cuerpo, llamadores y tests existentes) encuentra defectos que, sin
inferencia, QAgent omitiría.

| Función | Defecto sembrado | Evidencia estática que lo delata |
|---|---|---|
| `aplicar_descuento` | Devuelve el monto del descuento, no el precio final | `uso.total_a_pagar` lo usa como precio a cobrar; `tests/test_uso.py::test_total_con_veinte_por_ciento` espera 80 |
| `es_mayor_de_edad` | `edad > 18` excluye a los de 18 años | `uso.puede_comprar_alcohol` y `tests/test_uso.py::test_a_los_18_puede_comprar` |
| `doble` | Ninguno (control) | Su cuerpo; la prueba inferida debe pasar |

## Cómo medir

1. Abre esta carpeta como proyecto en QAgent (necesita Docker y un modelo real).
2. Corre con `[inferencia] activa = false` (las tres se omiten) y luego con `activa = true`.
3. Comparación esperada con la inferencia activa:
   - `aplicar_descuento` y `es_mayor_de_edad`: **hallazgo a revisar** (la prueba inferida
     falla contra el código).
   - `doble`: la prueba de regresión pasa.
4. Anota aquí el resultado. Si la inferencia no aporta hallazgos útiles frente a omitir, o
   produce más falsos hallazgos que útiles, el tipo queda **apagado por defecto** (ADR-015,
   sección 4.7).

Resultados: _pendientes de la primera medición con un modelo real_.
