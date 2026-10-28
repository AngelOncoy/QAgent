# Banco Java de QAgent — TA-01 (#131)

Proyecto de referencia independiente del núcleo Python de QAgent.
Contiene tres métodos correctos y tres con defectos intencionales.

## Requisitos

- JDK 21. Entorno utilizado: Eclipse Temurin 21.0.7.
- Maven. Versión utilizada: 3.10.0.
- Internet en la primera ejecución para descargar dependencias.

JUnit Jupiter 5.11.4 se descarga automáticamente mediante Maven.

## Ejecutar

Desde la raíz del repositorio QAgent:

    mvn -f bench_java/pom.xml clean test

Resultado esperado:

    Tests run: 11, Failures: 0, Errors: 0, Skipped: 0
    BUILD SUCCESS

Ocho pruebas verifican comportamientos correctos.
Tres comprueban la detección controlada de defectos conocidos;
no certifican que los métodos defectuosos sean correctos.

Los errores técnicos inesperados hacen fallar la ejecución.

## Estructura

- src/main/java: métodos del banco y Javadoc.
- src/test/java: pruebas JUnit 5.
- casos.md: especificaciones independientes.
- bugs.md: identificación de defectos y resultados esperados.
- pom.xml: configuración Maven y dependencias.
- target/surefire-reports: informes generados, excluidos de Git.

## Documentación

- [Casos de referencia](casos.md).
- [Defectos intencionales](bugs.md).
- [Informe técnico](../docs/ta-01-banco-java.md).

Este banco todavía no incorpora soporte Java a la aplicación QAgent.