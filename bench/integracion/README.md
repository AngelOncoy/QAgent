# Banco de integración interna (#245, ADR-014)

Proyecto mínimo para medir las pruebas de integración interna.

| Raíz | Cadena que se ejecuta de verdad | Qué se simula | Defecto |
|---|---|---|---|
| `total_del_pedido` | `total_del_pedido` → `aplicar_descuento` | nada | **Sembrado**: `aplicar_descuento` espera un porcentaje (0-100) y se le pasa una fracción (0-1). Con `100.0, 0.2, 2` devuelve `199.6` en lugar de `160.0`. Una unitaria que simula `aplicar_descuento` no lo ve. |
| `total_con_impuesto` | `total_con_impuesto` → `con_impuesto` | nada | Ninguno (control: la integración debe aprobar). |
| `recibo` | `recibo` | `sello_de_hora` (usa el reloj) | No es candidata: su única función interna es de efecto y se simula. |

## Cómo medir

Necesita Docker y una clave real (usa el modelo configurado en `config.toml`), así que no
forma parte de `python test.py`:

1. Abrir `bench/integracion/` como proyecto en QAgent.
2. Corrida A: solo **Unitarias** sobre `total_del_pedido`.
3. Corrida B: solo **Integración interna** sobre `total_del_pedido`.
4. Comparar los veredictos en Resultados.

**Criterio del ADR-014 (4.7):** si la integración no encuentra nada que las unitarias no
encuentren, el tipo queda apagado por defecto y se anota en el ADR. Hoy ya viene apagado:
nunca se activa sin que la persona lo elija en Preparar.
