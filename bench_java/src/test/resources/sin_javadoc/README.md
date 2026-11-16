# Regresión Java sin Javadoc (#292)

Fixture independiente con Maven de un módulo. El sandbox usa JDK 25 y compila
para Java 21. `sumar` y `doble` no tienen Javadoc y cuentan con evidencia de tests
existentes, que se leen sin ejecutarlos al construir el contexto de inferencia.
`momentoActual` depende del reloj: no se fija su resultado y debe quedar omitido.

Para la comprobación visual, abrir esta carpeta como proyecto en QAgent, seleccionar
Unitarias y activar la inferencia en Preparar. Se pueden revisar los contratos
antes de generar. Los casos inferidos deben citar evidencia y mostrarse como
regresión sin contrato documentado. Con inferencia desactivada los métodos sin
contrato no deben recibir casos inventados. El número de casos que proponga un
proveedor real depende de la evidencia que acepte; una omisión sigue siendo válida
cuando no puede justificar el resultado.

La ejecución de las pruebas generadas ocurre exclusivamente en Docker sin red.
Este fixture no valida por sí solo métodos con servicios, bases de datos ni estados
de construcción desconocidos.
