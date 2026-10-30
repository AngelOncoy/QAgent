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

La ejecución real del 30/10/2026 produjo cinco mutantes exclusivamente en
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
omitieron esas aserciones. El equipo debe tratar esta compatibilidad por separado.

## Límites de esta entrega y dependencias

La ejecución admite proyectos Maven de un módulo sin POM padre, con fuente en
`src/main/java/paquete/Clase.java` y una sola clase superior inequívoca. No resuelve
Gradle, herencia Maven, proyectos multimódulo, clases anidadas ni sobrecargas;
los rechaza con motivo explícito. No muta endpoints Spring.

`JavaAdapter.completo` sigue siendo `False`: no se declara operativa la generación
y revisión JUnit de extremo a extremo. La conexión final desde una corrida Java
de la aplicación requiere completar los prerrequisitos de EP-12a, especialmente
#184. No se debe cerrar #180 como soporte integral en la aplicación mientras esa
dependencia y la revisión del equipo no estén resueltas. El cambio deja probados
PIT real y la conexión de su resultado con los componentes comunes.
