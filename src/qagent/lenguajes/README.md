# Adaptadores por lenguaje (EN-17)

Todo lo que depende del lenguaje del código del usuario vive aquí. El orquestador,
el Planner, el Generator y el Reviewer son compartidos: piden un adaptador al
registro y hablan con él y con los contratos, nunca con un parser o un runner
concreto. Decisión completa en `docs/decisiones/ADR-007-adaptadores-por-lenguaje.md`.

| Archivo | Contenido | Estado |
|---|---|---|
| `base.py` | `LanguageAdapter`, `AdaptadorEnDesarrollo`, `Deteccion`, `EntornoSandbox`, `NoImplementado` | Estable |
| `registro.py` | `Registro`, `listar_archivos` | Estable |
| `python.py` | `PythonAdapter` (delega en el flujo actual) | Completo |
| `javascript.py` | `JavaScriptAdapter`, `TypeScriptAdapter` | Solo detecta |
| `java.py` | `JavaAdapter` | Detecta, analiza, valida sintaxis y lee JUnit XML (prototipo EN-19) |

## Uso

```python
from qagent.lenguajes import adaptador_de_contrato, adaptador_para, detectar_lenguaje

detectar_lenguaje("ruta/al/proyecto")
# [Deteccion(lenguaje='typescript', archivos=12, marcadores=('tsconfig.json',), confianza=0.8), ...]

adaptador = adaptador_para("python")
# Igual que analizar_proyecto, más "lenguaje".
estructura = adaptador.analizar("ruta/al/proyecto")
# [{"modulo", "tipo", "objetivo"}, ...]
adaptador.objetivos(estructura)
# ["pytest", "/work/tests", "--cov=tienda.precios", ...]
adaptador.comando_pruebas("tienda.precios")

# v2 -> PythonAdapter; v3 -> según "lenguaje".
adaptador_de_contrato(contrato)
```

Contratos:

```python
from qagent import contracts

contracts.validar_versionado(contracts.FAMILIA_PLANNER, contrato)  # acepta v2 y v3
contracts.normalizar_planner(contrato_v2)  # copia en v3 (python + pytest)
```

## La interfaz

| Operación | Qué devuelve | Notas |
|---|---|---|
| `detectar(archivos)` | `Deteccion` o `None` | Ya implementada con `extensiones` y `marcadores`. Se puede sobrescribir `es_fuente` (TypeScript ignora `.d.ts`). |
| `analizar(raiz)` | `{"lenguaje", "modulos", "errores", "resumen"}` | Misma forma que `qagent.analysis.analizar_proyecto`. **Estático.** |
| `objetivos(estructura)` | `[{"modulo", "tipo", "objetivo"}]` | Ya implementada: recorre `funciones` y `endpoints`. |
| `comando_pruebas(modulo, framework=None)` | `list[str]` | Usa `elegir_framework()` para validar el framework del contrato. |
| `entorno_sandbox()` | `EntornoSandbox` | Imagen, herramientas base, carpetas e informe. |
| `interpretar_resultados(informe)` | `dict` con `total`, `pasaron`, `fallaron`, `errores`, `omitidos`, `duracion_s`, `inicio`, `casos` | Jest (`jest-junit`), Vitest (`--reporter=junit`) y Surefire de JUnit 5 también escriben JUnit XML: conviene reutilizar `qagent.sandbox.informe_pytest`. |
| `validar_sintaxis(codigo)` | `list[str]` (vacía = válido) | Parsear, no ejecutar. |
| `comparar_aserciones(original, reparado)` | objeto con `es_laundering` y `resumen` | Ver las 7 reglas de `qagent.analysis.laundering`. |
| `leer_cobertura(dir_salida)` | `dict` en el formato JSON de coverage.py (`files`, `totals`) o `None` | Es el formato que lee el Reviewer. Cada lenguaje convierte el suyo (v8, JaCoCo) a este. |
| `archivo_de_prueba(objetivo)` | nombre del archivo, sin carpetas | Valor de `archivo` en `generated_test.v2` (`test_generado.py`, `precios.test.ts`, `PreciosTest.java`). |
| `comando_mutacion(modulo, funciones)` | `ComandoSandbox` (comando y variables de entorno) | Solo sobre funciones `critical: true`: mutmut, Stryker o PIT. |

## Cómo implementar un lenguaje

1. Trabaja solo en tu archivo (`javascript.py` o `java.py`) y en `tests/lenguajes/`.
2. Reemplaza los métodos de `AdaptadorEnDesarrollo` **uno por uno**; los que falten siguen lanzando `NoImplementado`.
3. `analizar` debe devolver objetivos cuyo `objetivo` cumpla el contrato v3: un nombre (`calcularDescuento`, `Precios.calcular`) o `MÉTODO /ruta` para endpoints.
4. El parser es **tree-sitter** (decisión de SPK-04, ver ADR-007, sección 3): úsalo para `analizar` y para `validar_sintaxis` (nodos `ERROR` del árbol). Su dependencia y la gramática de tu lenguaje se agregan a `pyproject.toml` en tu tarea. Python sigue con `ast` hasta su propia migración.
5. Si cambian los lenguajes o frameworks admitidos, actualiza a la vez los `enum` de `planner_contract.v3` / `generated_test.v2` y `contracts.FRAMEWORKS_PRUEBAS` / `FRAMEWORKS_APP` (una prueba lo exige).

Reglas que no se rompen (AGENTS.md): nada del usuario se ejecuta fuera del sandbox, el valor esperado sale del contrato y nunca de ejecutar el código, y este paquete no importa `qagent.app` ni `webview`.

## Revisión con los responsables de JS/TS y Java

### Análisis Java del prototipo EN-19

`JavaAdapter().analizar("bench_java")` devuelve un diccionario serializable como
JSON con `lenguaje`, `modulos`, `errores` y `resumen`, según la interfaz de EN-17.
No ejecuta ni compila las fuentes. Utiliza `tree-sitter-java==0.23.5`.

- Cada módulo contiene `ruta` relativa POSIX, `huella` SHA-256 del texto con
  saltos normalizados, `clases`, `funciones` y `endpoints` (vacío en el prototipo).
- Cada clase contiene `nombre`, `tipo` de declaración, `linea` desde 1 y
  `docstring` con Javadoc literal o `null`.
- Cada función pública contiene `nombre` como `Clase.metodo`, `clase`, `linea`,
  `firma`, `parametros`, `retorno`, `docstring`, `tipada` y `es_async: false`.
- Cada parámetro conserva `nombre`, `tipo` escrito y `por_defecto: null`.
  Se incluyen genéricos, arrays y varargs; no se resuelven imports ni tipos.
- `objetivos(estructura)` produce `modulo`, `tipo: funcion` y `objetivo`,
  compatibles con los identificadores de los contratos versionados de EN-17.
  La estructura estática no es un contrato del Planner ni propone valores esperados.
- Los archivos con errores de sintaxis, lectura o sobrecargas no admitidas se
  reportan en `errores` con `ruta`, `tipo`, `linea` (puede ser `null`) y `mensaje`.
  No se extraen objetivos de esos archivos y se continúa con los demás.

El banco TA-01 debe producir dos módulos, dos clases y seis métodos públicos,
sin errores. Se excluyen `src/test`, las carpetas ignoradas por el registro
(incluido `target`) y las fuentes que son enlaces simbólicos.

`JavaAdapter().interpretar_resultados(contenido_xml)` lee un informe Surefire
(`testsuite`) o varias suites planas (`testsuites`) reutilizando el lector común
de EN-17. Recibe contenido, no una ruta. Devuelve `total`, `pasaron`, `fallaron`,
`errores`, `omitidos`, `duracion_s`, `inicio` y `casos`. Conserva mensajes y
trazas Java, pero no extrae todavía sus marcos de pila ni el tipo de excepción
del atributo XML `type`; tampoco deduce valores esperados desde mensajes.
Un fallo de aserción sigue siendo fallo y un error técnico sigue siendo error.
Las detecciones controladas del banco aparecen como éxitos porque así las
registró JUnit, no porque el lector haya reclasificado un fallo.

La duración XML es la suma de las duraciones de suites. No incluye toda la
compilación o el arranque de Maven. El lector rechaza XML vacío, mal formado,
de tamaño excesivo, con entidades, con raíz ajena a JUnit o suites anidadas.
La fixture `tests/fixtures/java/junit5-banco.xml` preserva suites y casos de la
ejecución local del banco; no requiere Maven para verificar su interpretación.

Limitaciones de esta etapa: no extrae constructores, métodos no públicos,
clases locales o anónimas, llamadas, ramas, cobertura ni endpoints Spring.
Las sobrecargas públicas de una misma clase se rechazan porque `Clase.metodo`
todavía no distingue sus firmas. `validar_sintaxis` no reemplaza `javac`:
un árbol válido no demuestra que los tipos o dependencias sean correctos.
Los puntos de ejecución y seguridad no implementados siguen lanzando
`NoImplementado`; el prototipo no habilita el pipeline Java de la aplicación.

La [propuesta del sandbox Java](../../../docs/java/sandbox-propuesto.md) registra
versiones, tiempos locales, recursos propuestos y validaciones todavía no
realizadas para ejecutar JUnit en Docker sin red (EN-19).

Antes de cerrar EN-17 conviene revisar juntos:

- [ ] ¿Alcanzan `lenguaje`, `framework_pruebas` y `framework_app` del contrato v3? ¿Falta algún framework (Mocha, TestNG…)?
- [ ] ¿El `objetivo` como `Clase.metodo` sirve para Java y para métodos de clases en TS?
- [ ] ¿Los `origen` del oráculo (`docstring` incluye JSDoc y Javadoc) bastan?
- [ ] ¿La forma de `analizar` (módulos → funciones/endpoints) es suficiente para su parser?
- [ ] ¿El runner de cada lenguaje puede producir JUnit XML para reutilizar `interpretar_resultados`?
- [ ] ¿Qué imagen de sandbox necesita cada lenguaje (Node, JDK + Maven/Gradle sin red)?
