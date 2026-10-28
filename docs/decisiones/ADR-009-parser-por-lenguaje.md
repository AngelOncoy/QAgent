# ADR-009: Análisis estático multilenguaje — Tree-sitter frente a Parsers Nativos y Graphify

- **Estado:** Aceptado
- **Fecha:** 2026-10-26
- **Ítem:** SPK-04 — Evaluación de Graphify, tree-sitter y parsers nativos para análisis multilenguaje
- **Responsable de la investigación:** Castillo Pezo, Mateo Salvador Vincenzo
- **Relacionado:** ADR-001 (modelos y costos), ADR-002 (mapa de código y Graphify; este ADR lo extiende a los lenguajes nuevos), ADR-005 (distribución e instalador Windows), ADR-007 (adaptadores por lenguaje, EN-17), ADR-008 (orquestador y Explicador, SPK-03), ADR-010 (arquitectura del Sprint 2), EN-02 (analizador AST), EN-14 (rutas y endpoints), HU-04, HU-05, HU-06, HU-24

---

## 1. Contexto

QAgent nació con soporte exclusivo para proyectos en Python (FastAPI y funciones de biblioteca), analizados mediante el módulo nativo `ast` de la biblioteca estándar (EN-02 y EN-14). Este analizador alimenta directamente al agente **Planner**, el cual requiere una estructura determinista (`Estructura`):
1. **Identificación de objetivos:** archivos, funciones, clases, métodos y endpoints.
2. **Firmas y tipado:** nombres de parámetros, valores por defecto y tipos anotados.
3. **Docstring / Documentación:** actúa como el **oráculo formal de especificación** a partir del cual el Planner deduce valores esperados y casos de prueba sin ejecutar el código (regla inquebrantable de AGENTS.md).
4. **Complejidad y ramas:** conteo de puntos de decisión (`if`, `for`, `while`, `match`, etc.) para marcar funciones críticas (`critical: true`) y activar el análisis de mutación (HU-06).
5. **Relaciones y dependencias:** mapa de llamadas internas (`llama_a`) para que el Generator configure simulaciones (mocks).

Con la expansión de QAgent a **JavaScript**, **TypeScript** y en el futuro cercano **Java**, el sistema requiere una solución de análisis estático capaz de extraer dicha estructura en todos los lenguajes destino, manteniendo el presupuesto de tokens, tiempos de respuesta rápidos y la portabilidad de la aplicación de escritorio (`QAgent.exe` en Windows).

---

## 2. Pregunta

¿Qué herramienta o combinación de herramientas permite ampliar el análisis estático de QAgent a JavaScript, TypeScript y Java, extrayendo la información requerida por el Planner, con 0 tokens en la fase de análisis, tiempos inferiores a 50 ms por archivo y sin romper el empaquetado portable de Windows?

---

## 3. Opciones evaluadas

| Opción | Descripción |
|---|---|
| **A. Parsers Nativos Independientes** | Utilizar las herramientas oficiales de cada ecosistema: Python `ast` para Python; `@babel/parser` o `typescript` vía subproceso Node.js para JS/TS; y `JavaParser` vía subproceso JVM/JAR para Java. |
| **B. Graphify** | Utilizar Graphify para construir un grafo del repositorio completo y consultar sus relaciones mediante su capa de enriquecimiento semántico con LLM. |
| **C. Tree-sitter (Motor Unificado o Híbrido)** | Integrar la biblioteca Tree-sitter mediante sus bindings oficiales para Python (`tree-sitter`, `tree-sitter-python`, `tree-sitter-javascript`, `tree-sitter-typescript`, `tree-sitter-java`), utilizando consultas S-expression (`.scm`) para normalizar el árbol de sintaxis concreta (CST) al formato común de QAgent. |

---

## 4. Comparación Técnica y Resultados Empíricos (SPK-04)

Las tres alternativas se evaluaron sobre un banco de pruebas espejo, con implementaciones funcionalmente equivalentes de funciones de cálculo, ramas lógicas, clases, métodos y llamadas asíncronas en Python, TypeScript, JavaScript y Java.

### 4.1 Capacidad de extracción de metadatos frente a los requisitos de QAgent

| Metadato Requerido por QAgent | Parser Nativo Python (`ast`) | Parsers Nativos Externos (Node / Java) | Tree-sitter (Bindings Python) | Graphify (Estructural + LLM) |
|---|:---:|:---:|:---:|:---:|
| **Huella SHA-256 de archivo** | Sí | Sí | Sí | Sí |
| **Funciones y Métodos** | Sí | Sí | Sí | Parcial (grafo genérico) |
| **Clases y Constructores** | Sí | Sí | Sí | Sí |
| **Parámetros y Defaults** | Sí | Sí | Sí | Incompleto |
| **Tipos estáticos anotados** | Sí | Sí | Sí (nodos `type_annotation`) | No confiable / omitido |
| **Docstring / JSDoc / Javadoc (Oráculo)** | Sí | Sí | Sí (nodos `comment` adyacentes) | **No** (sintetizado en texto libre) |
| **Conteo de Ramas (`critical`)** | Sí | Sí | Sí (queries de bifurcaciones) | **No** |
| **Mapa de llamadas (`llama_a`)** | Sí | Sí | Sí (queries `call_expression`) | **Sí** (su mayor virtud) |
| **Endpoints y Decoradores** | Sí (FastAPI) | Sí (Express / Spring) | Sí (queries de decoradores) | No como contrato de prueba |

### 4.2 Métricas de Rendimiento, Tokens y Recursos (Entorno Windows AMD64)

| Herramienta | Lenguaje | Tiempo Medio | Tokens LLM | Memoria Pico | Determinista |
|---|---|:---:|:---:|:---:|:---:|
| **Parser Nativo (`ast`)** | Python | **4.36 ms** | **0** | 311 KB | Sí |
| **Parser Nativo JS (Node subproceso)** | JavaScript | 125.00 ms | **0** | 51 KB | Sí |
| **Tree-sitter (Python)** | Python | **2.78 ms** | **0** | ~180 KB | Sí |
| **Tree-sitter (TypeScript)** | TypeScript | **3.21 ms** | **0** | ~210 KB | Sí |
| **Tree-sitter (Java)** | Java | **3.23 ms** | **0** | ~220 KB | Sí |
| **Graphify** | Python | 2,445.00 ms | **1,669** | 3,200 KB | No |
| **Graphify** | TypeScript | 2,445.00 ms | **1,784** | 3,450 KB | No |

---

## 5. Análisis de Viabilidad y Distribución

1. **Riesgo Operativo de los Parsers Nativos Externos (Opción A):**
   - Para analizar JS/TS y Java mediante parsers nativos, la máquina del usuario requeriría tener instalados y configurados en el `PATH` los runtimes de **Node.js (v20+)** y un **JRE/JDK de Java (v17+)**.
   - Si se intentara empaquetar estos runtimes dentro del instalador de Windows ([`qagent.iss`](../../packaging/windows/qagent.spec)), el tamaño del instalador aumentaría en más de **250 MB**, multiplicando la superficie de fallas y vulnerabilidades.
   - La invocación mediante subprocesos (`subprocess.run`) añade una penalización de arranque de proceso de entre 100 ms y 200 ms por cada archivo, ralentizando severamente la fase de exploración en proyectos medianos.

2. **Incompatibilidad de Graphify (Opción B):**
   - Tal como se concluyó preliminarmente en el [ADR-002](ADR-002-mapa-de-codigo.md), Graphify está diseñado para exploración de código asistida por IA en agentes conversacionales, no para alimentar contratos formales de testing.
   - Su fase semántica consume más de 1,600 tokens por archivo pequeño. En un repositorio de 30 módulos consumiría ~50,000 tokens únicamente en la pantalla de "Explorar", agotando prematuramente el presupuesto del proyecto.
   - Carece de extracción determinista de docstrings literales y ramas de decisión, lo que imposibilita alimentar el oráculo del Planner y clasificar funciones críticas para mutmut.

3. **Fortalezas de Tree-sitter (Opción C):**
   - **100 % integrado en Python:** Se distribuye como ruedas binarias precompiladas (*wheels*) de C para Windows, macOS y Linux.
   - **Cero dependencias del sistema:** No requiere Node.js, Java ni compiladores externos en la máquina del usuario.
   - **Compatibilidad con PyInstaller:** Se compila limpiamente dentro del ejecutable `QAgent.exe` ([`qagent.spec`](../../packaging/windows/qagent.spec)) con un incremento de tamaño despreciable (~15 MB por todas las gramáticas combinadas).
   - **Alta velocidad:** Analiza archivos en menos de 4 milisegundos de forma puramente determinista y con 0 tokens consumidos.
   - **Extensibilidad trivial:** Incorporar nuevos lenguajes (Java, Go, C#, Rust) solo requiere instalar la gramática correspondiente (`tree-sitter-<lenguaje>`) y redactar el archivo de consulta `.scm`.

---

## 6. Decisión

**Se adopta la Opción C bajo una Arquitectura Híbrida Unificada:**

1. **Tree-sitter como motor estándar multilenguaje:**
   - Se fija la incorporación de Tree-sitter y las gramáticas de JavaScript y TypeScript en `pyproject.toml` con rangos de versión semántica compatibles:
     - `tree-sitter>=0.22.0,<0.25.0`
     - `tree-sitter-javascript>=0.21.0,<0.24.0`
     - `tree-sitter-typescript>=0.21.0,<0.24.0`
   - La gramática de Java (`tree-sitter-java`) queda reservada para su incorporación por parte del responsable del lenguaje Java en su propia issue.
   - Las gramáticas se cargan de forma diferida y centralizada mediante caché en `qagent.lenguajes.treesitter.cargar_gramatica()`.
   - Se habilita la validación estática de sintaxis (`validar_sintaxis()`) sin requerir Node.js en la máquina del usuario, cubriendo extensiones `.js`, `.mjs`, `.cjs`, `.jsx`, `.ts`, `.tsx`, `.mts` y `.cts` (ignorando `.d.ts`).
2. **Python también con tree-sitter (TA-16, #154):**
   - El analizador de Python ([`analyzer.py`](../../src/qagent/analysis/analyzer.py), [`rutas.py`](../../src/qagent/analysis/rutas.py) y [`ramas.py`](../../src/qagent/analysis/ramas.py)) usa tree-sitter con la gramática `tree-sitter-python>=0.23.0,<0.24.0`. Reemplaza a ADR-002 para Python.
   - Todo lo que lee código del usuario pasó a tree-sitter: además del analizador, el contexto del Generator (`analysis/contexto.py`), el aislamiento de manejadores para mutmut (`sandbox/manejadores.py`), las huellas y líneas de la regresión (`orchestrator/regresion.py`) y las ayudas de firmas del Planner (`agents/planner.py`). `ast` solo queda para las pruebas que genera QAgent (`analysis/laundering.py`, Reviewer, Generator y `PythonAdapter.validar_sintaxis`).
   - La base común es [`arbol_ts.py`](../../src/qagent/analysis/arbol_ts.py) (parser, nodos, parámetros, imports, errores de sintaxis y huella por función) y [`texto_ts.py`](../../src/qagent/analysis/texto_ts.py), que reproduce `ast.unparse`, `ast.get_docstring` y `ast.literal_eval` para que tipos, valores por defecto y firmas salgan con el mismo texto. El parser de Python vive en `qagent.analysis` y no en `qagent.lenguajes.treesitter`: ese paquete importa `qagent.analysis`, así que la importación sería circular.
   - **Estructura idéntica:** se comprobó con fotos tomadas con el analizador `ast` antes de migrar (`tests/analysis/casos_tree_sitter/`, `test_tree_sitter_identico.py`) y con una comparación sobre la biblioteca estándar y los paquetes instalados (ver sección 7).
   - **Errores de sintaxis:** tree-sitter recupera los errores y acepta algo de Python 2. `error_de_sintaxis()` reporta los nodos `ERROR`/`MISSING` y además `print`/`exec` de Python 2, `<>`, `except A, e`, `:=` suelto, el orden de los valores por defecto, `*` sin parámetros por nombre, argumentos posicionales después de uno por nombre, bloques vacíos y sangría inconsistente. Los archivos siguen en `errores` con su tipo y su línea; el `mensaje` ahora está en español (antes era el de CPython y ya cambiaba entre versiones).
   - **Defectos de la gramática que se corrigen en QAgent:** invierte la precedencia de `^` y `&` (las cadenas de operadores binarios se reagrupan con las precedencias de Python) y, en cadenas crudas que terminan en `\`, deja el contenido dentro del token de cierre (el contenido se calcula desde la comilla de apertura).
   - **Huella por función (`huella_objetivo`):** era el SHA-256 de `ast.dump`, que tree-sitter no puede reproducir. Ahora es la huella del árbol de tree-sitter (`version_huella_objetivo: 2` en la spec y `"version": "2"` en `mutacion/<id>.json`). Las specs viejas se migran solas si su módulo no cambió (misma huella de módulo); si cambió, la función se trata como modificada, igual que antes. La huella de **módulo** (SHA-256 del texto) no cambia.
3. **Interfaz unificada a través de los adaptadores de ADR-007:**
   - El despacho por lenguaje lo hace el registro de adaptadores (`qagent.lenguajes`, ADR-007, EN-17): `PythonAdapter.analizar()` delega en `analyzer.py`, y los adaptadores de JS/TS y Java implementan su `analizar()` con Tree-sitter. Todos producen exactamente la misma estructura de datos JSON normalizada para el Planner.
4. **Descarte definitivo de Graphify:**
   - Graphify queda descartado tanto para el análisis estático como para el mapa de llamadas, ratificando la decisión del ADR-002 en contextos multilenguaje.

---

## 7. Consecuencias

### Positivas
- **Soporte multilenguaje limpio:** QAgent podrá analizar proyectos en TypeScript, JavaScript y Java con tiempos de milisegundos y 0 tokens gastados en el análisis.
- **Independencia de runtimes externos:** El usuario final no necesita instalar Node.js ni Java para que QAgent explore y prepare pruebas en dichos proyectos.
- **Preservación de contratos:** El formato de salida generado por Tree-sitter coincide al 100 % con la `Estructura` que hoy produce `analizar_proyecto()` y consume el Planner; el contrato del Planner con lenguaje y framework es `planner_contract.v3` (ADR-007).
- **Integración fluida en CI/CD y empaquetado:** `tree-sitter` se empaqueta sin fricción en el instalador de Windows de `packaging/windows/`.

### Mitigaciones y Trabajo Futuro
- **Mapeo de Queries Tree-sitter:** Se deben mantener archivos de consulta `.scm` por cada lenguaje para capturar de forma robusta las asociaciones entre comentarios JSDoc/Javadoc y sus respectivas funciones/métodos.
- **Extracción de endpoints Express y Spring Boot:** Se implementarán consultas específicas sobre decoradores y llamadas a routers (`app.get()`, `@GetMapping`) de forma análoga a lo desarrollado en EN-14 para FastAPI.
- **Dependencias:** `tree-sitter`, `tree-sitter-javascript`, `tree-sitter-typescript` y `tree-sitter-python` quedan fijadas en `pyproject.toml`. Hay ruedas `abi3` de `tree-sitter-python` 0.23.6 para Windows, macOS y Linux, y de `tree-sitter` 0.24 para Python 3.10 a 3.13.
- **Reproducibilidad de las cifras:** el banco espejo y los scripts de medición del spike se preservan en `bench/multilenguaje/`.
- **Python con tree-sitter:** hecho en TA-16 (#154), con la estructura idéntica a la de `analizar_proyecto()` (ver sección 6, punto 2). En las mediciones de TA-16 **no** se repitió la ventaja de la sección 4.2: solo el parseo tarda 2,71 ms por archivo con tree-sitter frente a 1,70 ms con `ast.parse`, y el análisis completo de `src/qagent` (84 archivos) unos 810 ms frente a 465 ms, porque los recorridos del árbol se hacen nodo por nodo desde Python. Sigue en milisegundos y la ganancia que se buscaba es tener un solo parser. Si hace falta acelerar, el camino es usar consultas de tree-sitter (corren en C), lo que exige subir el mínimo de `tree-sitter` a 0.23 (su API cambió). Las cifras se repiten con `python scripts/medir_analizador.py bench src/qagent`.
