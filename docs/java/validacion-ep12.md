# EP-12 · Validación del soporte de Java (#174)

Esta verificación reúne evidencia de la épica y sus dependencias #168 y #169.
Los resultados esperados proceden de Javadoc, tipos y declaraciones de rutas;
nunca se obtienen ejecutando el proyecto.

## Criterios y trazabilidad

| Criterio de #174 | Implementación | Comprobación reproducible |
|---|---|---|
| Banco Java con Javadoc y JUnit 5 | #131, `bench_java` | `test_ep174_java_integrado_docker.py` conserva el POM original y exige tres métodos correctos y tres defectos detectados. |
| Prototipo de análisis estático y ejecución | #132, tree-sitter-java, `JavaAdapter` | `tests/lenguajes/test_java*.py`: extracción de estructura, Javadoc, parámetros y exportación JSON. |
| Unitarias Java en el flujo completo | #181, #184, #182 y apertura #227 | Apertura → vista previa → selección → agentes → resultados → repetición de aprobadas. |
| Mutación PIT en métodos críticos | #180 | `test_pit_corrida_docker.py`: perfil Profundo, mutación acotada y puntuación reutilizada en regresión. |
| Python conserva su funcionamiento | Adaptador Python y contratos existentes | Regresión general sin Docker/red, sin relajar aserciones. |
| Controladores Spring de la descripción | #183 | `test_spring_corrida_docker.py`: MockMvc, MockBean, caso correcto, bug HTTP y omisión sin oráculo. |

Las referencias antiguas «por crear» corresponden hoy a #181, #184, #182 y #180.
`tree-sitter-java==0.23.5` ya está declarado en `pyproject.toml`. El cierre de
sub-issues no sustituye la validación sobre la versión integrada.

## Alcance

Se comprueban proyectos Maven de un módulo, sin POM padre, con fuentes en
`src/main/java`. El banco y el ejemplo Spring usan Java 21; el JDK vive en la
imagen. Se usan JUnit 5, JaCoCo y PIT. Spring MVC se prueba mediante la plantilla
verificable de WebMvcTest/MockMvc con servicios MockBean, sin servicios reales.
Gradle, herencia Maven, multimódulo y sobrecargas no se declaran validados.

## Entorno de esta comprobación

Validación local del 3 de noviembre de 2026 sobre la base integrada `d5f8750`:
Windows 11, Python 3.10.10, tree-sitter 0.24.0 y tree-sitter-java 0.23.5.
Docker Engine 28.3.3; imagen Java reconstruida desde la receta vigente con
Temurin 25.0.4.1 y Maven 3.9.16. Los proyectos comprobados compilan para Java 21.
El límite configurado por ejecución Java es 4 GiB y 300 segundos.

## Preparación

Docker Desktop debe estar iniciado. Reconstruir la base si es anterior a los
cambios actuales del equipo y preparar las derivadas con red solo al construir:

```powershell
python -u -c "from qagent.sandbox.imagen import construir_imagen_base; print(construir_imagen_base(imagen='qagent-sandbox:java', avanzar=print))"
python -u -c "from qagent.sandbox.imagen import preparar_imagen; print(preparar_imagen('bench_java', imagen='qagent-sandbox:java', avanzar=print))"
python -u -c "from qagent.sandbox.imagen import preparar_imagen; print(preparar_imagen('bench_java/src/test/resources/spring', imagen='qagent-sandbox:java', avanzar=print))"
```

Ningún comando ejecuta fuentes Java en la máquina anfitriona.

La derivada Maven descarga también `junit-platform-launcher` con la versión del
engine resuelto del proyecto, incluso si procede de un BOM. Surefire lo solicita
dinámicamente: `go-offline` y `dependency:resolve` por sí solos dejaron fuera el
launcher 1.11.4 del banco original. La receta actual invalida esas imágenes
anteriores. No se cambia el POM ni se ejecutan pruebas durante esta preparación.
La alineación está descrita en la [guía de JUnit](https://docs.junit.org/5.14.1/running-tests/build-support.html).

## Regresión sin Docker ni proveedores reales

```powershell
python test.py -m "not docker and not red"
```

Incluye lint, formato, contratos, análisis, agentes, persistencia y flujo Python.
Para guardar temporales dentro del proyecto, usar un basetemp dedicado:

```powershell
python test.py -m "not docker and not red" --basetemp .qagent/pytest-174-cierre-evidencia
```

Las pruebas de auditoría aíslan automáticamente el descubrimiento de Git para
sus archivos ficticios mediante una fixture con entorno temporal. Así no heredan
el repositorio padre cuando `--basetemp` está dentro de `.qagent/`. No hace falta
configurar `GIT_CEILING_DIRECTORIES` manualmente; sus aserciones no cambian.

## Banco original, Spring y PIT con Docker real

Ejecutar por separado de la regresión general para evitar competencia con la JVM:

```powershell
python -m pytest tests/sandbox/test_ep174_java_integrado_docker.py -q -s
python -m pytest tests/sandbox/test_spring_corrida_docker.py -q -s
python -m pytest tests/sandbox/test_pit_corrida_docker.py -q -s
```

La prueba de aceptación copia el banco conservando su POM, abre y analiza con
DesktopAPI y entrega los seis objetivos a la entrada productiva de la corrida,
con la preparación normal de imagen. Solo se sustituye el proveedor de IA por
respuestas grabadas basadas en la especificación independiente del banco.

Se exige `3 accept + 3 bug_detectado`, cobertura por método y lenguaje Java en
resultados, además de tres aprobaciones al repetir las pruebas guardadas. Se
comprueban red deshabilitada, raíz de solo lectura, memoria configurada,
eliminación de contenedores y conservación de las fuentes originales.

Un `skipped` por falta de imagen no acredita ejecución real. Los errores de
compilación, memoria, tiempo o dependencias se registran como fallos técnicos.

## Interpretación de la evidencia

Resultados de la repetición final, confirmados en las capturas de terminal:

| Comprobación | Resultado |
|---|---|
| Auditoría con temporales dentro de .qagent | 8 aprobadas, 5,24 s. |
| Recetas de imágenes por lenguaje (Docker simulado) | 32 aprobadas, 1,80 s. |
| Revisión general final sin Docker/red | 3211 aprobadas, 1 omitida, 59 deseleccionadas, 255,36 s; lint y formato correctos (417 archivos). |
| Banco original y repetición de aprobadas | 1 prueba aprobada, 186,78 s; 3 accept, 3 bugs, cobertura del 100 % por método; regresión con 3 accept. |
| Spring MVC | 1 prueba aprobada, 98,62 s; 1 accept, 1 bug HTTP 201/200, 1 omitido; cobertura del 100 %. |
| PIT en Profundo | 1 prueba aprobada, 63,17 s; puntuación del 60 %, solo Criticos.critico; caché reutilizada sin repetir PIT. |
| Pruebas afectadas del sandbox tras corregir el launcher | 284 aprobadas y 51 deseleccionadas, 42,90 s. |

Las duraciones son las de pytest en este equipo; incluyen preparación y varias
ejecuciones. No son el tiempo ni el consumo de memoria de una única prueba JVM.

Java y sus herramientas se ejecutan realmente en Docker. Las respuestas de IA
son grabadas: no se acredita aquí el comportamiento de un proveedor LLM real.
La prueba de DesktopAPI tampoco sustituye la comprobación visual de toda una
corrida en la interfaz. Las capturas y resultados observados se registran en
el informe local de #174 en `docs/evidencias/`.

Referencias: [ejecución Java](ejecucion-revision.md),
[generación y guardrail](generacion-guardrail.md), [PIT](mutacion-pit.md) y
[Spring MVC](spring-mockmvc.md).
