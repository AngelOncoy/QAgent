# EN-19 (#132) — Prototipo Java con Tree-sitter y JUnit 5

> Esta página conserva la evidencia del prototipo #132. La ampliación de análisis
> y la planificación de #181 están en [analisis-planificacion.md](analisis-planificacion.md):
> constructores, etiquetas Javadoc, decisiones, llama_a y contratos Java/JUnit 5.
> La generación JUnit y el guardrail de #184 se documentan en
> [generacion-guardrail.md](generacion-guardrail.md). El resto de esta página
> describe el estado histórico del prototipo, no la disponibilidad actual de cada extensión.

## Objetivo y estado

Prototipo independiente que analiza el banco Java TA-01 con Tree-sitter y lee
los resultados JUnit XML de Maven Surefire. Extiende `JavaAdapter` conforme a la
interfaz `LanguageAdapter` de EN-17 (#129), sin modificar Planner, Generator,
Reviewer, orquestador ni interfaz de escritorio.

No declara operativo el pipeline Java de QAgent. Los puntos de extensión de
ejecución, sandbox, cobertura, mutación y comparación de aserciones siguen
pendientes y lanzan `NoImplementado`.

## Entorno y preparación

Desde la raíz del repositorio, activar el entorno virtual Python del proyecto:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Entorno comprobado: Python 3.10, Tree-sitter 0.24.0 y gramática Java 0.23.5.
Para ejecutar el banco se utilizaron JDK Temurin 21.0.7, Maven 3.10.0, JUnit
Jupiter 5.11.4, Compiler Plugin 3.13.0 y Surefire 3.5.2. Las dependencias Python
se declaran en `pyproject.toml` y las Java en `bench_java/pom.xml`.

El análisis estático no requiere JDK, Maven, Docker ni una API de IA. La
instalación de dependencias requiere red si no están disponibles localmente.

## Exportar análisis y medición

```powershell
python -m qagent.lenguajes.prototipo_java bench_java --salida docs/java/ejemplo-analisis.json
```

El comando crea o actualiza un JSON UTF-8 con la estructura de análisis y un
bloque `medicion`. La consola muestra la ruta, los totales y el tiempo observado.
Sin `--salida`, imprime el JSON completo en la salida estándar.

- Código 0: se analizaron fuentes y no hubo errores.
- Código 1: errores parciales, carpeta vacía, ruta inexistente o fallo de escritura.
- Código 2: opciones inválidas, incluida una salida sin extensión `.json`.

El banco debe producir dos módulos, dos clases, seis métodos públicos y cero
errores. Los archivos con errores quedan registrados; no se extraen objetivos
de esos archivos. Los casos públicos sobrecargados se reportan como limitación
del prototipo para evitar confundir objetivos `Clase.metodo`.

[ejemplo-analisis.json](ejemplo-analisis.json) es una salida real de referencia.
Al repetir el comando, el bloque de medición puede cambiar. El tiempo incluye
lectura y análisis (incluida la primera carga de gramática cuando corresponda),
pero excluye el arranque de Python y la escritura del JSON. Es una sola muestra,
no un promedio ni una garantía de rendimiento. No mide memoria nativa ni CPU.

## Formato y relación con EN-17

- `lenguaje`: `java`.
- `modulos`: ruta POSIX relativa, huella SHA-256, clases, funciones y endpoints.
- `errores`: ruta, tipo, línea cuando esté disponible y mensaje.
- `resumen`: totales de módulos, clases, métodos públicos, endpoints y errores.
- `medicion`: duración, alcance y versiones del entorno del exportador.

Los métodos usan `nombre: Clase.metodo`; contienen firma, parámetros, retorno,
línea y Javadoc literal en `docstring`. No se inventan resultados esperados ni
se convierte un comentario común en Javadoc. Los tipos se conservan tal como
se escribieron: no se realiza resolución semántica de tipos o dependencias.

`JavaAdapter.objetivos(estructura)` produce `modulo`, `tipo: funcion` y `objetivo`,
como exige la base de adaptadores. La huella, firma y docstring quedan disponibles
para una futura construcción del contrato `planner_contract.v3` con
`lenguaje: java` y `framework_pruebas: junit5`. El JSON del análisis no es un
contrato del Planner: no contiene casos, oráculos deducidos ni `critical`.
Esta tarea no conecta esos datos a los agentes ni modifica los schemas existentes.

El formato completo y sus limitaciones se describen en
[la documentación de adaptadores](../../src/qagent/lenguajes/README.md).

## Verificación automatizada del prototipo

```powershell
python -m pytest tests/lenguajes tests/test_contracts_versionados.py -q
```

Se comprueban el banco real, parámetros genéricos/arrays/varargs, asociación
Javadoc con anotaciones, clases anidadas, archivos inválidos, codificación,
carpetas excluidas, sobrecargas, exportación JSON y códigos de salida.
También se ejecutan pruebas existentes de Python, JS/TS y contratos versionados.

Las pruebas de lectura XML distinguen aprobación, fallo, error y omisión;
rechazan XML inválido, inseguro, excesivo o con suites anidadas. La fixture
`tests/fixtures/java/junit5-banco.xml` proviene de la ejecución real del banco
y no exige Maven en la suite pytest.

### Regresión general verificada

En el equipo utilizado, Git descubre un repositorio padre en el directorio del
usuario al revisar los temporales de pytest. Para aislar esa interferencia,
se utilizó una variable de entorno temporal en PowerShell:

```powershell
$env:GIT_CEILING_DIRECTORIES = $env:TEMP
python test.py -m "not docker and not red"
```

Resultado observado: lint aprobado, formato aprobado (278 archivos),
1995 pruebas aprobadas y 27 excluidas en 185.94 s. Las exclusiones son las
pruebas marcadas Docker o red. No se cambiaron aserciones ni código de auditoría.
La variable limita la búsqueda de repositorios padre desde el directorio
temporal; no modifica ni elimina repositorios. No es un requisito del parser
Java: fue necesaria por la configuración Git de este equipo.

## Ejecución JUnit observada

Solo para reproducir el banco conocido TA-01:

```powershell
java -version
mvn -version
mvn -f bench_java/pom.xml clean test
```

Resultado local observado: 11 casos, 0 fallos, 0 errores, 0 omitidos y
`BUILD SUCCESS`. Ocho verifican comportamiento correcto y tres comprueban
fallos de aserción esperados por los defectos sembrados. No se ocultan errores
técnicos. Maven registró 9.836 s; las suites registraron 0.111 s y 0.016 s.

`JavaAdapter.interpretar_resultados(contenido_xml)` interpreta cada archivo
`bench_java/target/surefire-reports/TEST-*.xml` y devuelve el formato común:
total, pasaron, fallaron, errores, omitidos, duracion_s, inicio y casos.
Debe recibir contenido, no una ruta. No ejecuta Maven ni prueba aislamiento.
Mensajes y trazas se conservan, pero no se extraen aún marcos de pila Java
ni valores esperados desde el texto de errores.

## Ejecución aislada futura

La [propuesta del sandbox](sandbox-propuesto.md) contiene herramientas,
recursos propuestos y pasos de validación offline. No se ha construido ni
validado la imagen Java. La preparación y ejecución de proyectos ajenos deberá
ocurrir en aislamiento; los comandos locales de este documento son evidencia
del banco controlado, no un runner general para código del usuario.
