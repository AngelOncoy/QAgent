# TA-01 — Banco de pruebas Java con Javadoc y JUnit 5

## Referencia

- Issue: #131.
- Rama de trabajo: feat/ta-01-banco-java.
- Rama de destino del Pull Request: develop.

## Objetivo

Crear un banco Java reproducible con tres métodos correctos y tres
métodos con defectos intencionales, documentados mediante Javadoc
y comprobados con JUnit 5.

Este trabajo prepara una referencia para futuras evaluaciones
del soporte Java. No incorpora todavía análisis ni generación
de pruebas Java en QAgent.

## Alcance

El banco se encuentra en bench_java y funciona como un proyecto
Maven independiente.

No se modificó el núcleo Python de QAgent.

## Entorno utilizado

- Sistema operativo: Windows 11.
- JDK: Eclipse Temurin 21.0.7.
- Apache Maven: 3.10.0.
- JUnit Jupiter: 5.11.4.
- Maven Compiler Plugin: 3.13.0.
- Maven Surefire Plugin: 3.5.2.
- Codificación del proyecto: UTF-8.

Las versiones de JUnit y de los plugins están declaradas en pom.xml.

## Especificaciones independientes

Los comportamientos esperados se definieron en
[casos.md](../bench_java/casos.md) antes de implementar los métodos.

Cada método incluye Javadoc con su comportamiento, parámetros,
precondiciones y resultado esperado.

Las pruebas utilizan esas reglas como referencia. Los valores
esperados no se obtienen ejecutando la implementación.

## Implementación

### Casos correctos

La clase BancoCorrecto contiene:

- C01: sumarPrecios, suma los precios y devuelve cero para una lista vacía.
- C02: aplicarDescuento, calcula el precio después de un descuento.
- C03: esMayorDeEdad, comprueba la mayoría de edad desde los 18 años.

BancoCorrectoTest contiene ocho pruebas que comprueban ejemplos
y casos límite de esos métodos.

### Defectos intencionales

La clase BancoDefectuoso contiene:

- D01: calcularPromedio, pierde decimales por división entera.
- D02: calcularEnvio, excluye incorrectamente el límite de 100.
- D03: calcularTotalConImpuesto, resta el impuesto en lugar de sumarlo.

Los defectos, las entradas y los resultados esperados se detallan
en [bugs.md](../bench_java/bugs.md).

BancoDefectuosoTest contiene tres pruebas de detección controlada.

## Control de fallos intencionales

Cada prueba de detección compara el resultado real con el valor
correcto mediante assertEquals.

Un assertThrowsExactly externo exige que esa comparación lance
AssertionFailedError. Así se comprueba el incumplimiento del contrato
sin dejar la ejecución normal del banco en estado fallido.

La llamada al método se realiza fuera de ese control. Una excepción
técnica durante la ejecución no se acepta como detección del defecto.

Estas pruebas confirman que los bugs sembrados siguen siendo
detectables; no certifican que los métodos defectuosos sean correctos.

No se utiliza una opción para ignorar todos los fallos de Maven.
Los errores inesperados siguen produciendo una ejecución fallida.

## Compilación y ejecución

Requisitos: JDK 21 y Maven disponibles en la terminal.
La primera ejecución necesita internet para descargar dependencias.

Ejecutar desde la raíz del repositorio QAgent.

### Comprobar las herramientas

    java -version
    javac -version
    mvn -version

### Validar la configuración

    mvn -f bench_java/pom.xml validate

### Compilar las clases Java

    mvn -f bench_java/pom.xml compile

### Limpiar, compilar y ejecutar las pruebas

    mvn -f bench_java/pom.xml clean test

Maven genera los resultados en bench_java/target/surefire-reports/.
La carpeta target está excluida del control de versiones.

## Resultados observados

La ejecución de clean test compiló las dos clases del banco
y las dos clases de prueba.

| Clase de pruebas | Ejecutadas | Fallos | Errores | Omitidas |
|---|---:|---:|---:|---:|
| BancoCorrectoTest | 8 | 0 | 0 | 0 |
| BancoDefectuosoTest | 3 | 0 | 0 | 0 |
| Total | 11 | 0 | 0 | 0 |

Resultado de Maven: BUILD SUCCESS.

Las ocho pruebas de los casos correctos fueron satisfactorias.
Las tres pruebas restantes detectaron los incumplimientos esperados
de los métodos defectuosos.

## Incidencia resuelta durante el desarrollo

Inicialmente, BancoCorrecto.java se guardó fuera de la carpeta
de fuentes del proyecto Maven.

Al compilar las pruebas apareció el mensaje cannot find symbol
para BancoCorrecto.

Se corrigió colocando el archivo en:

    bench_java/src/main/java/org/qagent/bench/BancoCorrecto.java

Después se ejecutó clean test y las pruebas finalizaron correctamente.

Esta incidencia fue un problema de ubicación del archivo,
no uno de los defectos intencionales del banco.

## Limitaciones

- Las entradas fuera de las precondiciones de casos.md no se evalúan.
- Los cálculos decimales se comparan con tolerancia numérica.
- El banco no está integrado todavía al pipeline de QAgent.
- Esta ejecución no demuestra que la CI remota haya sido ejecutada.

## Estado de entrega

- [x] Seis casos definidos mediante especificaciones independientes.
- [x] Tres métodos correctos implementados.
- [x] Tres defectos intencionales identificados.
- [x] Métodos documentados con Javadoc.
- [x] Proyecto compilado mediante Maven.
- [x] Once pruebas ejecutadas satisfactoriamente con JUnit 5.
- [x] Defectos y resultados documentados.
- [ ] README del banco completado.
- [ ] Cambios revisados y publicados en la rama.
- [ ] Pull Request creado hacia develop.