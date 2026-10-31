# Mutación con PIT de métodos críticos Java (#180)

## Comportamiento

El adaptador Java ofrece `comando_mutacion` y `ejecutar_mutacion`. El orquestador
común conserva la selección: solo métodos `critical: true` con prueba aprobada
en Profundo o regresión profunda. Los métodos no críticos y las pruebas rechazadas
quedan fuera. El motor no llama a un LLM.

`pit_comando.py` construye argumentos separados de Maven, sin shell. La clase
se fija exactamente mediante `targetClasses` y se excluyen los nombres de métodos
no seleccionados mediante `excludedMethods`. PIT admite expresiones regulares
con prefijo `~`. Se usa el nombre del método porque el filtro estándar no distingue
sobrecargas: estas se rechazan antes de ejecutar. El XML se vuelve a contrastar
con los pares exactos clase/método; un resultado fuera de selección es un error.

## Ejecución y configuración

`pit_ejecucion.py` copia el proyecto y delega en `ejecutar_en_sandbox`. El sandbox
común aplica red deshabilitada, raíz de solo lectura, límites de CPU/memoria,
restricciones de procesos y limpieza de contenedores. Java y Maven se ejecutan
exclusivamente dentro de `qagent-sandbox:java`.

`pit_preparacion.py` crea `.qagent-pit.xml`, `.qagent-pit-tests` y un directorio
de compilación `.qagent-pit-target` en la copia desechable. Reubica las pruebas
aprobadas según su paquete y clase Java, incluso cuando entran con los nombres
hash del almacén común. Las salidas de compilación se separan para no reutilizar
clases o pruebas antiguas. No cambia el POM original ni `src/test`.

Una declaración `pitest-maven` en el POM, incluidos perfiles y pluginManagement,
o una referencia a `pitest` en los scripts Gradle examinados produce
`config_propia`: QAgent conserva esa configuración y omite su ejecución automática.
Los archivos reservados preexistentes también se rechazan.

Las versiones se toman de la receta compartida
`src/qagent/sandbox/java/calentamiento/pom.xml`: PIT 1.30.1 y
pitest-junit5-plugin 1.2.3. La imagen usa JDK 25, Maven 3.9.16 y Gradle 9.8.2.
El proyecto de integración usa JUnit 5.14.4, ya preparado por la imagen.
Maven se ejecuta offline y usa `/opt/qagent/m2`; dependencias ausentes son un
error técnico. No se habilita red como respaldo.

Sin límites explícitos, se usan `[sandbox.java]` de `config.toml` (4 CPU,
4 GB, 300 s). El tiempo de mutación se limita adicionalmente a
`[mutacion].tiempo_maximo_por_funcion_s` (120 s) multiplicado por la cantidad
de métodos distintos seleccionados. Si el llamador fija un límite menor, se
respeta. El sandbox puede ajustar CPU a la disponibilidad de Docker. Los 4 GB
son un límite configurado; esta tarea no afirma haber medido el pico de RAM.

## Resultados y reutilización

`pit.py` convierte `mutations.xml` en `ResultadoMutacion`, sin crear un contrato
alternativo. Usa la función común `puntuacion`:

```text
detectados / (detectados + sobrevivientes) * 100
```

`KILLED` y `TIMED_OUT` cuentan como detectados; `SURVIVED` y `NO_COVERAGE`
como sobrevivientes. Los estados técnicos incompletos, timeout del contenedor,
OOM, Maven con salida no cero o XML inválido no reciben score. Un informe sin
mutantes evaluables tampoco se convierte en un 100 %.

Se conserva el cambio, la línea y el identificador de los sobrevivientes.
La serialización común los incorpora a `results.json`, la vista de Resultados
y el informe PDF; el Markdown conserva el score con el mismo formato que Python.
Las pruebas de integración del almacenamiento usan el XML real grabado y simulan
la llamada Docker; no equivalen a una corrida completa de la aplicación.

`JavaAdapter.huellas_de_archivo` calcula huellas SHA-256 por objetivo con contexto
conservador: incluyen ruta, nombre y fuente completa. También invalidan la caché
cambios en imports, campos, auxiliares o comentarios del archivo. Esto puede
repetir trabajo, pero evita reutilizar un score con contexto distinto. La caché
existente de #70 compara además el código de todas las pruebas aprobadas usadas
en el módulo. Sin cambios devuelve el score, `reutilizada` y `run_origen`.
Los errores sin score no se guardan como resultados reutilizables.

La capacidad `huellas_disponibles` permite al recolector común obtener estas
huellas sin marcar completo un adaptador todavía en desarrollo.

## Evidencia y reproducción

Desde la raíz de QAgent, con el entorno virtual activo:

```powershell
docker build -t qagent-sandbox:java -f src/qagent/sandbox/Dockerfile.java src/qagent/sandbox
python -m pytest tests/sandbox/test_pit_docker.py -q -s
python -m pytest tests/sandbox/test_pit_interpretacion.py tests/sandbox/test_pit_comando.py tests/sandbox/test_pit_preparacion.py tests/sandbox/test_pit_ejecucion.py tests/lenguajes/test_java_huellas.py tests/orchestrator/test_pit_cache_resultados.py -q
python test.py -m "not docker and not red"
```

La construcción de la imagen requiere descargas; la prueba PIT usa el contenedor
sin red. El test real está marcado `pytest.mark.docker`; si falta Docker o la
imagen, se omite y esa omisión no constituye una validación real.

La validación inicial del 30/10/2026 produjo cinco mutantes exclusivamente en
`Criticos.critico`: tres detectados y dos sobrevivientes, 60 %. Duró 18.031 s
en la primera ejecución satisfactoria; la repetición del integrante duró 19.703 s.
El segundo método de la clase quedó fuera de la mutación. El POM y la fuente
originales no cambiaron. El XML versionado está en
`tests/fixtures/pit/critico-real.xml` y se puede interpretar sin Docker.

La validación conjunta de PIT sin Docker, adaptadores y caché produjo **184
pruebas aprobadas**. La revisión general con Python 3.10 produjo **2392 aprobadas,
32 deseleccionadas y dos fallos**; lint y formato pasaron. Los dos fallos son
casos de `tests/analysis/test_texto_ts.py`: el desempaquetado de tuplas en una
comprensión de diccionario tiene paréntesis distintos en `ast.unparse`, y
`Generic[*Ts]` no es aceptado por `ast.parse` en Python 3.10. Se reprodujeron
ambos en una copia temporal del commit base `6d761ce` (**48 aprobadas y dos
fallos** en ese archivo), sin los cambios de #180. No se modificaron ni se
omitieron esas aserciones. Esta evidencia es histórica: #214 ya corrigió ambos
casos y está integrado en la actualización descrita a continuación.

## Actualización tras integrar #184 (31/10/2026)

Se incorporó `origin/develop` en la misma rama `feat/180-mutacion-pit-java`,
incluyendo #181, #184 y #214. Se resolvió el conflicto de `java.py` conservando
análisis, planificación, generación, validación del oráculo y guardrail junto con
las operaciones de mutación. No se sustituyó un lado completo por el otro.

La revisión reprodujo y corrigió dos problemas de integración:

- #184 genera artefactos por objetivo que pueden compartir `ClaseTest`.
  La preparación PIT rechazaba esa entrada por clase duplicada. Ahora conserva
  todos los artefactos y asigna nombres únicos solo a las declaraciones duplicadas
  dentro de la copia temporal. No cambia cuerpos, aserciones, comentarios, cadenas
  ni archivos originales. Una referencia al nombre propio de una clase duplicada
  se rechaza para no transformar tipos o llamadas por conjetura.
- La regresión profunda entregaba los límites generales del sandbox a la mutación.
  Ahora consulta el lenguaje del contrato y usa `limites_del_lenguaje`, como la
  corrida común: Java recibe los 4 GB configurados y el motor PIT mantiene el tope
  temporal de `[mutacion]`. No se introduce lógica Java en el orquestador.

Se añadieron cuatro regresiones sin Docker: clases duplicadas, conservación de
comentarios y cadenas con Unicode, rechazo de referencias ambiguas y límites por
lenguaje al profundizar pruebas guardadas. La comprobación focalizada produjo
**337 aprobadas en 12.50 s**, incluidos los tests de generación y guardrail de #184.

El test real Docker usa ahora el Generator productivo con un cliente grabado y
valida ambos artefactos con el oráculo real de #184 antes de entregarlos a PIT.
Los dos artefactos tienen el mismo nombre de clase original. Maven/PIT compilan y
evalúan exclusivamente dentro del sandbox, sin red. Resultado: **1 aprobada en
24.96 s**, cinco mutantes de `Criticos.critico`, tres detectados, dos sobrevivientes,
**60 %** y 22.422 s dentro del sandbox. `noCritico`, el POM y la fuente original
conservaron sus verificaciones; no se relajaron las aserciones existentes.

| Criterio de #180 | Evidencia actual |
|---|---|
| Comando limitado a clase y métodos críticos aprobados | test_pit_comando; selección común; test Docker comprueba clase y método de cada mutante. |
| XML a ResultadoMutacion y fórmula común | test_pit_interpretacion y XML real versionado; puntuacion compartida. |
| Tiempo de mutación y memoria Java | test_pit_ejecucion y nueva regresión de límites al profundizar. |
| Configuración PIT propia intacta | test_pit_preparacion comprueba POM directo, perfiles y scripts Gradle; no añade ejecución Gradle. |
| Reutilización por huella de método y pruebas | test_java_huellas y test_pit_cache_resultados; invalidación al cambiar código o prueba. |
| Score y sobrevivientes en results.json e informe | test_pit_cache_resultados comprueba persistencia, vista y exportación PDF. |
| Pruebas sin Docker, XML grabado y ejecución real marcada docker | 337 aprobadas sin Docker y test_pit_docker aprobado con generación/oráculo de #184. |

Registro local de la regresión general: `.qagent/validacion-180-actualizada.txt`,
ignorado por Git. Resultado definitivo: **2738 aprobadas, 32 deseleccionadas,
ningún fallo**, en 195.69 s; lint y formato aprobados. Se ejecutó con Python 3.10.10,
IA simulada, `GIT_CEILING_DIRECTORIES` apuntando a TEMP y selección
`not docker and not red`. Los dos fallos históricos ya no aparecen tras integrar #214.

## Límites de esta entrega y dependencias

La ejecución admite proyectos Maven de un módulo sin POM padre, con fuente en
`src/main/java/paquete/Clase.java` y una sola clase superior inequívoca. No resuelve
Gradle, herencia Maven, proyectos multimódulo, clases anidadas ni sobrecargas;
los rechaza con motivo explícito. No muta endpoints Spring.

`JavaAdapter.completo` sigue siendo `False`: #184 ya está integrada y su generación
y oráculo se usan en la prueba PIT real. La ejecución JUnit/JaCoCo y la revisión
del flujo Java completo desde la aplicación corresponden a #182, que se revisará
por separado. Esta actualización no incorpora su rama ni declara completada
EP-12a. El PR #213 conserva el alcance de mutación y queda sujeto a la revisión
del equipo y al orden de dependencias de la épica.
