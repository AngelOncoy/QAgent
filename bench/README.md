# Bancos de Pruebas y Scripts de Medición de QAgent (`bench/`)

Este directorio contiene los bancos de pruebas empíricos y los scripts de medición que sustentan las decisiones arquitecturales de QAgent registradas en los ADRs del proyecto (**ADR-008**, **ADR-009**, **ADR-012** y **GitHub #196**).

---

## Estructura del Directorio

```
bench/
├── banco_mvp.py                     # Banco de 6 funciones Python (3 con bugs sembrados)
├── bugs.md                          # Documentación detallada de los bugs sembrados en banco_mvp.py
├── medir_orquestador_spk03.py       # Script de medición de SPK-03 / ADR-008 (orquestador determinista)
├── resultados_spk03.json            # Resultados de la última medición de SPK-03
├── multilenguaje/                   # Banco de pruebas espejo en 4 lenguajes (SPK-04 / ADR-009)
│   ├── README.md                    # Descripción de la equivalencia sintáctica y semántica
│   ├── calculadora.py               # Implementación en Python 3.10+
│   ├── calculadora.js               # Implementación en JavaScript (Node ES6)
│   ├── calculadora.ts               # Implementación en TypeScript
│   ├── Calculadora.java             # Implementación en Java 17+
│   ├── medir_parsers_spk04.py       # Script de medición de parsers nativos vs tree-sitter vs Graphify
│   ├── spk04_benchmark.py           # Entrada compatible para medir_parsers_spk04.py
│   └── resultados_spk04.json        # Resultados de la última medición de SPK-04
└── dependencias/                    # Banco modular de dependencias entre archivos (SPK #196)
    ├── README.md                    # Explicación del caso de dependencias entre módulos
    ├── modelos.py, api.py, ...      # Módulos interconectados
    └── medir_dependencias_spk196.py # Script de medición de contexto y grafo de dependencias
```

---

## Cómo Ejecutar las Mediciones

Todos los scripts corren de forma determinista, **con 0 tokens consumidos**, **sin conexión a internet** y **sin requerir Docker**:

### 1. Medición de Coordinación del Orquestador (ADR-008, Sección 4.1)

Mide la máquina de estados determinista sobre `bench/banco_mvp.py` con la IA simulada (`FakeLLMClient`) y ejecuciones grabadas (`EjecutorGrabado`):

```bash
python bench/medir_orquestador_spk03.py
```

**Cifras del ADR-008 que reproduce:**
- **Traza de estados:** `planificar → (generar → ejecutar_revisar) × 6 → fin` (14 transiciones).
- **Veredictos:** 3 `bug_detectado` y 3 `accept`, todos resueltos en el intento 1.
- **Llamadas al LLM:** Planner 1, Generator 6, Reviewer 0 (las reglas deterministas resuelven todo sin consultar a la IA).
- **Tamaño de prompts:** tamaño en caracteres por agente.
- **Tiempo de coordinación:** latencia del orquestador en segundos en N repeticiones (por defecto 5).
- **Reproducibilidad:** 5 de 5 corridas idénticas (mismas decisiones, intentos, laundering y huellas de tests generados).
- **Salida estructurada:** guarda los datos en `bench/resultados_spk03.json`.

---

### 2. Medición de Parsers Multilenguaje (ADR-009, Secciones 4.1 y 4.2)

Evalúa el rendimiento en tiempo, memoria pico (`tracemalloc`) y capacidad de extracción de metadatos entre el parser nativo de Python (`ast`), Tree-sitter multilenguaje, parsers externos (Node.js) y Graphify:

```bash
python bench/multilenguaje/medir_parsers_spk04.py
```

**Cifras del ADR-009 que reproduce:**
- **Tabla 4.2 (Rendimiento, Tokens y Recursos):**
  - `ast` de Python vs `tree-sitter-python`.
  - `tree-sitter-typescript` y `tree-sitter-javascript`.
  - `tree-sitter-java`.
  - Parser nativo de JavaScript con subproceso Node.js (opcional: si Node no está en el `PATH`, documenta la línea base de referencia).
  - Graphify (herramienta externa descartada: registra la línea base de referencia de 2 445 ms y >1 600 tokens).
- **Tabla 4.1 (Capacidad de extracción de metadatos):** verificación de oráculo docstring/JSDoc/Javadoc, firmas, tipos, ramas de decisión y mapa de llamadas.
- **Salida estructurada:** guarda los datos en `bench/multilenguaje/resultados_spk04.json`.

---

### 3. Medición del Grafo de Dependencias (SPK-196 / GitHub #196 / ADR-012)

Evalúa el impacto del análisis estático de dependencias entre módulos sobre el contexto del Generator mediante tree-sitter (`grafo_imports.py`) frente a Graphify:

```bash
python bench/dependencias/medir_dependencias_spk196.py
```

**Cifras del ADR-012 que reproduce:**
- **Tasa de aprobación:** 100 % (5 de 5) con `grafo_imports` frente a 60 % (3 de 5) sin grafo inter-archivo.
- **Dependencias sin simular:** 0 con `grafo_imports` frente a 2 sin grafo.
- **Tiempo de análisis:** ~27–36 ms (tree-sitter puro, sin subprocesos ni binarios en la máquina del usuario).
- **Consumo de tokens en análisis:** 0 tokens.
- **Salida estructurada:** guarda los datos en `docs/evidencias/spk-196/resultados-benchmark.json`.

---

## Reglas de Mantenimiento

1. **Aislamiento de la suite regular:** Los scripts de `bench/` son herramientas de medición empírica y reproducibilidad; **no** forman parte de la suite regular de pruebas unitarias (`python test.py` ni `pytest`).
2. **Exclusión de Ruff:** `bench/` está excluido de las reglas de formateo y linting de Ruff en `pyproject.toml` porque contiene bugs sembrados y patrones intencionales para evaluar a los agentes. No obstante, los scripts de medición siguen las buenas prácticas del proyecto (type hints y docstrings en español).
3. **Persistencia atómica:** Los scripts escriben sus resultados en archivos JSON versionables que registran la fecha, la arquitectura, el sistema operativo y las versiones de las herramientas para garantizar trazabilidad científica.
