# EN-19 (#132) — Propuesta de sandbox Java

## Estado y alcance

Propuesta técnica para el prototipo Java. No hay una imagen Java construida o
validada por esta tarea, ni se ha comprobado la ejecución Docker sin red.
El adaptador todavía no implementa `comando_pruebas()` ni `entorno_sandbox()`:
siguen lanzando `NoImplementado`. No se modifica el sandbox Python.

La issue permite entregar una propuesta y dejar la validación Docker para una
tarea posterior. La ejecución local observada corresponde únicamente al banco
conocido TA-01; no habilita ejecutar proyectos de terceros en el equipo anfitrión.

## Herramientas y requisitos observados

| Componente | Versión utilizada | Función |
|---|---|---|
| Windows | 11, amd64 | Equipo donde se ejecutó el banco |
| Python | 3.10, entorno `.venv` | Adaptador y pruebas pytest |
| tree-sitter | 0.24.0 | Parser integrado en Python |
| tree-sitter-java | 0.23.5 | Gramática Java |
| JDK | Eclipse Temurin 21.0.7 | Compilar y ejecutar Java |
| Maven | 3.10.0 | Resolver dependencias y lanzar JUnit |
| JUnit Jupiter | 5.11.4 | Pruebas del banco |
| Maven Compiler Plugin | 3.13.0 | Compilación con `release` 21 |
| Maven Surefire Plugin | 3.5.2 | Ejecución y generación de JUnit XML |

El análisis estático solo necesita Python y sus dependencias, no la JVM.
La ejecución necesita JDK y Maven; un JRE sin compilador no basta.
Se necesita red para descargar dependencias nuevas durante la preparación.
No se registraron memoria pico ni uso de CPU de los procesos Java; no se afirma
un mínimo de RAM medido ni se extrapola el rendimiento a otros proyectos.

## Mediciones locales observadas

Comando ejecutado desde la raíz de QAgent:

```powershell
mvn -f bench_java/pom.xml clean test
```

| Medición | Resultado |
|---|---|
| Total registrado por Maven | 9.836 s |
| Suite BancoCorrectoTest | 8 aprobadas; 0.111 s |
| Suite BancoDefectuosoTest | 3 detecciones controladas aprobadas; 0.016 s |
| Total JUnit | 11; 0 fallos; 0 errores; 0 omitidas |
| Estado de Maven | BUILD SUCCESS |

Las duraciones de suites no incluyen todas las fases de compilación, limpieza
y arranque de Maven. Son observaciones de una corrida local con dependencias
disponibles; no constituyen una comparación de rendimiento ni cifras de Docker.

## Diseño propuesto

### 1. Preparación con red, separada de la ejecución

- Elegir una imagen Linux de confianza con JDK 21 y Maven. Verificar la etiqueta
  disponible y registrar su digest, arquitectura y versiones antes de usarla.
- Preparar una imagen derivada con las dependencias y plugins del POM, sin claves
  ni archivos personales. No montar `.m2` completo del anfitrión, `settings.xml`
  personal, el directorio del usuario ni el socket de Docker.
- Resolver dependencias con un objetivo versionado como
  `org.apache.maven.plugins:maven-dependency-plugin:3.11.0:go-offline` dentro del
  contenedor de preparación. Esto no demuestra por sí solo que la corrida final
  pueda funcionar offline: hay que comprobar plugins, proveedores y perfiles.
- Los POM, extensiones y plugins pueden ejecutar código. La preparación de
  proyectos ajenos también debe estar aislada y limitada; no usar Maven sobre
  ellos directamente en el anfitrión.
- Usar el mismo repositorio Maven preparado en la fase de ejecución. Registrar
  el POM, sus versiones y la huella de la imagen para poder reproducirla.

### 2. Ejecución sin red

Propuesta de parámetros iniciales; no son límites validados empíricamente:

| Parámetro | Propuesta | Propósito |
|---|---|---|
| Red | `--network none` | Impedir conexiones externas del contenedor |
| CPU | `--cpus 2` | Limitar consumo de CPU |
| Memoria | `--memory 2g --memory-swap 2g` | Limitar memoria y evitar swap adicional |
| Procesos | `--pids-limit 256` | Acotar procesos e hilos; validar con la JVM |
| Usuario | UID/GID no privilegiados | Ejecutar sin root |
| Privilegios | `--cap-drop ALL --security-opt no-new-privileges` | Reducir permisos |
| Sistema base | `--read-only` | Evitar escritura sobre la imagen |
| Tiempo máximo | 120 s, controlado por el runner | Detener ejecuciones bloqueadas |
| Salida y temporal | Espacios escribibles con cuotas por definir | Compilados, XML y temporales |

El runner debe copiar las fuentes a un área efímera escribible, preparar un
`target` vacío y proporcionar el repositorio Maven ya resuelto. Debe permitir
las escrituras requeridas por Maven sin exponer archivos personales. El acceso
a disco y el tamaño de informes también requieren límites y limpieza.

Comando **propuesto**, dentro del área del proyecto en ese contenedor:

```text
mvn --offline --batch-mode -Dmaven.repo.local=/work/m2 clean test
```

`--offline` limita Maven; el bloqueo de red lo impone Docker. No usar
`--fail-never`, `maven.test.failure.ignore`, `skipTests` ni otras opciones que
oculten fallos. El proceso padre debe conservar el código de salida, distinguir
timeout y falta de memoria, recoger informes antes de eliminar el contenedor
y limpiarlo incluso ante cancelación. No se propone integrar aún este runner
al orquestador ni ejecutar código generado.

### 3. Interpretación de resultados

Surefire genera `target/surefire-reports/TEST-*.xml`. Leer todos los informes de
la corrida en orden, una sola vez, sin mezclar archivos viejos o totales agregados.
El runner debe rechazar una corrida sin informes cuando se esperaban pruebas.

`JavaAdapter.interpretar_resultados()` recibe el contenido de cada XML y lo
convierte al formato común de EN-17. El lector no cambia el veredicto ni ignora
el código de salida del proceso: una compilación fallida puede no producir XML.
Los errores de preparación, compilación, timeout, OOM y lectura se registran
aparte de los resultados JUnit. Las pruebas controladas de defectos del banco
aparecen aprobadas porque así las registra JUnit.

## Validación que falta antes de declarar operativo el sandbox

1. Construir la imagen y registrar digest, versiones y dependencias.
2. Ejecutar TA-01 desde una carpeta limpia con `--network none` y Maven offline.
3. Confirmar 11 casos y extraer los dos informes XML antes de la limpieza.
4. Comprobar mediante una prueba controlada que la conexión externa falla.
5. Provocar dependencia ausente, error de compilación, fallo de aserción y error
   técnico; comprobar que no se confunden con ejecuciones satisfactorias.
6. Verificar límites de tiempo, CPU, memoria, procesos y escrituras; medir sus
   valores reales y ajustar la propuesta en función de los resultados.
7. Integrar los puntos de extensión del adaptador y el runner con pruebas de
   regresión Python. Validar empaquetado y permisos en Docker Desktop.

EN-19 documenta estos pasos; no afirma que ya se hayan ejecutado.

## Referencias oficiales

- [Restricciones de recursos Docker](https://docs.docker.com/engine/containers/resource_constraints/).
- [Ejecución y opciones de contenedores](https://docs.docker.com/engine/containers/run/).
- [Opciones de Maven](https://maven.apache.org/ref/3.9.9/maven-embedder/cli.html).
- [Preparación de dependencias go-offline](https://maven.apache.org/plugins/maven-dependency-plugin/go-offline-mojo.html).
