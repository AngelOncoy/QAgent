# Ejecución y revisión Java en el sandbox (#182)

## Base de trabajo

Rama: `feat/182-ejecucion-revision-java`, creada desde el commit `eeb64f7` de
`feat/181-analisis-plan-java`. #181 todavía esperaba revisión al iniciar esta tarea.
Antes del PR final se revisará su comparación cuando el equipo integre la base.
No se modifica ni se fusiona el PR de #181 desde esta tarea.

#182 es la tercera parte de EP-12a. Se reutilizan la conexión de adaptadores de
#168, la imagen y los límites Java de #169 y el banco de #131. La generación y
su guardrail pertenecen a #184, que se desarrollará posteriormente por decisión
del integrante. Las comprobaciones de ejecución usarán pruebas JUnit controladas;
esa sustitución debe distinguirse de una corrida con generación automática real.

## Primer bloque: informes JUnit

`JavaAdapter.interpretar_resultados` delega en `java_junit.py`. Se reutilizan los
casos y totales del lector común, añadiendo tipo de error, esperado/obtenido y
marcos Java con archivo y línea. El estado original de cada caso se conserva:
éxito, fallo de aserción, error técnico u omisión.

Los esperado/obtenido son textos explícitos del diagnóstico JUnit, no resultados
calculados por QAgent ni oráculos que alimenten al Planner. Se reconoce el mensaje
expected: <...> but was: <...>, incluidos prefijos personalizados de JUnit 5.
Un formato desconocido o ambiguo conserva su mensaje y traza sin inventar valores.
También se presenta el diagnóstico de assertThrows cuando no se lanza excepción.

La pila conserva marcos con fuente y línea positiva. Cuando existe un marco de la
clase de prueba, se usa como ubicación principal, en lugar de elegir una línea de
Assertions.java. Native Method y Unknown Source se mantienen en el texto sin
inventar ubicaciones. No se abre ninguna ruta de la traza. La traza y el número de
marcos están limitados.

El lector rechaza XML inválido, entidades, suites anidadas, casos fuera de su nivel,
duraciones negativas/no finitas, estados incompatibles y reportes sin casos.
Los resultados de casos omitidos se conservan como omisiones.

## Evidencia de este bloque

`tests/fixtures/java/junit5-banco.xml` sigue siendo la grabación real de TA-01,
con sus once casos. `junit5-fallos-controlados.xml` es una fixture sintética
etiquetada como tal, con éxito, fallo, error y omisión; no demuestra ejecución
real en Docker. Los informes reales de #182 se describen en el cuarto bloque.

```powershell
python -m pytest tests/lenguajes/test_java_resultados.py tests/lenguajes/test_java_junit.py -q
```

Resultado: **32 pruebas aprobadas**, sin ejecutar Java ni necesitar Docker.
Se comprueba además la conservación de los diagnósticos en resumir_ejecucion,
el componente común que utiliza el Reviewer. Esta prueba no equivale todavía a
una revisión completa con Generator y ejecución real.

## Segundo bloque: cobertura JaCoCo

`JavaAdapter.leer_cobertura` lee exclusivamente `jacoco.xml` desde la salida del
sandbox. `java_cobertura.py` convierte sus datos a files/totals, compatibles con
los cálculos compartidos. Conserva líneas ejecutadas/faltantes y cantidades de
ramas por línea. No inventa arcos ni líneas destino de ramas: las entradas de rama
son números de origen repetidos según el contador de JaCoCo.

Se respetan las métricas de JaCoCo: una línea cuenta como ejecutada cuando al menos
una instrucción se ejecutó. Puede contener instrucciones o ramas pendientes sin
contarse también como una línea faltante. Las ramas de JaCoCo no equivalen al
conteo de decisiones del análisis: JaCoCo mide las alternativas del bytecode de
if/switch y no considera catch como una rama de cobertura.

La sección functions conserva contadores de class/method por nombre y descriptor
JVM. `cobertura_de_metodo` selecciona ese resumen exacto; no suma las líneas de
varios métodos para inventar la cobertura del archivo. Esto distingue métodos
que comparten un renglón. Las sobrecargas se guardan con descriptor y no se elige
una de ellas por nombre sin más información. Sin ramas, la métrica es None;
sin líneas de fuente utilizables, el lector devuelve None.

Las rutas se proyectan a src/main/java/paquete/Archivo.java, que es la disposición
Maven estándar prevista para el ejecutor. No se afirma compatibilidad con cualquier
directorio de fuentes personalizado. Archivos de grupos que tengan la misma ruta
se rechazan por ambigüedad. Los paquetes vacíos y clases anidadas se conservan.

El lector admite la declaración DTD estándar de JaCoCo retirándola antes del
parseo; nunca descarga report.dtd. Rechaza otras DTD, entidades, rutas externas,
contadores negativos, datos inconsistentes, duplicados y cantidades excesivas.
Se limita el tamaño del archivo y la expansión de datos de líneas/ramas. No se
abren las fuentes ni se ejecuta código Java para leer el informe.

La fixture `tests/fixtures/java/jacoco-controlado.xml` es sintética y está marcada
como tal. La grabación real del banco con JaCoCo se describe en el cuarto bloque.
Las pruebas sintéticas no sustituyen esa ejecución real.

```powershell
python -m pytest tests/lenguajes/test_java_cobertura.py -q
```

Resultado: **29 pruebas aprobadas**. Se verifican la cobertura parcial, métricas
por método, métodos sin ramas, sobrecargas, renglones compartidos, fuentes sin
datos de depuración, XML inválido y compatibilidad con el recorte por rango del
Reviewer. La selección del resumen exacto por objetivo se conectará en el bloque
de revisión, junto con los rangos del analizador.

Referencias del formato y sus métricas:
[Contadores JaCoCo](https://www.jacoco.org/jacoco/trunk/doc/counters.html) y
[DTD oficial](https://raw.githubusercontent.com/jacoco/jacoco/master/org.jacoco.report/src/org/jacoco/report/xml/report.dtd).

## Tercer bloque: comando y preparación de la ejecución

`JavaAdapter.comando_pruebas` devuelve etapas Maven offline. El módulo se valida
y pasa como argumento separado, sin interpolarse en un script. Las etapas se
identifican en la salida con QAGENT_JAVA_ETAPA: proyecto, prueba, ejecucion y
cobertura. Primero se compilan las fuentes del proyecto y después la prueba.
La ejecución JUnit conserva su código de salida; el informe JaCoCo se intenta
generar también cuando una aserción falla. Si falta ese informe se registra un
error técnico en la etapa cobertura, sin presentar una métrica inventada.

Antes de ejecutar el comando, `preparar_java` debe recibir una copia desechable
del proyecto y la carpeta con una fuente .java controlada. La preparación es
estática en Python: no ejecuta Java ni Maven en el anfitrión. Crea
.qagent-junit.xml y .qagent-junit-tests, y dirige la compilación a
.qagent-junit-target. No modifica el pom.xml ni src/test originales. Rechaza
rutas reservadas preexistentes y usa exclusivamente la prueba recibida.

El POM temporal toma versiones de herramientas de la receta compartida del
sandbox, conserva las dependencias existentes y añade JUnit 5 si falta. Se
preserva la configuración útil del compilador y las opciones JVM de Surefire;
se ajustan selección de prueba, reportes y agente JaCoCo para esta ejecución.
Las dependencias del proyecto deben estar disponibles en su imagen derivada:
la ejecución no habilita red para descargarlas.

Se mantiene el alcance inicial Maven de un módulo sin padre. Los errores de
preparación de proyecto y prueba se distinguen con ErrorPreparacionSandbox y
la etapa correspondiente. Una prueba con sintaxis inválida no se repara para
hacerla pasar: se conserva para el diagnóstico de test-compile.

JUnit escribe informes en /out/junit-raw y JaCoCo en /out/jacoco.xml.
`recoger_junit` combina las suites de esa salida con límites de tamaño y sin
seguir rutas externas; conserva fallos y devuelve None si el informe no es válido.

```powershell
python -m pytest tests/lenguajes/test_java_ejecucion.py -q
```

Resultado: **21 pruebas aprobadas**, sin ejecutar Maven, Java ni Docker.
Se verifican las etapas del comando, conservación de archivos y dependencias,
selección de una prueba, errores de preparación y agregación de reportes.
Las pruebas detectaron una duplicación de saltos de línea en Windows al copiar
la fuente; se corrigió y se verifica la conservación de sus bytes.

La conexión con el ejecutor común y la evidencia real se describen a continuación.

## Cuarto bloque: conexión y ejecución real

LanguageAdapter ofrece dos puntos opcionales: preparador_sandbox y
lector_informe_sandbox. Su valor por defecto es None, conservando la ejecución
de Python. Java entrega preparar_java y recoger_junit. El Reviewer pasa esas
operaciones al ejecutor común sin incorporar reglas específicas de Java.

El preparador se llama después de copiar el proyecto y antes de crear el
contenedor. Los errores controlados se devuelven como fallos de preparación con
su etapa; no arrancan un contenedor. Los errores inesperados se propagan, y en
ambos casos se limpia la copia. Los lectores se ejecutan antes de borrar /out y
sus datos se conservan en ResultadoSandbox. No cambian las restricciones de red,
montajes, privilegios, memoria, CPU, tiempo o limpieza.

La validación con Docker simulado y pruebas existentes del sandbox y Reviewer
produjo **55 aprobadas**. Incluye preparación en la copia, recogida de reportes,
recorte de CPU, memoria y timeout, pruebas montadas en solo lectura y limpieza.
La validación conjunta de adaptadores, Planner y conexión, incluidas las dos
nuevas lecturas de XML real, produjo **270 aprobadas**. Lint y formato pasaron.

### Prueba Docker sobre TA-01

```powershell
python -m pytest tests/sandbox/test_java_ejecucion_docker.py -q -s
```

Resultado del 30/10/2026: **2 pruebas del sistema aprobadas en 51.48 s**.

| Método del banco | Resultado JUnit | Líneas / ramas | Tiempo del sandbox |
|---|---|---|---|
| BancoCorrecto.sumarPrecios | 1 caso, 0 fallos | 100 % / 100 % | 25.812 s |
| BancoDefectuoso.calcularPromedio | 1 caso, 1 fallo: 2.5 esperado y 2.0 obtenido | 100 % / 100 % | 23.547 s |

Cada ejecución respetó el límite Java de 4 GB y timeout de 300 s y produjo
JUnit/JaCoCo. Se ejecutó solo la prueba recibida; las once pruebas preexistentes
del banco quedaron fuera. El POM y los archivos del proyecto original no cambiaron.
La prueba del sistema pasa cuando verifica que JUnit detectó el defecto previsto:
no convierte ese fallo JUnit en un caso correcto de la aplicación.

La prueba usa las fuentes reales de TA-01 y un POM con las versiones de la receta
ya almacenadas en la imagen. Las pruebas JUnit son controladas: esta validación
no demuestra generación automática con #184 ni una corrida completa desde la
interfaz. La cobertura del 100 % del promedio registra ejecución del código,
mientras que su aserción demuestra que el comportamiento incumple el Javadoc.

Los informes reales del promedio están en junit5-sandbox-promedio.xml y
jacoco-sandbox-promedio.xml dentro de tests/fixtures/java. Se retiraron las
propiedades del entorno del JUnit; casos, mensajes, trazas y tiempos se conservaron.
Las pruebas unitarias leen esos archivos sin necesitar Docker.
Solo se regeneran cuando QAGENT_GRABAR_JAVA=1 y la prueba real pasó sus verificaciones.

## Quinto bloque: Reviewer, reintentos y persistencia

`java_revision.py` clasifica ResultadoSandbox antes de aceptar una prueba. Una
compilación fallida en la etapa proyecto termina sin veredicto; una compilación
fallida en la etapa prueba vuelve al Generator como error_test. Timeout, OOM,
problemas de cobertura, XML ausente/inválido, suites totalmente omitidas y códigos
de salida incoherentes tampoco se convierten en bugs ni aceptaciones.
Un fallo JUnit de aserción reconocido conserva bug_detectado; no se debilita la
aserción para conseguir que pase. Los errores JUnit técnicos o desconocidos se
mantienen sin veredicto, con motivo explícito.

Los puntos opcionales clasificar_ejecucion y cobertura_de_objetivo mantienen la
lógica específica en el adaptador. Python conserva sus reglas y cálculo por
rangos. Java selecciona el contador exacto de clase/método; no sustituye datos
ausentes por el promedio de cobertura de todo el proyecto.

Se amplió review_result con motivo_sin_veredicto opcional, compatible con revisiones
anteriores. El schema impide combinarlo con accept o bug_detectado. El orquestador
persiste decision=null y su motivo y continúa con los demás objetivos. Los motivos
también están declarados en run_log. Se conservan máximo tres intentos y corte por
hash repetido: tres errores distintos permiten tres intentos; el mismo error corta
en el segundo. Las pruebas usan Reviewer y Orquestador reales con sandbox grabado.

Los controles de sintaxis usan validar_sintaxis del adaptador, de modo que Java
válido ya no se juzga con ast.parse de Python. La vista de resultados conserva el
lenguaje y explica los motivos técnicos. La vista de reporte y las exportaciones
Markdown/HTML/PDF incluyen el lenguaje, el framework real y las métricas; no se
inventa un archivo tests/test_metodo.py para una prueba JUnit. Las corridas antiguas
siguen leyéndose y el frontend conserva Python como respaldo de presentación.

La compilación real también se comprobó con dos fallos controlados en copias del
banco: un símbolo inexistente en la fuente del proyecto y otro en el JUnit. Ambos
fallaron al compilar, sin producir JUnit; el primero se clasificó como entorno con
error_compilacion_proyecto y el segundo como error_test. **2 pruebas aprobadas,
2 no seleccionadas, en 22.87 s**:

```powershell
python -m pytest tests/sandbox/test_java_ejecucion_docker.py -k compilacion_real -q -s
```

## Validación de integración controlada sobre los seis métodos

```powershell
python -m pytest tests/sandbox/test_java_corrida_docker.py -q -s
```

Resultado: **1 prueba de integración aprobada en 165.81 s**, con seis ejecuciones
reales de Maven/JUnit/JaCoCo dentro del sandbox. Usa Planner real con IA simulada,
Orquestador y Reviewer reales. El Generator y los dos puertos de validación de
#184 se sustituyen únicamente en tests/agents/java_controlado.py: aceptan las seis
fuentes fijas byte a byte y no admiten reparaciones. No se cambia completo=False
del adaptador productivo ni se habilita el proyecto en la aplicación.

| Método | Veredicto | Líneas | Ramas | Intentos |
|---|---|---|---|---|
| BancoCorrecto.sumarPrecios | accept | 100 % | 100 % | 1 |
| BancoCorrecto.aplicarDescuento | accept | 100 % | sin ramas | 1 |
| BancoCorrecto.esMayorDeEdad | accept | 100 % | 50 % | 1 |
| BancoDefectuoso.calcularPromedio | bug_detectado | 100 % | 100 % | 1 |
| BancoDefectuoso.calcularEnvio | bug_detectado | 100 % | 50 % | 1 |
| BancoDefectuoso.calcularTotalConImpuesto | bug_detectado | 100 % | sin ramas | 1 |

Solo se ejecutó una prueba recibida por método. Los once tests originales de TA-01
no se incorporaron a la ejecución. Los esperados fueron los declarados en Javadoc:
promedio 2.5, envío desde 100 igual a 0 e impuesto de 18 % sobre 100 igual a 118.
El banco conservó sus tres defectos y todos sus archivos originales.

La integración valida results.json, detalle.json y log.json con los contratos
habituales; comprueba las vistas que consume la aplicación y las exportaciones
Markdown/HTML. Se verificó además PDF con el XML real grabado y sin Docker. La
columna lenguaje vale java. Mutation Score queda null en el perfil std porque esta
corrida no solicita mutación; las ramas sin decisiones también quedan null.

Con QAGENT_GRABAR_JAVA=1, solo después de pasar todas las aserciones, la prueba
copia evidencia real a .qagent/evidencia-182/ (ignorada por Git). Sin esa variable
no escribe evidencia en el repositorio. Para reproducir la integración basta la
imagen Java ya construida: no necesita JDK ni Maven instalados en Windows.

## Límites de esta entrega

### Regresión final

La validación focalizada de adaptadores, Planner, Reviewer Java, conexión, vistas
y contratos produjo **459 aprobadas en 8.45 s**. La regresión general con
`python test.py -m "not docker and not red"` aprobó lint y formato y terminó con
**2501 aprobadas, 2 fallidas y 36 no seleccionadas en 127.08 s**. Las dos fallidas
son las ya reproducidas en la base bajo Python 3.10 en
tests/analysis/test_texto_ts.py: comprensión de diccionario frente a ast.unparse y
Generic[*Ts]. No se modificaron ni relajaron esas pruebas. El registro completo
queda en .qagent/validacion-182.txt, fuera del control de versiones.

La regresión detectó además una incompatibilidad introducida al leer objetivos
antiguos sin atributo contrato. Se corrigió el respaldo y la última regresión ya
no presenta esos fallos de almacenamiento. Una comprobación anterior también
detectó el nuevo campo lenguaje en una vista antigua: se preservó la forma
anterior cuando el registro no trae lenguaje, con respaldo visual Python.

La ejecución admite Maven de un módulo con src/main/java estándar. Un proyecto
Gradle, con padre, multimódulo o directorios distintos queda fuera de este primer
ejecutor y no se declara compatible. El POM temporal se genera en la copia
desechable; nunca se modifica el POM del usuario. Las dependencias deben estar
precargadas en la imagen derivada; no se descarga nada al ejecutar.

La integración automática desde la interfaz y con generación libre sigue
condicionada a #184 y a la integración de las ramas dependientes. La prueba con
Generator controlado verifica #182 sin afirmar que #184 ya está implementada.
No se ha validado una corrida iniciada desde la interfaz con generación Java real.
