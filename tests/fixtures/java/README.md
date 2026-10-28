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
