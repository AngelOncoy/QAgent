# ADR-023: Vigencia Java por dependencias, evidencia y entorno

- Fecha: 2026-11-21.
- Estado: Propuesta implementada para revisión mediante PR.
- Issue: #307. Épica histórica EP-12 (#174), sin reabrirla.
- Relacionados: ADR-007/008/009, ADR-017/018/019/020/021/022.

## Problema

La huella de A.java no cambia al modificar B.g(), un llamador o un test usado
como evidencia. Comparar solo esa huella permite conservar un contrato inferido
que ya no representa el contexto actual. El score de PIT tampoco puede atribuirse
a una ejecución con dependencias, pruebas, imagen o configuración diferentes.

## Decisión

El adaptador declara `requiere_claves_reutilizacion` y produce un snapshot de
metadatos de versión 1. El orquestador y almacenamiento comparan las claves sin
implementar reglas Java. Los otros adaptadores conservan su política. No cambia
la huella del módulo ni la del archivo/objetivo existente, ni se cambia un contrato
entre agentes: los metadatos son envoltorios del almacenamiento.

| Clave | Entradas relevantes | Consumidor |
|---|---|---|
| spec | Fuente completa, componente de dependencias, evidencia de inferencia, descriptores y recursos Maven, receta y política del adaptador, configuración de inferencia pertinente | Plan modular por objetivo |
| pruebas | spec y límites efectivos de ejecución | Pruebas aprobadas/repetición |
| mutacion | pruebas y configuración de mutación | Caché de PIT, además de sus huellas existentes de objetivo y tests |
| entorno | ID inmutable de la imagen comprobada/preparada | Repetición de pruebas y PIT |

El grafo estático usa tree-sitter, declaraciones de tipos, identificadores y
imports comodín. Los enlaces son bidireccionales y a nivel de archivo: se toma
la componente conexa, no se afirma resolución exacta de despacho Java. Esto
incluye ciclos, herencia, tipos con nombres ambiguos y dependencias transitivas,
invalidando conservadoramente también llamadores y archivos relacionados. Los
archivos de componentes desconectadas conservan sus claves. Una señal de carga
dinámica/reflexión conecta conservadoramente el contexto completo.

Para métodos sin Javadoc la componente puede incluir tests existentes y helpers:
se incluyen sus bytes completos, rutas y adiciones/borrados. Para métodos con
contrato documentado no se usa el contenido de tests como evidencia de su
esperado. Se mantienen procedencia y referencias del caso inferido tal cual.
El significado sigue siendo regresión/hallazgo a revisar, sin ampliar inferencia
a endpoints Spring. La búsqueda de evidencia sigue bajo ADR-018; esta política
de invalidación puede abarcar más fuentes que las enviadas al LLM.

Los POM, opciones Maven y recursos se incluyen conservadoramente para todo el
proyecto; no se deduce qué plugin o recurso afecta a un método. La receta y la
implementación de la política se identifican por contenido. No se almacenan
claves, cuerpos ni configuración secreta: solo huellas y el identificador de
imagen. Precios y presupuesto no son evidencia funcional de un contrato.

El snapshot se captura después de la preparación y precompilación, antes del
Planner, sobre fuentes que coincidan con el módulo analizado. Se guarda ese
snapshot, evitando certificar un contrato anterior con huellas calculadas después
de que sus fuentes cambien. Al combinar planes solo se conservan contratos cuya
clave actual se comprobó; no se renueva metadatos de objetivos obsoletos omitidos
por la selección. Una parte válida del módulo se conserva al replanificar la
parte faltante.

La regresión compara primero contenido/configuración y luego la identidad real
de la imagen preparada, antes de ejecutar el test. Un cambio requiere corrida
nueva; no se toma un resultado anterior como una medición actual.

## Registros anteriores y límites

La versión de claves es independiente de VERSION_HUELLA_OBJETIVO. Un registro
Java sin metadatos completos, de versión desconocida o sin imagen comprobable
es legible pero no reutilizable donde se exige esa información. No se infieren
huellas o referencias pasadas ni se migran retrospectivamente las huellas Java.
Los resultados de corridas anteriores permanecen intactos.

La lectura tiene límites explícitos (300 archivos, 200 000 bytes por archivo y
4 000 000 bytes acumulados), no incrementa los topes de inferencia, IA o Docker.
Un enlace, lectura fallida, sintaxis inválida o exceso de límite hace que no se
emitan claves reutilizables; no detiene el análisis/ejecución autorizados ni
presenta cobertura ausente como cero. Los directorios generados y .qagent quedan
fuera del inventario. La política puede rechazar reutilización de más: no promete
resolver dinámicamente Java ni ofrecer una mejora porcentual de rendimiento.

## Validación

La issue incluye reproducción A.f → B.g, cambios transitivos, ciclos, cambios y
borrado de evidencia, cambios Maven/receta/configuración/imagen y control sin
cambios. Se verifica conservación de componentes desconectadas, registros
anteriores intactos y flujo productivo con IA grabada. Toda ejecución de fuentes
y tests generados permanece en Docker; los esperados se declaran en fixtures y
evidencia estática, nunca se deducen ejecutando la implementación.
