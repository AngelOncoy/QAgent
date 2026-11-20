# ADR-019: Identidad por firma de métodos Java

- Fecha: 2026-11-20.
- Issue: #299; épica histórica EP-12 (#174).
- Estado: Implementación propuesta para revisión del equipo mediante PR.
- Relacionados: ADR-007, ADR-008, ADR-009, ADR-017 y ADR-018.

## Problema

`Clase.metodo` no identifica una sobrecarga. Rechazar el archivo completo elimina
también sus métodos no ambiguos. El mismo nombre tampoco permite atribuir
contadores JaCoCo ni resultados PIT sin mezclar firmas.

## Decisión

Los nombres únicos conservan su identidad histórica. Cuando hay varias
declaraciones del mismo nombre en una clase, incluso no públicas, cada objetivo
usa `Clase.metodo(tipo1,tipo2)`: nombres de parámetros excluidos, genéricos
borrados, arrays conservados y varargs normalizado a `[]`. Las clases miembro
conservan su ruta `Exterior.Interior`. No se recorren clases locales o anónimas.
Dos declaraciones con la misma firma borrada son inválidas; se omiten
individualmente con diagnóstico, conservando los otros objetivos del archivo.

Se califican únicamente primitivos, tipos conocidos de `java.lang`, imports
explícitos y tipos declarados en el archivo. No se introduce un compilador
semántico ni se resuelven imports comodín por conjetura. Una identidad sin tipo
resoluble no autoriza atribuir métricas o invocar otra sobrecarga.

El schema `planner_contract.v3` admite esta extensión para Java. No se añade
ningún campo obligatorio ni se cambian contratos guardados. Un contrato antiguo
sin sufijo puede asociarse a la fuente actual solo si su firma textual identifica
una única declaración. La generación valida además esa firma. Los archivos de
spec nuevos con sufijo incorporan hash de su identidad completa: `int` e `int[]`
no colisionan después de limpiar los nombres para Windows.

El oráculo verifica el tipo estático de cada argumento, además de su valor del
Planner. Rechaza promociones, boxing y conversiones que no pueda demostrar.
Los literales usan su tipo Java real; `long`, `float` y `double` requieren su
forma literal correspondiente. Varargs se invoca como array explícito. `null`
necesita cast al tipo completo elegido. Un alias con tipo `Object` no se acepta
como argumento de la sobrecarga `String`, aunque su inicializador sea una cadena.
Esto puede rechazar pruebas Java válidas pero demasiado complejas para el
guardrail; no se relaja ninguna aserción ni se ejecuta Java para deducir esperados.

JaCoCo se selecciona por los parámetros del descriptor JVM; la estructura XML
conserva el descriptor completo, incluido el retorno. Un nombre histórico sin
firma no recibe cobertura cuando el informe contiene varias sobrecargas.
Los formatos históricos de cobertura siguen siendo legibles.

PIT mantiene `targetClasses` exacto y `excludedMethods` para nombres. Para una
selección por firma, añade en la copia desechable una anotación con retención
CLASS a las otras declaraciones del mismo nombre. Se configura el interceptor
FANN de PIT para excluirlas antes de evaluar mutantes. Se preservan cuerpos,
aserciones y números de línea. La anotación y la fuente modificada nunca se
escriben en el proyecto original. Una colisión con su ruta reservada es un error.
El XML se contrasta por clase, método **y descriptor**; cualquier firma ajena
invalida el score. No basta con filtrar resultados después de mutar otros métodos.

## Límites y consecuencias

La resolución de llamadas entre funciones sigue siendo conservadora: una
llamada a un nombre sobrecargado sin tipos demostrables no crea una arista
inventada. La inferencia de ADR-018 conserva su clasificación de regresión y
separa los cuerpos por identidad; no se extiende a Spring.

PIT conserva sus límites previos sobre clases anidadas y endpoints. Tampoco
se añaden Gradle, servicios reales, pruebas de propiedades ni dependencias.
Las ambigüedades de herencia, genéricos, tipos externos o despacho dinámico que
requieren semántica de compilador no se resuelven por IA.

## Referencias técnicas

- [PIT: excludedMethods](https://pitest.org/quickstart/maven/#excludedmethods).
- [Interceptor FANN y su parámetro annotation](https://github.com/hcoles/pitest/blob/master/pitest-entry/src/main/java/org/pitest/mutationtest/build/intercept/annotations/ExcludedAnnotationInterceptorFactory.java).
- [Pruebas de #299](../../tests/lenguajes/test_issue299_sobrecargas.py),
  [PIT estático](../../tests/sandbox/test_issue299_pit_firmas.py) y
  [JUnit/PIT en Docker](../../tests/sandbox/test_issue299_sobrecargas_docker.py).
