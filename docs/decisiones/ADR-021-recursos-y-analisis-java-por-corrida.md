# ADR-021: Reutilizar análisis Java y medir recursos por corrida

- Fecha: 2026-11-21.
- Estado: Propuesta implementada para revisión mediante PR.
- Issue: #308; épica histórica EP-12 (#174), sin reabrirla.
- Relacionados: ADR-007/008/009, ADR-017/018/019/020; #305 y #307.

## Problema y medición inicial

La consulta del rango de un método ejecutaba `JavaAdapter.analizar` sobre todo el
proyecto por intento. Generación, validación del oráculo, archivo de prueba y
huellas también volvían a parsear las mismas fuentes. En la base `fc3ad6f`, una
fixture estática de 12 archivos y 96 métodos requirió 1560 parseos y 1464
extracciones de declaraciones. El escenario estático completo tardó 32,388591 s
con tracemalloc activado; no es una medición de ejecución Maven ni de RSS.

Una corrida Docker grabada de ocho archivos, 32 objetivos disponibles y tres
seleccionados observó 64 parseos, 52 extracciones, cinco copias, cuatro
contenedores y siete compilaciones javac reconocibles en sus logs. No se propone
un porcentaje objetivo ni se generaliza ese tiempo a proyectos externos.

## Decisión

El adaptador Java abre una sesión explícita por corrida. Los otros adaptadores
conservan su comportamiento. La sesión se transmite a cada hilo de agente mediante
una copia de ContextVar; no reside en el registro global de adaptadores ni en un
directorio persistente. No modifica decisiones del orquestador ni contratos del
Planner/Generator.

Se comparte únicamente el AST de lectura y las declaraciones derivadas del
contenido exacto de la fuente actual. La clave es SHA-256 del texto normalizado
para análisis, no mtime, ruta, nombre de método o firma. Cada acceso sigue leyendo
y validando la ruta actual; paquete, selección, contexto y evidencia del contrato
se comprueban como antes. Las huellas persistentes de specs/PIT no cambian.
Esta caché no resuelve la ampliación de invalidación de contratos de #307.

Las declaraciones se entregan como copias independientes, porque el análisis
añade `llama_a`. El árbol se conserva bajo una interfaz de lectura con su
propietario original. No se usa `Tree.copy`, que produjo un fallo nativo de
Node.text en el entorno Windows/tree-sitter 0.24 de esta revisión. Los parsers
se crean por cálculo; no se comparte un Parser entre hilos.

La caché LRU tiene como máximo 32 entradas y 4 000 000 bytes de payload retenido
(fuente y declaraciones serializadas). Ese límite no representa un límite de RSS
ni mide la memoria nativa del AST. Al superar el límite se expulsa una entrada o
no se retiene la fuente; no se rechaza el objetivo por ello. Un lock por sesión
evita cálculos duplicados concurrentes. El cierre libera todas las entradas y
congela los contadores; los trabajadores tardíos no pueden reabrirla ni modificar
las mediciones cerradas.

El rango se obtiene de la declaración inequívoca del archivo seleccionado, sin
reconstruir el grafo global. Conserva clase/firma de sobrecargas y métodos anidados.
La inferencia conserva sus topes y su clasificación de regresión/hallazgo a revisar;
se reutiliza su índice de métodos y se explicita el límite que impidió obtener
evidencia. No se amplía a endpoints Spring.

## Artefactos que permanecen aislados

Cada intento conserva su copia de proyecto, tests, POM adaptado, directorios de
compilación y salidas JUnit/JaCoCo/PIT. No se comparten directorios escribibles,
hardlinks, clases compiladas ni veredictos entre objetivos o corridas. Los plugins
y los tests pueden alterar su copia; compartirla contaminaría los intentos.
La precompilación/cache de aprobación de ADR-020 mantiene su propia política.

Esta entrega reduce análisis redundante; no afirma reducir copias ni compilaciones.
Mantiene los límites Docker, presupuestos de tokens/USD y preparación de imágenes.
No se añaden dependencias ni se elevan límites de contexto/inferencia.

## Cancelación, limpieza y diagnóstico

Los contenedores heredan la consulta de cancelación de su sesión. Su cierre solo
retira contenedores que registró esa corrida, incluyendo una creación tardía;
nunca realiza limpieza global. Un error de limpieza se conserva en el registro y
se avisa si quedan recursos pendientes. Cada sandbox conserva además su `finally`
para eliminar su contenedor y copia temporal. Corridas concurrentes no comparten
cancelación ni propiedad de recursos.

Una cancelación durante el último objetivo se comunica como cancelación, no como
fin ni bug. Se añade el motivo `corrida_cancelada` al enum de `run_log` y su texto
de interfaz, manteniendo la interpretación de los registros anteriores. No se
cambian aserciones ni se deducen esperados de la ejecución.

`recursos.json` versionado, separado de las métricas de calidad, conserva
contadores y duración acumulada de parseos, declaraciones, copias e invocaciones
de sandbox; creaciones/eliminaciones propias; límites efectivos; y fases/compilaciones
que aparecen en logs. Los tiempos concurrentes son acumulados y no se suman como
tiempo de pared. Las compilaciones reconocidas son observaciones del log, no una
equivalencia entre una fase Maven y una ejecución javac. RSS, memoria/CPU Docker
y tiempo de descarga no medidos se representan como null, nunca como cero.
La ausencia de cobertura sigue siendo null y no una aprobación.

## Validación y límites

Se comparan antes/después con las mismas fuentes, selección, imagen y límites;
los resultados/huellas deben coincidir. El caso estático y el de Docker tienen
alcances diferentes y no se mezclan sus tiempos. Se conservan pruebas de
invalidación, concurrencia, cancelación, limpieza y originales intactos. Una
medición individual por escenario no constituye un objetivo de rendimiento ni
una caracterización estadística de proyectos grandes externos (#309).
