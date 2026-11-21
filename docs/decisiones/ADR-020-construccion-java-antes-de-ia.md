# ADR-020: Comprobación de construcción Java antes de consumir IA

- Fecha: 2026-11-21.
- Issue: #305; épica histórica EP-12 (#174).
- Estado: Propuesta de implementación para revisión mediante PR.
- Relacionados: ADR-007, ADR-008, ADR-009, ADR-017 y ADR-019.

## Decisión

La admisión estática de Maven no demuestra que el proyecto compile con las
bibliotecas, plugins y JDK del sandbox. El adaptador Java requiere una comprobación
de construcción después de preparar la imagen y antes de planificar o generar.
Los demás adaptadores conservan la planificación asíncrona de #148.

La imagen se prepara en su etapa de descarga. Después se ejecuta, exclusivamente
en un contenedor con las restricciones habituales y sin red:

```text
mvn --offline --batch-mode --no-transfer-progress
    -Dmaven.repo.local=/opt/qagent/m2 -f /work/proyecto/pom.xml
    [-pl <módulos seleccionados> -am]
    -DskipTests=true -Dmaven.test.skip=true -DskipITs=true clean compile
```

El alcance comprende los módulos con objetivos seleccionados y sus dependencias
del reactor. `clean` elimina salidas anteriores dentro de la copia del contenedor;
`compile` recorre la construcción de producción. No se solicita `test`,
`test-compile`, `verify` ni la ejecución de pruebas existentes o generadas.
Los flags omiten los proveedores estándar de tests. Los plugins del proyecto
vinculados a las fases de construcción sí se ejecutan en Docker: sus acciones
arbitrarias no pueden reinterpretarse como tests dirigidos por QAgent.

Se utiliza el POM original y la configuración Maven admitida por ADR-017. No se
sustituyen versiones de dependencias/plugins ni el JDK para lograr compatibilidad.
Los límites de BOM, classifiers, fuentes adicionales y configuración efectiva de
#303/#304 se mantienen; una limitación se comunica antes de consumir IA.

## Orden y diagnóstico

El orquestador consulta una capacidad del adaptador; no incorpora comandos Maven
ni decisiones específicas de Java. Java espera a su imagen, comprueba la
construcción y solo permite las llamadas de IA cuando el resultado es aprobado.
La IA simulada no salta esta comprobación. La dependencia se puede sustituir
explícitamente en los tests del sistema, igual que la ejecución de Docker.

Se distinguen dependencias ausentes, configuración, incompatibilidad de herramienta,
compilación y fallos técnicos no clasificables. Timeout y cancelación no son bugs
del proyecto. El resultado y un log acotado y saneado quedan en la corrida; no se
deducen resultados esperados ejecutando la aplicación ni se modifican contratos.

## Reutilización

Solo se reutiliza una construcción aprobada. Su huella incluye la versión de la
política, comando/selección, contenido y rutas de las entradas del proyecto y el
ID inmutable de la imagen utilizada, que identifica JDK, Maven y caché offline.
También incluye plataforma, versión del daemon y CPU disponibles, y límites
de CPU, memoria y tiempo configurados para esta comprobación.
Se incluyen fuentes, recursos, POM, configuración y scripts de todos los módulos;
se excluyen credenciales, datos de QAgent y salidas estándar `target` que `clean`
elimina. La huella se obtiene de una copia fija, no de fuentes que puedan cambiar
durante la compilación. Cambiar una entrada o la imagen invalida la reutilización.

El cache conserva únicamente aprobaciones válidas, con escritura atómica. Un
registro corrupto, una cancelación, timeout o fallo nunca autoriza el uso de IA.
La reutilización presupone los mismos inputs declarados de construcción; no
certifica servicios externos ni determinismo de plugins que usan reloj/azar.

## Consecuencias

Java deja de solapar planificación con preparación. Evita consumir IA en un
proyecto cuya construcción todavía no se ha comprobado. No afirma que `compile`
valide todos los perfiles, empaquetado, servicios, librerías o tests del proyecto.
Los errores de construcción conservan su diagnóstico técnico y no producen
veredictos de las pruebas generadas. La épica histórica no se reabre.

## Referencias

- [Maven: compilación de producción y de tests](https://maven.apache.org/plugins/maven-compiler-plugin/).
- [Surefire: omisión de ejecución y compilación de tests](https://maven.apache.org/surefire/maven-surefire-plugin/examples/skipping-tests.html).
- [Failsafe: skipITs y maven.test.skip](https://maven.apache.org/surefire/maven-failsafe-plugin/examples/skipping-tests.html).
- [Maven: selección de módulos y also-make](https://maven.apache.org/guides/mini/guide-multiple-modules.html).
