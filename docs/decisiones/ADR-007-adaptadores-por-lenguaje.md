# ADR-007: Adaptadores por lenguaje y contratos versionados

- **Estado:** Propuesto (pendiente de revisión con los responsables de JS/TS y Java)
- **Fecha:** 2026-10-27
- **Ítem:** EN-17 (#129) — Implementar la base de adaptadores y contratos multilenguaje
- **Responsable:** Oncoy Patricio, Angel
- **Relacionado:** ADR-002 (análisis con `ast`), SPK-04 (estrategia de parser por lenguaje), EN-01 (contratos), EP-09 (endpoints)

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

La interfaz no fija un parser: cada adaptador decide cómo implementa `analizar` y `validar_sintaxis`, **según la decisión de SPK-04**, con estas condiciones que no se negocian:

1. El análisis es estático: no se importa, compila con efectos ni ejecuta el código del usuario fuera del sandbox.
2. Python sigue con `ast` (ADR-002).
3. Si un lenguaje necesita una dependencia nueva (un parser o una herramienta externa), se registra en un ADR propio antes de agregarla a `pyproject.toml`.

> **Pendiente:** enlazar aquí el documento de SPK-04 cuando esté en el repositorio.

## 4. Alternativas descartadas

| Alternativa | Por qué no |
|---|---|
| Agregar `lenguaje` y `framework` a `planner_contract.v2` como opcionales | Cambia un contrato existente y no deja distinguir un v2 de Python de uno incompleto de otro lenguaje. |
| Un Planner/Generator/Reviewer por lenguaje | Duplica la lógica compartida (reintentos, oráculo, métricas) y viola la regla de no duplicar componentes. |
| Migrar ya todo el flujo de Python a v3 | Fuera de alcance; obliga a migrar specs guardadas y arriesga la persistencia histórica. |

## 5. Consecuencias

- Cada lenguaje se desarrolla en su archivo (`javascript.py`, `java.py`) sin tocar los agentes ni los contratos.
- El alcance de AGENTS.md (solo Python) se mantiene hasta que un lenguaje esté completo y probado; entonces se actualiza junto con un ADR de ese lenguaje.
- Hay que mantener sincronizados los `enum` de los schemas con las constantes de `contracts` (lo exige una prueba).
