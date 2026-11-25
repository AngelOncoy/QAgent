# Matriz de compatibilidad Java con proyectos externos (#309)

La matriz fija **qué** combinaciones de proyecto, commit y configuración se
comprueban y **qué** se espera de cada una antes de ejecutarlas. Vive en
`tests/compatibilidad_java/matriz.toml`; el ejecutor en
`tests/compatibilidad_java/ejecutar.py` y el comando en `scripts/matriz_java.py`.
Los fixtures anteriores (`bench_java`, banco Spring, #262, #290, #292) siguen
siendo la base y figuran como filas `fixture`: no se borran ni se presentan
como una matriz completa.

## Filas

| Fila | Tipo | Nivel | Soporte | Configuraciones | Origen fijado |
|---|---|---|---|---|---|
| gs-maven | externo | pr | declarado | maven_simple, inferencia | spring-guides/gs-maven `c65883f80b35` (Apache-2.0), `complete/` |
| gs-maven-defecto | externo | pr | declarado | + defecto_sembrado | mismo commit, `Greeter` cambiado en la copia |
| gs-multi-module | externo | pr | declarado | reactor, padre_publico, inferencia, spring | spring-guides/gs-multi-module `d88a2b721bda` (Apache-2.0) |
| gs-rest-service | externo | ampliada | no_admitido | padre_publico, spring | spring-guides/gs-rest-service `e15fec6773dc` (Apache-2.0), Spring Boot 4 |
| thealgorithms-java | externo | ampliada | declarado | maven_simple, tipos_aserciones, proyecto_grande | TheAlgorithms/Java `15a4a9d36387` (MIT), ~850 fuentes, JUnit 6, `-Werror` |
| thealgorithms-java-defecto | externo | ampliada | declarado | tipos_aserciones, defecto_sembrado | mismo commit, comparación de `FindMax` invertida |
| banco-spring | fixture | pr | declarado | spring, defecto_sembrado | `bench_java/src/test/resources/spring` |
| banco-java, perfiles-java, maven-padre-perfil-reactor, inferencia-java | fixture | ampliada | declarado | maven_simple, perfiles, padre_publico, reactor, inferencia… | pruebas `docker` existentes |

Cada externo declara URL, licencia (se comprueba que el archivo de licencia del
commit la contiene), SHA completo de 40 caracteres, subdirectorio, perfil,
objetivos y, por objetivo, el estado esperado. Nunca se usa la rama principal:
el ejecutor descarga solo ese commit (`git fetch --depth 1 origin <sha>`, sin
hooks ni credenciales) y comprueba `HEAD`. Una variante `defecto_sembrado` hereda
commit y casos de su base y aplica un parche que debe coincidir exactamente una
vez en la **copia**; el checkout descargado no cambia.

Los esperados de los casos salen del Javadoc del commit fijado (`FindMax`,
`AbsoluteValue`) o, sin Javadoc, de la lectura estática del cuerpo con origen
`inferido` y su evidencia (ADR-018). Nunca de ejecutar el proyecto.

## Resultados posibles de una fila

| Resultado | Significado | ¿Éxito? |
|---|---|---|
| `aprobado` | Soporte declarado y cada objetivo terminó en el estado esperado | Sí |
| `no_admitido_confirmado` | Escenario fuera del alcance y QAgent lo omitió o bloqueó con el motivo esperado | Sí |
| `fallo_funcional` | La corrida terminó, pero algún objetivo quedó en otro estado (incluye omitido, ausente o sin veredicto cuando se esperaba otra cosa) | No |
| `fallo_tecnico` | Descarga, commit, licencia, parche, imagen, Docker o excepción | No |
| `no_ejecutado` | No se ejecutó: presupuesto agotado o una prueba de fixture `skipped` | No |

Una omisión o un `skipped` nunca cuentan como aprobación, y una fila declarada no
puede esperar solo omisiones: el manifiesto lo rechaza. Tampoco hay `skip`/`xfail`
para ocultar una incompatibilidad: si una fila no pasa, el comando sale con 1.

## Ejecución

Necesita Docker y red (descargar commits y preparar imágenes). La IA es la
grabada de `tests/compatibilidad_java/proveedor.py`: 0 tokens y sin claves. El
proveedor solo sustituye la respuesta del modelo; Planner, Generator, guardrails,
preparación de imagen, construcción, ejecución en Docker sin red y veredictos son
los productivos.

```powershell
python scripts/matriz_java.py --listar --nivel ampliada
python scripts/matriz_java.py --nivel pr --salida C:/ruta/evidencias-matriz
python scripts/matriz_java.py --nivel ampliada --salida C:/ruta/evidencias-matriz
python scripts/matriz_java.py --fila gs-maven --fila gs-maven-defecto --salida C:/ruta/otra
```

En `--salida` quedan `matriz.json` (entorno, filas, esperados, observados y
diferencias), `matriz.md` y una carpeta por fila con `fila.json` y la carpeta de
la corrida (`results.json`, `detalle.json` con los JUnit y la salida de Maven,
`construccion.log`, `entorno.log` si falló la preparación, `recursos.json`), o el
`junit.xml` y `pytest.log` de un fixture, también cuando la fila no aprueba. Todo
el texto pasa por el saneado de secretos de QAgent antes de guardarse. El
entorno registra versión y commit de QAgent, Python, sistema, versión de Docker,
ID de la imagen Java y las versiones de JDK y Maven de la imagen. Al terminar se
borran las imágenes derivadas que creó la corrida, salvo con
`--conservar-imagenes`.

Las pruebas de las reglas del manifiesto, la clasificación, el saneado y el
proveedor grabado no usan Docker ni red y corren con la suite general:

```powershell
python -m pytest tests/compatibilidad_java -q
```

## En GitHub Actions

`.github/workflows/pruebas-docker.yml` tiene un trabajo `matriz-java`:

- **En cada PR a `develop`** que toca `src/qagent/lenguajes/java*.py`, el sandbox,
  el orquestador, los agentes, los contratos, `bench_java/` o la matriz: nivel
  `pr`, presupuesto de 25 minutos para iniciar filas y 40 de límite del trabajo.
  Una fila que no llega a iniciarse queda `no_ejecutado` y el trabajo falla.
- **Cada lunes** sobre `develop` y **a mano** (Run workflow, nivel a elegir): la
  matriz ampliada, con 100 y 120 minutos.
- El resumen Markdown se publica en la página del trabajo y la evidencia se sube
  como artefacto (14 días), excluyendo los checkouts descargados.

## Qué encontró la matriz

La primera ejecución detectó tres incompatibilidades reales y una prueba
desactualizada, corregidas en #309:

1. **JUnit 4 en el proyecto** (`gs-maven`). Surefire añade `junit-vintage-engine`
   con la versión de Jupiter de la prueba y Maven offline fallaba antes de
   ejecutarla. La receta Maven lo descarga cuando hay `junit:junit` (huella `v8`).
2. **Pruebas en un módulo de reactor** (`gs-multi-module`). El Generator escribía
   `library/src/test/java/...` y `generated_test.v2` solo admitía `src/test/java/`.
   El schema acepta ahora carpetas de módulo delante, con las mismas restricciones.
3. **Launcher JUnit en un reactor** (`gs-multi-module`, Spring Boot 3.5 con JUnit
   1.12.2). `dependency:list -DappendOutput` con un archivo común quedaba con la
   lista del último módulo (el agregador, vacío) y no se descargaba el launcher de
   la versión del proyecto; solo funcionaba si coincidía con la de QAgent (1.14.4).
   Cada módulo escribe ahora su lista y se juntan (huella `v9`).
4. `test_spring_corrida_docker.py` esperaba 2 contenedores; desde #305 hay una
   construcción previa a la IA. Ahora exige 3 y que el primero sea `clean compile`.

## Resultados de referencia

Ejecución local del 25/11/2026 sobre esta rama, Windows 11, Docker 29.8.1,
`qagent-sandbox:java` (Temurin 25.0.4.1, Maven 3.9.16), límites 4 GiB / 300 s:

| Fila | Resultado | Observado | Duración |
|---|---|---|---|
| gs-maven | aprobado | `Greeter.sayHello` inferido: accept | 68 s (imagen nueva) |
| gs-maven-defecto | aprobado | hallazgo a revisar (inferido, no un bug) | 13 s |
| gs-multi-module | aprobado | `ServiceProperties.getMessage` inferido: accept; `GET /` omitido | 98 s |
| banco-spring | aprobado | 1 passed: 1 accept, 1 bug 201/200, 1 omitido | 120 s |
| gs-rest-service | no_admitido_confirmado | `GET /greeting` omitido: sin resultado esperado verificable | 82 s |
| thealgorithms-java | aprobado | `FindMax.findMax` (normal + excepción) y `AbsoluteValue.getAbsValue`: accept, JaCoCo 100 % | 644 s |
| thealgorithms-java-defecto | aprobado | `FindMax.findMax`: bug_detectado; `AbsoluteValue`: accept | 559 s |

Nivel `pr` completo: 4 aprobadas de 4, código de salida 0, 299 s con la imagen base
ya construida. Las filas `ampliada` de TheAlgorithms y `gs-rest-service` corrieron
con la receta `v8`; el cambio a `v9` solo afecta a reactores. Las demás filas
`fixture` de la matriz ampliada son las pruebas `docker` existentes y se ejecutan
cada lunes en Actions.

Las demás filas y las repeticiones tras las correcciones se registran en el
informe de la tarea en `docs/evidencias/`. Las duraciones incluyen descarga,
imagen y varias JVM; no son una garantía de latencia.

## Límites

- La matriz no certifica compatibilidad universal con Maven ni con todas las
  bibliotecas sobre JDK 25; solo las filas declaradas en su commit.
- `thealgorithms-java` recompila el proyecto completo en cada prueba (unos 9
  minutos): queda en la matriz ampliada, no en la de PR. Véase #296.
- Spring Boot 4 (`gs-rest-service`) solo se comprueba hasta la omisión del
  endpoint sin oráculo; la plantilla MockMvc no está validada con Boot 4.
- Las respuestas de IA son grabadas: no se acredita el comportamiento de un
  proveedor LLM real ni la ventana de escritorio.
