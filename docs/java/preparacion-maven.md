# Preparación Maven de proyectos externos (#290)

La apertura de una carpeta y la clonación desde GitHub convergen en la misma
vista previa y el mismo adaptador Java. El origen del proyecto no cambia los
requisitos de construcción. Este documento describe la ampliación de ADR-017;
los informes anteriores de EP-12 conservan el alcance que se validó entonces.

## Comportamiento

- Antes de crear clientes IA se inspeccionan el POM raíz, los padres locales,
  módulos, propiedades Java y las opciones Maven admitidas. Preparar muestra el
  diagnóstico. Un requisito conocido incompatible bloquea el inicio; se puede
  seguir explorando el código.
- Durante la preparación Docker puede descargar padres públicos, dependencias,
  plugins, lanzadores JUnit y recursos declarados por Remote Resources Plugin.
  El POM efectivo se obtiene dentro de Docker. No se compila el proyecto ni se
  ejecutan sus pruebas durante la descarga.
- El contexto de construcción conserva las rutas de los POM necesarios y
  `.mvn/maven.config` validado. También contiene el lector Java propio de QAgent;
  no incluye las fuentes, `.env`, `settings.xml` ni credenciales del proyecto.
- Las dependencias internas se comparan por grupo, artefacto y versión. Solo en
  la copia de descarga se omiten las que se compilarán en el reactor. Las demás
  dependencias se conservan, aunque compartan nombre con un módulo interno.
- La ejecución usa una copia con un reactor reservado `.qagent-maven/`. Compila
  los módulos auxiliares necesarios y ejecuta exclusivamente la prueba generada
  elegida. No ejecuta automáticamente los tests existentes del repositorio.
- Los comandos de prueba siguen siendo offline, en contenedores sin red, con
  límites de CPU, memoria y tiempo. PIT solo muta los métodos críticos elegidos.
- Un fallo al preparar el entorno se distingue de un bug del código. Cuando hay
  log técnico se guarda `entorno.log` en la carpeta de la corrida, acotado a
  512 KiB y con secretos saneados; el mensaje muestra su ruta relativa.

El sandbox sigue usando JDK 25. La versión objetivo declarada por el proyecto
se conserva: el fixture de perfil `compat` compila con `release=17` y su prueba
comprueba que el bytecode resultante tiene versión mayor 61 (Java 17).

## Límites explícitos

No se declara compatibilidad universal con proyectos Maven. Gradle,
`systemPath`, fuentes fuera de `src/main/java`, extensiones Maven y opciones JVM
adicionales requieren trabajo separado. Tampoco se preparan credenciales privadas.
Un BOM interno o un artefacto interno con classifier/tipo distinto de jar requiere
instalación adicional y se rechaza explícitamente.

En `.mvn/maven.config` se admiten perfiles compactos `-P...` y propiedades de
versión `revision`, `changelist`, `sha1`. Otras opciones se rechazan; no se ignoran.
La inspección estática no sustituye al modelo efectivo de Maven ni demuestra que
una biblioteca o plugin arbitrario sea compatible con JDK 25.

La falta de un resultado esperado verificable en métodos Java sin Javadoc es
otro problema. Resolver Maven no convierte esos métodos omitidos en pruebas
aprobadas y no autoriza a inventar el valor esperado leyendo su ejecución.

## Construcción antes de consumir IA (#305)

En Humo, Estándar y Profundo, Java espera a que termine la preparación de la
imagen y comprueba la construcción antes de llamar al Planner o al Generator.
La admisión estática mostrada en Preparar sigue siendo una comprobación inicial;
no equivale a haber compilado. Regresión conserva su flujo sin llamadas de IA.

La comprobación usa una copia del proyecto y su POM original, exclusivamente en
Docker sin red, con los límites de recursos del sandbox:

```text
mvn --offline --batch-mode --no-transfer-progress
    -Dmaven.repo.local=/opt/qagent/m2 -f /work/proyecto/pom.xml
    [-pl <módulos seleccionados> -am]
    -DskipTests=true -Dmaven.test.skip=true -DskipITs=true clean compile
```

En un reactor se incluyen los módulos seleccionados y sus dependencias internas.
No se ejecutan automáticamente sus tests existentes. Los plugins vinculados a
las fases de construcción sí se ejecutan dentro del contenedor. No se sustituyen
versiones de bibliotecas, plugins ni JDK para lograr una compilación aprobada.

Una construcción fallida bloquea el consumo de IA. El Monitor distingue errores
de compilación, dependencias, configuración e incompatibilidad de herramientas;
también comunica cancelación, timeout y otros fallos técnicos. Se conservan
`construccion.json` y `construccion.log` saneado en la carpeta de la corrida.
Un fallo de descarga anterior conserva `entorno.log`.

Solo se reutiliza una aprobación cuya huella coincide con fuentes, recursos,
configuración, scripts, selección, política, ID inmutable de imagen y entorno
Docker/límites. El registro está en `.qagent/cache/construccion_java/`.
Cambiar una dependencia interna o cualquiera de esas entradas invalida la
comprobación. Un fallo, timeout, cancelación o registro corrupto no autoriza IA.
No se certifican todos los perfiles, empaquetados ni el determinismo de plugins
arbitrarios. Véase [ADR-020](../decisiones/ADR-020-construccion-java-antes-de-ia.md).

Las pruebas de esta comprobación, con IA simulada, se ejecutan con:

```powershell
python -m pytest tests/lenguajes/test_issue305_construccion_java.py tests/orchestrator/test_issue305_antes_de_ia.py tests/sandbox/test_issue305_cancelacion.py -q
python -m pytest tests/sandbox/test_issue305_construccion_docker.py --docker -q -s
```

## Comprobaciones reproducibles

### Recursos y análisis por corrida (#308)

Java reutiliza AST de lectura y declaraciones por contenido durante la corrida;
la sesión se libera al terminar. Consultar el rango de un objetivo solo lee su
módulo. Las copias, compilaciones y salidas de cada intento siguen aisladas.
No cambia la política de aprobación de construcción ni las huellas persistentes.

Cada corrida registra `recursos.json` junto a sus resultados: operaciones y
duraciones observadas, estado de la caché y contenedores propios. CPU/RSS y pico
de memoria Docker no medidos se expresan como `null`. Los límites efectivos no
son mediciones de consumo. Las duraciones acumuladas pueden solaparse entre hilos.
Véase [ADR-021](../decisiones/ADR-021-recursos-y-analisis-java-por-corrida.md).

Para reproducir los escenarios, desde la raíz del repositorio, con IA simulada
y un directorio de evidencia externo nuevo:

```powershell
python scripts/medir_java_estatico.py medicion --salida C:/ruta/evidencias-java
python scripts/medir_java_docker.py medicion --salida C:/ruta/evidencias-java
```

El primero no ejecuta fuentes. El segundo requiere la receta Java vigente ya
preparada y ejecuta Maven/JUnit sin red en Docker; usa fixtures y proveedores
grabados de `tests/`, por lo que es una herramienta del checkout de desarrollo.
No llama a una API de IA. Separa tiempos, archivos/objetivos, parseos,
declaraciones, copias, compilaciones observadas y veredictos. Para comparar con
`fc3ad6f`, copia los scripts fuera del checkout y ejecútalos contra cada revisión
con `PYTHONPATH` apuntando a su `src`, usando un directorio de salida nuevo para
cada muestra. Conserva la misma imagen, selección y límites. Una pareja de
muestras no es una matriz de compatibilidad externa ni una garantía de latencia.
La matriz externa está en [matriz-compatibilidad.md](matriz-compatibilidad.md) (#309).

Con el entorno virtual activo y Docker Desktop abierto:

```powershell
python -m pytest tests/sandbox/test_issue290_dependencias_docker.py tests/sandbox/test_issue290_pit_maven_docker.py --docker -q -s
```

Son tres comprobaciones: padre Apache 35 con Commons Lang 3.17.0, reactor con
dependencia pública y mutación aislada en el módulo seleccionado. El padre Apache
expuso el recurso heredado `apache-jar-resource-bundle:1.7` que faltaba offline;
la prueba conserva ese padre después de la corrección. No se utiliza IA real.

Para volver a comprobar los perfiles existentes, preparar primero las imágenes:

```powershell
python -c "from pathlib import Path; from qagent.sandbox.imagen import preparar_imagen; from qagent.sandbox.modelos import IMAGEN_JAVA; [preparar_imagen(Path(ruta), imagen=IMAGEN_JAVA, avanzar=print) for ruta in ('bench_java', 'bench_java/src/test/resources/spring')]"
python -m pytest tests/sandbox/test_issue262_perfiles_java_docker.py tests/sandbox/test_ep174_java_integrado_docker.py tests/sandbox/test_pit_corrida_docker.py tests/sandbox/test_spring_corrida_docker.py --docker -q -s
```

La segunda orden comprueba Humo, Estándar, Regresión, Profundo/PIT y Spring
MockMvc con los bancos anteriores. Es una comprobación adicional de regresión;
no sustituye los fixtures externos ni una comprobación visual de la aplicación.
