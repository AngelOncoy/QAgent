# Banco de Pruebas Espejo Multilenguaje (SPK-04)

Este conjunto de referencia contiene implementaciones funcional y estructuralmente equivalentes en **Python**, **JavaScript**, **TypeScript** y **Java**, diseñadas específicamente para evaluar y comparar herramientas de análisis estático multilenguaje.

Sustenta las decisiones técnicas del **ADR-009** (SPK-04: *Análisis estático multilenguaje — Tree-sitter frente a Parsers Nativos y Graphify*).

---

## 1. Estructura de Equivalencia

Cada archivo implementa exactamente los mismos componentes de código para garantizar paridad sintáctica y semántica:

| Componente | Tipo | Propósito en la Evaluación de QAgent |
| :--- | :--- | :--- |
| `calcular_descuento` / `calcularDescuento` | Función pura | Extracción de docstring/JSDoc/Javadoc, tipos de entrada/salida y validación básica de precondiciones. |
| `clasificar_edad` / `clasificarEdad` | Función con ramas | Conteo de bifurcaciones lógicas (`if`/`elif`/`else`) para determinar complejidad ciclomática y marcado `critical: true`. |
| `calcular_estadisticas` / `calcularEstadisticas` | Función de agregación | Manejo de estructuras de colecciones (listas/arrays), bucles (`for`) y retornos estructurados (diccionarios/objetos/mapas). |
| `GestorImpuestos` | Clase con estado | Extracción de clases, constructores con valores por defecto, métodos de instancia y mapa de llamadas internas (`llama_a`). |
| `registrar_operacion` / `registrarOperacion` | Función asíncrona | Detección de funciones `async`/`await` y tipos de retorno asíncronos (`Promise` / `Task`). |

---

## 2. Archivos del Banco

- [`calculadora.py`](calculadora.py): Implementación en Python 3.10+ con type hints completos y docstrings estilo Google.
- [`calculadora.ts`](calculadora.ts): Implementación en TypeScript con interfaces y anotaciones JSDoc.
- [`calculadora.js`](calculadora.js): Implementación en JavaScript (Node ES6 / CommonJS) con JSDoc tipado.
- [`Calculadora.java`](Calculadora.java): Implementación en Java 17+ con Javadoc estándar y métodos tipados.
- [`react/`](react/): proyecto React con TypeScript para las pruebas de componentes (#171). No entra en la medición de SPK-04:

| Archivo | Qué prueba |
| :--- | :--- |
| `src/Boton.tsx` | Componente correcto: props de `interface` con opcional, valor por defecto y evento `onPulsar` documentado. Se aprueba. |
| `src/Insignia.tsx` | Bug sembrado: el JSDoc promete «Agotado» y muestra «Sin stock». Exportación por defecto. Se detecta. |
| `src/Libre.tsx` | Sin props tipadas ni JSDoc: queda omitido como «sin resultado esperado verificable». |
| `src/formato.ts` | Función de lógica con `@example`, en el mismo proyecto. |

Las respuestas grabadas del Planner están en `tests/lenguajes/test_banco_react.py`, y la corrida real en Docker, en `tests/sandbox/test_react_corrida_docker.py`.

---

## 3. Cómo Ejecutar la Medición

Para reproducir las cifras de rendimiento y metadatos de las secciones 4.1 y 4.2 del **ADR-009**:

```bash
python bench/multilenguaje/medir_parsers_spk04.py
```

Opciones disponibles:
- `-i`, `--iteraciones <N>`: Número de iteraciones para promediar tiempos (por defecto `50`).
- `-o`, `--salida <ruta>`: Ruta personalizada para el JSON de resultados (por defecto `bench/multilenguaje/resultados_spk04.json`).

También se puede invocar con el script compatible:
```bash
python bench/multilenguaje/spk04_benchmark.py
```

### Condiciones de Ejecución
- **0 tokens LLM consumidos** en las herramientas integradas.
- **Sin conexión a internet ni llamadas de red**.
- **Sin necesidad de Docker**.
- Escribe sus resultados estructurados en [`resultados_spk04.json`](resultados_spk04.json) con metadatos del entorno, fecha, versiones de librerías y tiempos.

### Dependencias y Herramientas Opcionales
- **Python `ast` y Tree-sitter (Python, JS, TS, Java):** Se ejecutan directamente con las dependencias fijadas en `pyproject.toml` (100 % Python/C embebido, sin dependencias del sistema).
- **Node.js runtime (`node`):** Opcional. Si está disponible en el `PATH` del sistema, ejecuta la medición del parser nativo de JavaScript vía subproceso; si no se encuentra, se documenta como no disponible localmente sin interrumpir el resto de la suite.
- **Graphify:** Herramienta externa descartada formalmente en ADR-002 y ADR-009. Sus cifras se preservan en los resultados como referencia empírica del spike original.
