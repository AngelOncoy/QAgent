# Generación JUnit 5 y guardrail Java (#184)

## Base y orden de integración

La rama feat/184-generacion-guardrail-java parte de develop, commit c1a8e0d, con
#181 integrado mediante el PR #215. No incorpora el PR #216 de #182 ni la rama de
mutación #180. Este documento registra el desarrollo por bloques; no afirma que
la tarea esté completa antes de validar todos sus criterios.

## Primer bloque: generación, rutas y sintaxis

JavaAdapter entrega al Generator compartido el prompt JUnit de java_generacion.py.
El contexto se obtiene por tree-sitter de la fuente del contrato: paquete, imports,
clase, firma, parámetros, condición static y constructores accesibles. Se necesita
ruta_proyecto para no adivinar el paquete ni los constructores. La firma debe
coincidir con la fuente actual. No se envían cuerpos ni notas implNote como oráculo.

El prompt conserva los esperados y excepciones del contrato del Planner, pide
@Test por caso, assertEquals/assertTrue/assertFalse/assertThrows y limita Mockito
a dependencias recibidas por el constructor. Prohíbe mockear o espiar la clase
probada, sustituir el método por un stub y descubrir el esperado ejecutando código.
Estas instrucciones del prompt se complementarán con validación estática del
oráculo y comparación de aserciones en el siguiente bloque: el prompt por sí solo
no demuestra ausencia de Assertion Laundering.

El Generator sigue siendo el real de QAgent; las pruebas sustituyen únicamente
su cliente LLM por respuestas Java grabadas de costo y tokens cero. No se usa una
API, javac, Maven ni Docker para estas comprobaciones. La sintaxis se valida con
el parser Java existente, sin confundir parseo con compilación o resolución de tipos.

archivo_de_prueba devuelve src/test/java/paquete/ClaseTest.java; el paquete se pasa
explícitamente desde el AST. Para clases anidadas, Exterior.Interior.f genera
Exterior_InteriorTest.java. El paquete predeterminado no añade carpetas inventadas.
El nombre del archivo generado se incorpora a generated_test.v2 mediante el punto
opcional archivo_para_contrato. Python y JS/TS conservan su comportamiento.

El schema acepta rutas src/test/java para Java y mantiene los nombres simples de
Java ya guardados. No amplía las rutas admitidas para Python o JS/TS ni cambia
generated_test.v1. El escritor temporal comprueba contención, componentes de ruta,
enlaces y nombres reservados de Windows antes de crear carpetas. No se escribe
en src/test del proyecto original.

Una respuesta Java que no parsea produce ErrorRespuestaGenerator con su código.
El Reviewer compartido la rechaza antes de llegar al ejecutor, emite error_test y
retry si queda un intento. La prueba comprueba que ese feedback permite generar
un segundo intento con sintaxis corregida y sin cambiar el contrato.

## Validación del primer bloque

```powershell
python -m pytest tests/agents/test_generator_java.py tests/sandbox/test_archivos_prueba.py tests/test_contracts_java_archivos.py -q
```

Resultado: **50 aprobadas en 3.02 s**. Incluye generación real con cliente grabado,
contexto sin cuerpos, paquetes que no coinciden con el directorio, paquete vacío,
constructores con Mockito, booleanos, excepciones, sintaxis, conservación de
contratos anteriores y rutas inválidas. Los JUnit recibidos se conservan sin
evaluar ni ejecutar sus expresiones.

La comprobación conjunta con los adaptadores, Planner, Generator y Reviewer de
Python y los contratos versionados terminó con **323 aprobadas en 8.18 s**. Ruff
check y format --check también aprobaron. Una primera ejecución detectó que
restringir la extensión de los nombres Java antiguos rompía una prueba de
compatibilidad: se preservó la regla anterior para nombres simples y se restringe
la nueva ruta Java a src/test/java y ClaseTest.java. No se cambió ni relajó la
prueba existente.

## Segundo bloque: comparación y oráculo antes de ejecutar

java_aserciones.py reconoce imports y aserciones de JUnit 5 con tree-sitter.
No considera una función cualquiera llamada assertEquals como prueba de JUnit.
Normaliza formato, comentarios, literales numéricos y alias locales estables,
manteniendo sujetos, entradas y valores. Los enteros grandes no se redondean
durante la comparación. Se limitan tamaño, cantidad de nodos y anidamiento.

java_laundering.py compara intentos sin IA. Detecta aserciones eliminadas,
valores esperados cambiados, sustitución de igualdad por assertNotNull o
assertTrue(true), assertThrows eliminado, excepción cambiada y try/catch que
oculte fallos. Cuenta la multiplicidad: copiar una aserción no sustituye otra
eliminada. También se rechazan omisiones, aserciones diferidas y condiciones que
impidan ejecutarlas. Se permiten mensajes nuevos, reordenamiento, comentarios,
alias y lambdas de una llamada expresadas con o sin bloque. Una tolerancia puede
reducirse, pero no aumentarse para aprobar.

java_oraculo.py valida también el primer intento contra el contrato: cada caso
debe tener una aserción que llame al objetivo real con sus entradas y compare el
valor esperado o excepción declarada. No basta con encontrar el mismo literal
en otra comprobación. Se distingue char de String y el contenido de arrays de
su igualdad de identidad; no se admiten coerciones a punto flotante para ocultar
diferencias de enteros. Las tolerancias de float/double están acotadas a la
convención de 1e-6 * max(1, abs(esperado)); no se usa esa tolerancia con enteros.
assertThrows conserva la semántica de subtipos; assertThrowsExactly no se acepta
como sustituto del contrato, que no declara una expectativa de tipo exacto.

El punto compartido validar_oraculo del adaptador permite contrastar además la
clase y el paquete con la fuente, sin añadir condiciones Java al Reviewer.
Python conserva sus reglas actuales. Se comprueban imports que intenten cambiar
el objetivo o una dependencia por un homónimo de otro paquete.

Mockito solo se admite para dependencias de constructores accesibles de la clase
real, en el orden de parámetros declarado. Incluye constructores protected desde
el mismo paquete. Se rechazan mocks/spy del objetivo, mockStatic, mockConstruction,
mocks sin uso como dependencia, tipos inventados y stubs del método probado.
Se permiten stubs when(...).thenReturn/thenThrow únicamente sobre las dependencias.
Los esperados nunca se obtienen de esos stubs ni del cuerpo de producción.

El Reviewer verifica el oráculo, compara con la referencia válida y registra
laundering_detectado en review_result. Un intento rechazado no sustituye la
referencia para el siguiente. También comprueba que el archivo recibido corresponda
al paquete y clase calculados, conservando el nombre simple equivalente de pruebas
anteriores. Estas comprobaciones suceden antes de crear el comando o ejecutar.

### Subconjunto verificable

Este guardrail no pretende resolver todos los tipos y programas Java. Admite
JUnit @Test con instrucciones directas, una aserción por caso, literales,
variables locales de una asignación y construcción del objetivo con sus mocks.
Rechaza helpers, campos, herencia de la clase de prueba, inicializadores, bucles,
condicionales, proveedores de mensajes y operaciones ajenas a los casos. Así no
aprueba una prueba cuya comprobación no puede demostrar estáticamente.

Las expectativas soportadas son números finitos, booleanos, null de referencias,
cadenas/char simples, List y arrays de valores reconocibles. No se evalúan
expresiones arbitrarias o constantes de bibliotecas. Los nombres de rutas e
identificadores del artefacto se restringen al subconjunto portable ASCII y $.
La compilación, resolución completa de tipos y ejecución real siguen en #182.

Los tests del guardrail usan el Generator y Reviewer reales, fuentes estáticas
y respuestas de IA grabadas. Las pruebas de aceptación/reintento que llegan al
runner sustituyen exclusivamente su puerto de ejecución y cobertura de #182:
devuelven JUnit grabado y comprueban el archivo temporal. No reemplazan el
oráculo, el comparador ni el Generator por un doble que apruebe por defecto.

```powershell
python -m pytest tests/lenguajes/test_java_laundering.py tests/lenguajes/test_java_oraculo.py tests/agents/test_reviewer_java_guardrail.py -q
```

Resultado del segundo bloque: **91 aprobadas en 10.94 s**. La comprobación conjunta
con adaptadores, Planner, Generator y Reviewer de Python, rutas y contratos
versionados produjo **414 aprobadas en 13.04 s**. Ruff check, format --check y
git diff --check aprobaron.

Se comprobó además el reintento con Planner, Generator, Reviewer y Orquestador
reales: el cliente grabado entrega primero Java inválido, recibe el feedback y
entrega una corrección. Solo el segundo intento válido llega al puerto de ejecución
simulado. Las pruebas de laundering usan el cliente del Reviewer configurado para
fallar si se invoca IA y un ejecutor configurado para fallar si recibe código
rechazado: ambos permanecen sin llamadas durante el rechazo.

## Estado de la aplicación

El guardrail y sus seis criterios cuentan con pruebas automatizadas. La regresión
general y la comprobación del banco se registran abajo. completo permanece False porque
la ejecución y lectura de JUnit/JaCoCo pertenecen a #182. No se declara Java
operativo desde la aplicación antes de integrar esa parte con esta generación.

## Validación final sobre TA-01

```powershell
python -m pytest tests/agents/test_java_generacion_banco.py -q -s
```

Esta prueba usa el banco original sin modificarlo, Planner y Generator reales,
clientes de IA grabados y el Reviewer real. Para cada uno de sus seis métodos
genera generated_test.v2, valida la ruta y su oráculo y presenta un intento
debilitado. El Reviewer debe rechazarlo sin consultar IA ni llamar al ejecutor.
No se ejecuta ni compila Java y no se afirma detectar aquí el comportamiento
defectuoso: la detección por JUnit durante ejecución corresponde a #182.

| Método | Esperado del contrato | Ruta del artefacto | Guardrail |
|---|---|---|---|
| BancoCorrecto.sumarPrecios | 30 | src/test/java/org/qagent/bench/BancoCorrectoTest.java | Rechaza esperado cambiado |
| BancoCorrecto.aplicarDescuento | 80 | src/test/java/org/qagent/bench/BancoCorrectoTest.java | Rechaza assertNotNull |
| BancoCorrecto.esMayorDeEdad | true | src/test/java/org/qagent/bench/BancoCorrectoTest.java | Rechaza assertTrue(true) |
| BancoDefectuoso.calcularPromedio | 2.5 | src/test/java/org/qagent/bench/BancoDefectuosoTest.java | Rechaza sustituir 2.5 por 2.0 |
| BancoDefectuoso.calcularEnvio | 0 | src/test/java/org/qagent/bench/BancoDefectuosoTest.java | Rechaza sustituir 0 por 10 |
| BancoDefectuoso.calcularTotalConImpuesto | 118 | src/test/java/org/qagent/bench/BancoDefectuosoTest.java | Rechaza sustituir 118 por 82 |

Cada objetivo escribe su test en un temporal independiente: compartir nombre de
clase de prueba entre métodos del mismo archivo no mezcla sus ejecuciones.

La comprobación inicial encontró una diferencia CRLF/LF en la firma multilínea
del impuesto. Se normaliza la lectura de saltos de línea igual que el analizador,
con pruebas explícitas para LF, CRLF y CR. No se cambian esperados ni se elimina la
comprobación de firma. También se comprueba que un error de análisis sin mensaje
no pueda convertirse en aprobación del oráculo.

## Criterios de aceptación y evidencia

| Criterio de #184 | Implementación y comprobación |
|---|---|
| generated_test.v2 con JUnit 5 y Mockito solo para dependencias del constructor | Generator compartido, prompt_java y oráculo; test_generator_java y test_java_oraculo, incluidos mock del objetivo, spy y stubs rechazados. |
| archivo_de_prueba respeta paquete y src/test/java/.../ClaseTest.java | Contexto de fuente por AST, archivo_para_contrato, schema compatible y escritura con ruta_de_prueba. Incluye paquete distinto al directorio y paquetes vacíos. |
| Sintaxis por tree-sitter antes de ejecutar y reintento con feedback | GeneratorAgent + ReviewerAgent + Orquestador reales con primer intento inválido; solo el segundo válido llega al runner simulado. |
| Detección de cada debilitamiento exigido | Matriz de test_java_laundering: eliminación, esperado cambiado, assertNotNull, assertTrue(true), assertThrows eliminado y try/catch. |
| Rechazo como Python y marca laundering_detectado | Reviewer compartido; test_reviewer_java_guardrail comprueba el flag, retry/stalled, ejecutor/IA sin llamadas y referencia válida conservada. |
| Pruebas sin Docker y con IA simulada | Banco TA-01 y pruebas unitarias; no se ejecuta código Java ni se usan proveedores reales. |

La validación general se ejecuta con python test.py -m "not docker and not red".
Su registro completo se guarda fuera de Git en .qagent/validacion-184.txt.
Resultado: lint y formato aprobados; 2667 pruebas aprobadas, 31 deseleccionadas y
dos fallos en tests/analysis/test_texto_ts.py bajo Python 3.10. Son los casos de
dict comprehension comparada con ast.unparse y Generic[*Ts], ya identificados
antes de esta tarea. No se modifican esas pruebas ni sus aserciones.

La comprobación final independiente del banco produjo 6 aprobadas en 6.97 s.
Estos resultados corresponden al entorno de desarrollo del 30 de octubre de 2026.
