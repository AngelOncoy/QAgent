# Informes JUnit del banco Java

`junit5-banco.xml` procede de los dos archivos `TEST-*.xml` producidos por
`mvn -f bench_java/pom.xml clean test` en la ejecución local del 28/10/2026.
Se combinaron bajo una raíz `testsuites` y se retiraron los elementos que no
son `testcase`, incluidas las propiedades del entorno. Se conservaron los
atributos de suites y casos; los tiempos no fueron inventados.

- JDK: Eclipse Temurin 21.0.7.
- Maven: 3.10.0; Surefire: 3.5.2; JUnit Jupiter: 5.11.4.
- BancoCorrectoTest: 8 casos aprobados, suite de 0.111 s.
- BancoDefectuosoTest: 3 detecciones controladas aprobadas, suite de 0.016 s.
- Tiempo total Maven observado: 9.836 s (no equivale al tiempo de suites).

Esta fixture comprueba lectura de resultados históricos sin ejecutar Java.
La ejecución actual se verifica con Maven y sus informes nuevos. Los XML de
fallo, error y omisión se definen como ejemplos controlados en
`tests/lenguajes/test_java_resultados.py`; no se presentan como ejecuciones reales.

## Fixture de fallos controlados para #182

`junit5-fallos-controlados.xml` es **sintético**: reproduce formatos JUnit 5 de
comparación, error y omisión para comprobar su lectura sin Docker. No es una
grabación de una ejecución real. La evidencia real previa del banco se conserva
en `junit5-banco.xml` y se describe al inicio de este documento.

## Fixture JaCoCo controlada para #182

`jacoco-controlado.xml` es **sintético**. Tiene un archivo con cinco líneas
ejecutables, una faltante, y una rama cubierta de dos. El método calcular tiene
dos líneas cubiertas de tres (66.67 %) y una rama cubierta de dos (50 %); constante
tiene una línea cubierta y no tiene ramas. La cobertura del archivo es 80 %.
El XML comprueba interpretación y no es evidencia de una ejecución real con JaCoCo.

## Informes reales del sandbox para #182

`junit5-sandbox-promedio.xml` y `jacoco-sandbox-promedio.xml` se obtuvieron el
30/10/2026 mediante `tests/sandbox/test_java_ejecucion_docker.py` en
qagent-sandbox:java, sin red. El banco conserva sus fuentes TA-01 y usa un POM
controlado con las herramientas de la receta de la imagen; la prueba JUnit es
una entrada controlada, no una salida del Generator de #184.

Se ejecutó un caso de calcularPromedio([2, 3]): JUnit registró un fallo con 2.5
esperado y 2.0 obtenido; JaCoCo registró 100 % de líneas y ramas del método.
Se conservaron ambos informes pese al código de salida fallido de JUnit.
Se retiraron del XML JUnit las propiedades del entorno. Las suites, casos,
diagnósticos y tiempos son reales. No se ejecutan pruebas al leer estas fixtures.

Para regenerarlos, definir QAGENT_GRABAR_JAVA=1 y ejecutar la prueba Docker.
Solo se escriben después de comprobar el resultado y la conservación del proyecto.
