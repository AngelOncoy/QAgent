# Controladores Spring y MockMvc (#183)

## Análisis y planificación

El análisis usa la gramática tree-sitter Java instalada por #181. No necesita
un JDK en el anfitrión ni carga la aplicación del usuario. `java_spring.py`
reconoce anotaciones Spring importadas o cualificadas: `RestController`,
`Controller`, `ResponseBody`, `RequestMapping` y los mappings HTTP específicos.
Combina prefijos y rutas literales, incluidos arrays; conserva parámetros de
ruta, query, cabeceras y cuerpo, tipos, anotaciones y estado explícito. Las rutas
calculadas o con placeholders de configuración quedan sin resolver.

El módulo expone los manejadores HTTP como endpoints, sin duplicarlos como
invocaciones unitarias directas. Los demás métodos públicos siguen disponibles
para JUnit como antes. Cada contrato v3 mantiene `lenguaje: java`,
`framework_pruebas: junit5`, `framework_app: spring` y la clase concreta del
controlador, incluso si el archivo contiene varias clases.

`java_spring_planificacion.py` envía al Planner exclusivamente declaraciones,
sin cuerpos ni notas de implementación. Sus filtros deterministas admiten el
estado explícito de `ResponseStatus` y el error 400 por ausencia de un parámetro
`RequestParam`, `RequestBody` o `RequestHeader` requerido y sin valor por defecto.
Un tipo general de retorno no justifica valores JSON concretos. No se obtiene
el esperado ejecutando el endpoint ni observando su implementación.

El punto de extensión `LanguageAdapter.motivo_endpoint_no_planificable` permite
omitir una declaración insuficiente antes de pedir casos al modelo. El Planner
conserva el motivo y el orquestador lo registra como «sin resultado esperado
verificable». El comportamiento predeterminado de los otros adaptadores no
filtra endpoints adicionales. `aplicacion_de_endpoint` permite seleccionar el
controlador específico sin incorporar lógica Spring al Planner compartido.

En esta etapa conservadora se omiten controladores de vistas sin `ResponseBody`,
estados no resolubles, condiciones de mapping en `params`/`headers` y verbos que
el contrato HTTP aún no representa. Los casos con ruta, verbo o estado inventado,
JSON no declarado o tipos HTTP incompatibles se rechazan. Las restricciones de
DTO y las expectativas sobre servicios simulados requieren su validación antes
de habilitar la generación correspondiente.

## Verificación de este bloque

```powershell
python -m pytest tests/lenguajes tests/agents/test_planner_java.py tests/agents/test_planner_spring.py -q
```

`test_planner_spring.py` utiliza el Planner, adaptador, parser, validación de
contratos y orquestador productivos con respuestas de IA grabadas. Comprueba que
un endpoint sin declaración no llama al modelo, al Generator ni al Reviewer.
Estas pruebas no ejecutan Java ni necesitan Docker o internet.

## Generación y guardrail MockMvc

El Generator compartido usa el contexto estático del controlador y una plantilla
de `java_spring_generacion.py`: `@WebMvcTest(controllers = Clase.class)`,
`@ContextConfiguration(classes = Clase.class)`, un campo `MockMvc` inyectado y
un `@MockBean` por dependencia nominal declarada. La configuración selecciona
el controlador sin iniciar un `@SpringBootTest` completo. Los servicios pueden
proceder de un constructor único o de campos `@Autowired`; los constructores
ambiguos, valores primitivos de configuración y varios beans del mismo tipo se
omiten sin adivinar cómo construirlos. Los nombres de mocks llevan el prefijo
`mock_` para no colisionar con el campo `mvc`.

El artefacto es `generated_test.v2`, en `src/test/java/<paquete>/<Clase>Test.java`.
Cada caso conserva verbo, ruta, query, cabeceras, cuerpo JSON y estado exactos del
contrato. El prompt incluye esta plantilla verificable y no incluye cuerpos de
implementación. Solo se permite cambiar formato y comentarios.

Antes de ejecutar, el adaptador vuelve a leer la fuente y contrasta controlador,
firma, ruta y dependencias. Compara los tokens del AST de la prueba con los de
la plantilla, ignorando comentarios y orden de imports. Así rechaza aserciones
eliminadas o modificadas, rutas diferentes, mocks del controlador/MockMvc,
`@Disabled`, helpers, bloques que oculten errores y código ajeno al contrato.
El mismo control se aplica al primer intento. Entre intentos, el guardrail
registra las modificaciones como `laundering_detectado` sin consultar IA ni
invocar el ejecutor. Es deliberadamente conservador: no demuestra equivalencia
de refactorizaciones arbitrarias del test.

`test_generator_spring.py` prueba el Generator y Reviewer productivos, con una
respuesta Java grabada independiente de la función que construye la plantilla.
Incluye modificaciones maliciosas, preservación de comentarios/formato,
dependencias por constructor/campo y rechazos antes del puerto de ejecución.

## Banco reproducible y ejecución offline

La extensión de TA-01 está en `bench_java/src/test/resources/spring/`. Es un
proyecto Maven independiente: se copia fuera de `src/test/resources` para
analizarlo y ejecutarlo. Así no se mezclan sus controladores con los seis casos
unitarios originales ni se ejecuta un defecto intencional en la CI general.
Declara Spring Boot 3.5.7 mediante BOM, `spring-boot-starter-web` y
`spring-boot-starter-test`; el BOM JUnit 5.14.4 mantiene coherente la versión con
las herramientas ya presentes en la imagen Java. No usa un POM padre ni módulos.

El controlador tiene un endpoint correcto con estado declarado 201, otro con
el defecto intencional D-Spring-01 (declara 201 pero devuelve un ResponseEntity
200) y uno sin estado verificable que debe omitirse. Su servicio es una interfaz
sin implementación real; `@MockBean` permite ejecutar el controlador sin red,
base de datos ni servicio externo.

Primero se prepara la imagen derivada, con red únicamente para descargar las
dependencias declaradas:

```powershell
python -u -c "from qagent.sandbox.imagen import preparar_imagen; print(preparar_imagen('bench_java/src/test/resources/spring', imagen='qagent-sandbox:java', avanzar=print))"
```

Después se ejecuta la prueba real, marcada `docker`. Omite la prueba si la imagen
no está preparada: no descarga dependencias durante la ejecución.

```powershell
python -m pytest tests/sandbox/test_spring_corrida_docker.py -q -s
```

La prueba usa la entrada productiva `ejecutar_corrida` y respuestas de proveedor
grabadas, sin sustituir agentes, parser, guardrails, selección/preparación de
imagen ni el ejecutor. Comprueba `accept`, `bug_detectado`, la omisión y su
motivo, JaCoCo del manejador, lenguaje Java en `results.json` y el informe, y que
los archivos del proyecto original no cambien. Observa las opciones reales de
Docker: red `none`, raíz de solo lectura, límites Java del equipo (4 GiB y
300 s) y eliminación de cada contenedor al terminar.

Primera corrida completa verificada: **1 passed en 176.32 s**; un endpoint
correcto, un bug detectado y uno omitido. Los métodos ejecutados tuvieron 100 %
de líneas JaCoCo; esto no representa cobertura del endpoint omitido ni de todos
los caminos del proyecto. Los valores HTTP esperado/obtenido se extraen del
mensaje JUnit `Response status expected:<201> but was:<200>`, únicamente como
diagnóstico de ejecución, nunca como oráculo del Planner.

La repetición aislada con la comprobación de valores HTTP en `detalle.json`
terminó con **1 passed en 120.72 s**. La revisión general sin Docker ni red
terminó con **2910 passed, 40 deselected**, lint y formato correctos.

## Problemas encontrados al integrar

La ruta predeterminada del backend todavía preparaba la imagen Python aunque
el adaptador fuera Java. Se corrigió para usar `entorno_sandbox().imagen` tanto
en corridas nuevas como al repetir pruebas. Un punto de extensión conserva la
comprobación de librerías de sistema del entorno Python sin invocarla en Java.
La selección de cobertura usa el manejador declarado del contrato en lugar del
texto `POST /ruta`.

Además, `mvn dependency:go-offline` dejó sin descargar algunas versiones
gestionadas por el BOM de Spring. La construcción Maven completa ahora la
resolución con `dependency:resolve`; la clave de caché cambia para no reutilizar
imágenes anteriores incompletas. Esta preparación no permite acceder a internet
durante la prueba: el comando sigue usando `mvn --offline` y Docker sin red.

Al ejecutar simultáneamente la suite general y Docker, Surefire forzó el cierre
de una JVM y dejó una cobertura incompleta. El clasificador Java identifica ese
diagnóstico como `terminacion_jvm`, sin veredicto. La repetición aislada verificó
la cobertura y los valores del informe sin aumentar los límites del sandbox.

## Revisión de los criterios de #183

| Criterio | Evidencia |
|---|---|
| Controladores, rutas, parámetros y tipos | `tests/lenguajes/test_java_spring.py`, parser real sin ejecutar fuentes. |
| Contratos endpoint desde declaraciones | `tests/agents/test_planner_spring.py`, contratos v3 y filtros de procedencia. |
| WebMvcTest, MockMvc y MockBean | `tests/agents/test_generator_spring.py`, artefacto v2 y oráculo AST del Reviewer. |
| Sandbox Java offline y revisión compartida | `tests/sandbox/test_spring_corrida_docker.py`, corrida productiva con red none, límites y limpieza reales. |
| Omisión sin declaración verificable | Planner, orquestador y corrida real registran el motivo sin ejecutar ese endpoint. |
| Pruebas sin Docker y banco real | Suite general, pruebas específicas y extensión de TA-01 en recursos, con defecto controlado. |

## Guion del video de revisión

1. Mostrar la rama `feat/183-spring-mockmvc` y abrir el controlador del banco.
   Explicar sus tres endpoints: correcto, defecto 201/200 y sin declaración.
2. Mostrar el código grabado de prueba en `test_generator_spring.py`: WebMvcTest,
   MockMvc y MockBean. Aclarar que solo el proveedor de IA está simulado; los
   agentes, guardrails y la ejecución Spring/Docker son productivos.
3. Con Docker Desktop iniciado y el entorno virtual activo, grabar la ejecución
   de `python -m pytest tests/sandbox/test_spring_corrida_docker.py -q -s`.
   Ejecutarla separada de la suite general. La imagen derivada debe estar preparada.
4. Mostrar `Spring real: 1 accept, 1 bug de estado 201/200, 1 omitido` y `1 passed`.
   Explicar que los asserts también verifican JaCoCo, red none, límites, limpieza,
   `results.json`, informe y esperado/obtenido de `detalle.json`.
5. Enviar el video con el PR a la persona revisora. No afirmar que se verificó
   visualmente la ventana de escritorio si el video solo muestra la prueba backend.

El PR de esta última tarea referencia #183 y, por indicación del equipo, incluye
también el cierre de la épica #174. La revisión y la fusión corresponden al equipo.
