# Banco de referencia Java — TA-01 (#131)

## Objetivo

Definir comportamientos conocidos para comprobar pruebas automatizadas
en Java con JUnit 5.

Los resultados esperados se establecen mediante estas reglas,
independientemente de la implementación.

## C01 — Sumar precios

- Método: sumarPrecios.
- Regla: devuelve la suma de los precios recibidos.
- Ejemplo: [10, 20] devuelve 30.
- Lista vacía: devuelve 0.
- Restricciones: lista no nula con precios finitos y no negativos.
- Implementación: correcta.

## C02 — Aplicar descuento

- Método: aplicarDescuento.
- Regla: precio final = precio × (1 - porcentaje / 100).
- Ejemplo: precio 100 y porcentaje 20 devuelve 80.
- Límites: 0 % conserva el precio; 100 % devuelve 0.
- Restricciones: precio finito y no negativo; porcentaje entre 0 y 100.
- Implementación: correcta.

## C03 — Validar mayoría de edad

- Método: esMayorDeEdad.
- Regla: devuelve true para edades mayores o iguales a 18.
- Ejemplo: 18 devuelve true.
- Límite inferior: 17 devuelve false.
- Restricciones: edad entera no negativa.
- Implementación: correcta.

## D01 — Calcular promedio

- Método: calcularPromedio.
- Regla: promedio = suma de los números / cantidad de números,
  conservando la parte decimal.
- Ejemplo: [2, 3] devuelve 2.5.
- Restricciones: lista no nula y no vacía de números enteros pequeños,
  cuya suma no desborde un int.
- Defecto intencional: realiza división entera.
- Resultado defectuoso del ejemplo: 2.0.
- La prueba debe exigir: 2.5.

## D02 — Calcular costo de envío

- Método: calcularEnvio.
- Regla: el envío cuesta 10 para compras menores a 100;
  desde 100 inclusive, cuesta 0.
- Ejemplo: compra de 100 devuelve 0.
- Otros casos: 99 devuelve 10; 101 devuelve 0.
- Restricciones: importe finito y no negativo.
- Defecto intencional: usa > en lugar de >= para el envío gratuito.
- Resultado defectuoso para una compra de 100: 10.
- La prueba debe exigir: 0.

## D03 — Calcular total con impuesto

- Método: calcularTotalConImpuesto.
- Regla: total = subtotal × (1 + porcentaje / 100).
- Ejemplo: subtotal 100 y porcentaje 18 devuelve 118.
- Límite: un impuesto de 0 % conserva el subtotal.
- Restricciones: subtotal y porcentaje finitos y no negativos.
- Defecto intencional: resta el impuesto en lugar de sumarlo.
- Resultado defectuoso del ejemplo: 82.
- La prueba debe exigir: 118.

## Política de entradas

Las entradas fuera de las restricciones indicadas no forman parte
de estos seis casos iniciales.

Las pruebas con resultados decimales utilizarán una tolerancia numérica.