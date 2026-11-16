# ADR-018: Regresión Java sin Javadoc con evidencia estática

- Fecha: 2026-11-16.
- Issue: #292.
- Estado: Implementado y comprobado en la aplicación con proveedor real.
- Base: ADR-016 y adaptadores por lenguaje (ADR-007).

## Decisión

Ampliar a métodos Java la inferencia estática de ADR-016. Solo se intenta para
objetivos sin Javadoc que el paso de contrato documentado no pudo planificar.
Java proporciona su lector tree-sitter y sus validaciones mediante el adaptador;
el orquestador mantiene el flujo común y determinista.

Un caso inferido conserva `origen: inferido` y una lista no vacía de referencias
a fuentes realmente entregadas al Planner. El contrato no necesita un nuevo
origen ni una versión incompatible. El Generator utiliza las entradas y el
resultado del contrato; el oráculo de JUnit continúa verificando sus aserciones.

Las fuentes son el cuerpo del método, firmas/documentación de dependencias
resueltas por `llama_a`, llamadores conocidos y pruebas Java existentes que
invocan la clase y método seleccionados. Se excluyen sobrecargas ambiguas,
enlaces y fuentes fuera del proyecto. Leer una prueba no autoriza a ejecutarla.
Los índices son perezosos, reutilizados por corrida y acotados por archivos,
bytes y caracteres. El contexto total respeta la configuración de inferencia.

No se calculan valores ejecutando Java ni importando el proyecto. El modelo no
debe inventar valores que dependan del reloj, azar, red, archivos, servicios o
estado no descrito. Si no hay evidencia suficiente, se mantiene la omisión.

## Presentación y perfiles

Los casos inferidos se presentan como regresión sin contrato documentado, con
sus referencias. Un fallo es un hallazgo a revisar, no una demostración de
incumplimiento de una especificación independiente. Se reutilizan las etiquetas
y el desglose de respaldo existentes; las pruebas documentadas conservan su flujo.

Humo conserva un caso normal por método. Estándar admite solo casos que superan
los filtros de evidencia y tipos. Regresión preserva la procedencia al guardar
y repetir. Profundo puede medir PIT en críticas aprobadas: su puntuación mide
la fuerza de la regresión inferida, no convierte su oráculo en documentación.

Se reutilizan los controles `[inferencia]` y la revisión opcional de contratos.
La capacidad se declara por adaptador para mostrar los controles también en
Java y conservar el comportamiento de Python.

## Límites

No amplía la inferencia a endpoints Spring, ni corrige sus IDs, ni modifica la
preparación Maven (#290) o la etiqueta de lenguaje del PDF. No incorpora stubs
arbitrarios, servicios reales ni Gradle. No promete que todo método pueda probarse.
Los proyectos y sus pruebas originales se conservan intactos.

## Validación

Se verifican lectura estática, referencias, límites, configuración, rechazo de
evidencia inventada, tipos Java y conservación del flujo documentado. La interfaz
y los exportadores diferencian hallazgos inferidos de posibles bugs con contrato.

Tres casos reales en Docker cubren Humo, Estándar con una expectativa inferida
deliberadamente incorrecta y Profundo con PIT. Las regresiones guardadas conservan
el origen y reutilizan la medición cuando corresponde. La IA de estas pruebas es
grabada: no consume tokens reales. No ejecutan Java en el anfitrión ni modifican
los originales.

`bench_java/src/test/resources/sin_javadoc` permite abrir otro proyecto independiente
desde la aplicación. La comprobación manual con un proveedor real se registra
por separado de las pruebas automatizadas. El soporte Maven de #290 sigue siendo
una tarea independiente y no se incorpora a esta rama.

El 16 de noviembre se comprobó manualmente Humo desde la aplicación con ese
proyecto: `Calculos.sumar` y `Calculos.doble` pasaron, y `Calculos.momentoActual`
quedó omitido. El detalle mostró «Regresión · contrato inferido», las referencias
`cuerpo` y al test existente de `CalculosTest`, y una aserción de `sumar(2, 3) == 5`.
Esta comprobación no equivale a garantizar la inferencia de cualquier método.

La revisión general sin Docker ni red obtuvo 4.009 aprobadas, dos omitidas,
73 deseleccionadas y un fallo en
`test_issue267_limpieza_disco.py::test_sin_limites_configurados_no_se_aplica_el_tope`.
El mismo fallo se reprodujo en una copia limpia del commit base `90dc2bf`,
cargando sus propios módulos: la fecha fija de la imagen simulada ya supera
el umbral de 30 días. No se modificó esa prueba ni la política de limpieza en
esta issue. Lint y formato pasaron; las 34 pruebas específicas, las 312 de
interfaz y los tres casos Docker descritos también pasaron.
