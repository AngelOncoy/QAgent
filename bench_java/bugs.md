# Defectos intencionales — TA-01 (#131)

Este banco contiene tres defectos sembrados deliberadamente.
Los resultados correctos se definen en casos.md y en el Javadoc,
independientemente de las implementaciones defectuosas.

Los defectos deben conservarse como referencia para evaluar
la detección de errores.

## D01 — División entera en el promedio

- Método: BancoDefectuoso.calcularPromedio.
- Defecto: divide dos enteros antes de convertir el resultado a double,
  por lo que pierde la parte decimal.
- Entrada: [2, 3].
- Resultado esperado: 2.5, porque (2 + 3) / 2 = 2.5.
- Resultado defectuoso: 2.0.
- Prueba: detectaDivisionEntera.

## D02 — Límite incorrecto para envío gratuito

- Método: BancoDefectuoso.calcularEnvio.
- Defecto: utiliza > 100 en lugar de >= 100.
- Entrada: importe de compra de 100.
- Resultado esperado: 0, porque el envío es gratuito desde 100 inclusive.
- Resultado defectuoso: 10.
- Prueba: detectaLimiteDeEnvioIncorrecto.

## D03 — Impuesto restado

- Método: BancoDefectuoso.calcularTotalConImpuesto.
- Defecto: resta el impuesto en lugar de sumarlo.
- Entrada: subtotal 100 y porcentaje 18.
- Resultado esperado: 118, porque 100 × (1 + 18 / 100) = 118.
- Resultado defectuoso: aproximadamente 82.
- Prueba: detectaImpuestoRestado.

## Ejecución controlada

Las pruebas comparan los resultados reales con los valores correctos
mediante assertEquals.

Un assertThrowsExactly externo comprueba que esa comparación produce
AssertionFailedError, confirmando la detección del incumplimiento.

La llamada a cada método se realiza fuera de assertThrowsExactly.
Por tanto, una excepción técnica durante su ejecución no se considera
una detección válida del defecto.

Estas pruebas verifican la presencia de los defectos conocidos;
no certifican que los métodos defectuosos sean correctos.
Si se corrige un defecto, su prueba de detección deberá fallar
para advertir que el banco cambió.

## Resultado observado

Comando ejecutado desde la raíz de QAgent:

    mvn -f bench_java/pom.xml clean test

- BancoCorrectoTest: 8 pruebas satisfactorias.
- BancoDefectuosoTest: 3 detecciones controladas satisfactorias.
- Total: 11 pruebas.
- Fallos: 0.
- Errores: 0.
- Pruebas omitidas: 0.
- Estado: BUILD SUCCESS.

Los fallos de las aserciones internas son esperados y controlados.
Los errores de compilación, dependencias o ejecución no se ocultan.