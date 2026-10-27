# ADR-007: Adaptadores por lenguaje y contratos versionados

- **Estado:** Propuesto (pendiente de revisión con los responsables de JS/TS y Java). Parser decidido en SPK-04: tree-sitter.
- **Fecha:** 2026-10-27
- **Ítem:** EN-17 (#129) — Implementar la base de adaptadores y contratos multilenguaje
- **Responsable:** Oncoy Patricio, Angel
- **Relacionado:** ADR-002 (análisis con `ast`), ADR-008 (orquestador y Explicador, SPK-03), ADR-009 (parser por lenguaje, SPK-04), EN-01 (contratos), EP-09 (endpoints)

## 1. Contexto

QAgent se construyó para Python: el analizador usa `ast`, el Generator escribe pytest, el sandbox ejecuta pytest con coverage y el Reviewer lee `junit.xml` y busca Assertion Laundering en el AST de Python. Para soportar JavaScript, TypeScript y Java sin duplicar el Planner, el Generator, el Reviewer ni el orquestador, hay que separar **lo que depende del lenguaje** de **lo que es compartido**, y los contratos tienen que poder decir de qué lenguaje y framework es cada objetivo.

Restricciones de la issue: no modificar los contratos existentes, no comprometer las specs y corridas ya guardadas en `.qagent/` y permitir que cada lenguaje se desarrolle en paralelo.

## 2. Decisión

### 2.1 Un adaptador por lenguaje

Paquete nuevo `src/qagent/lenguajes/` con la interfaz `LanguageAdapter` (clase abstracta) y un registro:

| Operación | Tipo | Qué hace |
|---|---|---|
| `detectar(archivos)` | común | Cuenta archivos fuente y marcadores de proyecto. Pura: recibe rutas, no lee el disco. |
| `analizar(raiz)` | abstracta | Análisis **estático**; devuelve la misma forma que `analizar_proyecto` más `lenguaje`. |
| `objetivos(estructura)` | común | Funciones y endpoints que se pueden probar. |
| `comando_pruebas(modulo, framework)` | extensión | Comando que corre el sandbox (pytest, jest, vitest, junit5). |
| `entorno_sandbox()` | extensión | Imagen, herramientas, carpetas e informe del sandbox. |
| `interpretar_resultados(informe)` | extensión | Informe del runner → totales y casos (forma de `review_result`). |
| `validar_sintaxis(codigo)` | extensión | Parsea el test generado sin ejecutarlo. |
| `comparar_aserciones(original, reparado)` | extensión | Detecta Assertion Laundering. |

`Registro` guarda un adaptador por lenguaje, comprueba que su lenguaje y frameworks existan en los contratos y elige el adaptador por nombre, por carpeta (`detectar`) o por contrato (`adaptador_de_contrato`, acepta v2 y v3).

- **Python** (`PythonAdapter`) está completo y **solo delega** en el código actual (`analizar_proyecto`, `comando_pytest`, `parsear_junit`, `comparar_aserciones`). Las pruebas verifican que da exactamente lo mismo.
- **JavaScript, TypeScript y Java** son esqueletos (`AdaptadorEnDesarrollo`): ya detectan; el resto lanza `NoImplementado` hasta que su responsable lo implemente.

### 2.2 Contratos versionados, sin tocar los existentes

| Familia | Versión actual (sin cambios) | Versión nueva |
|---|---|---|
| `planner_contract` | v2 (`planner_contract.v2.schema.json`) | **v3**: + `lenguaje`, `framework_pruebas`, `framework_app` (obligatorio en endpoints) |
| `generated_test` | v1 (`generated_test.schema.json`) | **v2**: + `lenguaje`, `framework_pruebas`, `archivo` opcional |

- El schema v3 rechaza las combinaciones que no corresponden (java + pytest, typescript + spring…). Las combinaciones válidas están en `contracts.FRAMEWORKS_PRUEBAS` y `contracts.FRAMEWORKS_APP`, y una prueba exige que coincidan con los `enum` de los schemas.
- `validar_versionado(familia, dato)` elige el schema por el campo `version`.
- `normalizar_planner()` / `normalizar_generated_test()` pasan un v2/v1 a la versión nueva **en memoria** (un v2 es siempre Python + pytest, y FastAPI si es endpoint) sin modificar el original.
- `review_result`, `detalle` y `run_log` no cambian: no dependen del lenguaje (el comando y la imagen ya viajan en `ejecucion.entorno`).

### 2.3 Lo que no cambia

El Planner sigue produciendo v2, las specs se guardan y leen como v2 y el orquestador no usa todavía el registro. Migrar el flujo de Python a v3 y conectar el registro al orquestador son tareas aparte (fuera de alcance de #129).

## 3. Estrategia de parser (SPK-04)

**Decisión de SPK-04: tree-sitter** (bindings de Python sobre C) es el parser de los lenguajes nuevos. La decisión completa, con sus mediciones, está en [ADR-009](ADR-009-parser-por-lenguaje.md) (SPK-04). La interfaz no fija el parser: `analizar` y `validar_sintaxis` lo usan dentro de cada adaptador.

Resumen de por qué tree-sitter:

- Es estático, determinista y no gasta tokens, como exigen las métricas reproducibles y la caché por huella (HU-24).
- Un solo parser sirve para JS, TS y Java, y no requiere Node ni un JDK en la PC del usuario (el parser nativo de JS sí, y es unas 40 veces más lento).
- Detecta errores de sintaxis sin ejecutar nada (nodos `ERROR` del árbol), lo que sirve para `validar_sintaxis`.

Condiciones que no se negocian:

1. El análisis es estático: no se importa, compila con efectos ni ejecuta el código del usuario fuera del sandbox.
2. **Python sigue por ahora con `ast`** (ADR-002). Su migración a tree-sitter es una tarea aparte y debe dar exactamente la misma estructura (las pruebas de `tests/lenguajes/test_python.py` ya la comparan con `analizar_proyecto`).
3. tree-sitter y sus gramáticas se agregan a `pyproject.toml` en la tarea de cada lenguaje, no en EN-17: esta base no suma dependencias que todavía nadie usa.

### 3.1 Alternativa evaluada: elegir el parser según el tamaño del proyecto

Se propuso contar las líneas de código del proyecto y usar Graphify por encima de un umbral (por ejemplo, un millón de líneas) y tree-sitter por debajo. **Se descarta por ahora:**

- **El costo de tree-sitter crece en línea recta y es bajo.** Con ~3 ms por archivo (ADR-009), un proyecto de un millón de líneas (del orden de 10 000 archivos) se analiza en unos 30 s, una sola vez por huella. Graphify tarda ~2.4 s por archivo y además gasta tokens, así que en ese mismo proyecto tardaría horas.
- **Graphify no es determinista y envía código a un LLM.** Dos análisis del mismo proyecto podrían dar estructuras distintas, lo que rompe la caché por huella y la comparación entre corridas, y saca código de la PC del usuario (ADR-002).
- **La ventaja de Graphify en repositorios grandes no aplica a QAgent.** Sirve para que un asistente navegue un repositorio sin leerlo entero. QAgent ya trabaja por módulo y por función, y la persona elige qué módulos probar.
- **Dos parsers según un umbral duplican el trabajo:** dos salidas que deben ser equivalentes, el doble de pruebas y un umbral arbitrario en el que un proyecto cambia de resultado por una línea.

Si algún día un proyecto real muestra que el análisis es el cuello de botella, el camino es hacerlo incremental (solo los archivos cuya huella cambió) antes que cambiar de herramienta. La idea queda registrada para revisarla con esa medición.

## 4. Alternativas descartadas

| Alternativa | Por qué no |
|---|---|
| Agregar `lenguaje` y `framework` a `planner_contract.v2` como opcionales | Cambia un contrato existente y no deja distinguir un v2 de Python de uno incompleto de otro lenguaje. |
| Un Planner/Generator/Reviewer por lenguaje | Duplica la lógica compartida (reintentos, oráculo, métricas) y viola la regla de no duplicar componentes. |
| Graphify o el parser nativo de cada lenguaje (subproceso de Node, JDK) | No deterministas o lentos y con dependencias en la PC del usuario (sección 3, mediciones de SPK-04). |
| Elegir el parser según las líneas de código del proyecto | Dos parsers con un umbral arbitrario y sin beneficio medido (sección 3.1). |
| Migrar ya todo el flujo de Python a v3 | Fuera de alcance; obliga a migrar specs guardadas y arriesga la persistencia histórica. |

## 5. Consecuencias

- Cada lenguaje se desarrolla en su archivo (`javascript.py`, `java.py`) sin tocar los agentes ni los contratos.
- El alcance de AGENTS.md (solo Python) se mantiene hasta que un lenguaje esté completo y probado; entonces se actualiza junto con un ADR de ese lenguaje.
- Hay que mantener sincronizados los `enum` de los schemas con las constantes de `contracts` (lo exige una prueba).
