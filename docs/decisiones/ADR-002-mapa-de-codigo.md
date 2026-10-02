# ADR-002: Mapa del código — Graphify frente al análisis con `ast`

- **Estado:** Aceptado (evaluación documental) · medición empírica pendiente (ver sección 7)
- **Fecha:** 2026-09-30
- **Ítem:** SPK-02 — Evaluar Graphify frente al análisis con ast
- **Responsable de la investigación:** Oncoy Patricio, Angel
- **Revisión:** Castillo Pezo, Mateo (responsable de EN-02 y EN-14)
- **Relacionado:** EN-02 (analizador AST), EN-14 (analizador de rutas FastAPI), HU-04, HU-05, HU-24, ADR-001

## 1. Contexto

El Planner es el agente más caro de QAgent: con Claude Opus 5.5 representa ~80 % del gasto de una corrida (ADR-001). Todo lo que reduzca la cantidad de código que lee baja el costo total.

Un integrante propuso usar **Graphify**, una herramienta que convierte un repositorio en un grafo de conocimiento (funciones, clases, llamadas e imports) para que un asistente de IA consulte el grafo en lugar de leer los archivos, y así gaste menos tokens.

Con la incorporación de pruebas de endpoints FastAPI (EP-09), el análisis debe extraer además rutas, métodos, modelos Pydantic, `response_model` y `status_code`, y el Planner necesita saber qué funciones del proyecto llama cada función o endpoint para decidir qué simular.

## 2. Pregunta

¿Graphify aporta a QAgent algo que el análisis estático con el módulo `ast` de Python no dé, para funciones y endpoints FastAPI, con un costo razonable en tokens, tiempo y dependencias?

## 3. Opciones evaluadas

| Opción | Descripción |
|---|---|
| **A. Graphify reemplaza a EN-02** | Graphify genera toda la estructura del código y un traductor la convierte a `estructura.json`. |
| **B. Graphify como complemento** | EN-02 sigue con `ast`; Graphify solo aporta el mapa de llamadas. |
| **C. Solo `ast`, con mapa de llamadas propio** | EN-02 y EN-14 con `ast`, y se agrega el campo `llama_a` recorriendo los nodos `ast.Call`. |

## 4. Cómo funciona Graphify

1. **Paso estructural:** usa tree-sitter para parsear el código a un AST en local, sin LLM ni envío de datos. Extrae llamadas, herencia e imports.
2. **Paso semántico:** procesa documentación y archivos Markdown **con un LLM** para enlazar conceptos de diseño con el código. Este paso consume tokens.
3. **Salidas:** `graph.json` (grafo), `GRAPH_REPORT.md` (resumen) y `graph.html` (visualización).

Está pensado para asistentes de IA que **exploran o buscan** en un repositorio desconocido. Sus cifras publicadas de ahorro (de 49x a 70x menos tokens) corresponden a repositorios grandes.

## 5. Comparación

| Criterio | Graphify | `ast` (opción C) |
|---|---|---|
| Firmas y tipos | Sí, genérico | Sí, completo (`ast.unparse` de anotaciones) |
| Docstrings (oráculo del Planner) | No como campo propio | Sí (`ast.get_docstring`) |
| Número de ramas (para marcar funciones críticas, HU-06) | No | Sí (conteo de `If`, `For`, `While`, `Try`, `Match`, `BoolOp`, `IfExp`) |
| Rutas FastAPI (método, ruta) | No: ve una llamada genérica al decorador | Sí: lee `@app.<método>` y `@router.<método>` |
| `response_model`, `status_code`, modelos Pydantic | No | Sí: argumentos del decorador y clases `BaseModel` |
| Mapa de llamadas (`llama_a`) | **Sí, es su fortaleza** | Sí, recorriendo `ast.Call` y resolviendo por nombre (ver sección 8) |
| Lenguajes | Muchos (tree-sitter) | Solo Python, que es el alcance de QAgent |
| Tokens para construir el mapa | 0 en el paso estructural; **> 0 en el paso semántico** | 0 |
| Dependencias nuevas | Graphify + `uv` + tree-sitter | Ninguna (biblioteca estándar) |
| Formato de salida | Grafo del repositorio completo | `estructura.json` por módulo, igual al contrato |
| Integración con la caché de specs (HU-24) | Requiere sincronizar la regeneración del grafo con el hash | Directa: mismo SHA-256 por módulo |

### Efecto en el costo del Planner

QAgent **no busca** en el código: **recorre** cada función elegida y necesita su firma, sus tipos y su docstring para diseñar los casos. Un grafo no evita leer esa información; es la materia prima del Planner.

Lo que controla el costo en un repositorio grande ya está en el backlog:

- **HU-05:** elegir qué módulos y funciones entran en la corrida.
- **HU-24:** reutilizar el spec si el SHA-256 del módulo no cambió.
- **HU-06:** mutation testing solo en funciones críticas.

La idea de Graphify que sí reduce tokens es enviar al Planner **la función más las firmas de lo que llama**, en lugar del módulo completo. Eso se logra con `llama_a` en la opción C.

## 6. Decisión

**Se adopta la opción C: análisis solo con `ast`, con el campo `llama_a` en `estructura.json`. Graphify no se integra en QAgent.**

Motivos:

1. **Duplica lo que ya existe.** EN-02 ya genera un resumen estático y HU-24 ya evita reprocesar módulos sin cambios.
2. **No entiende lo que QAgent necesita.** No extrae docstrings como oráculo, ni ramas, ni la semántica de FastAPI y Pydantic. Esa información igual tendría que salir de `ast`.
3. **Su parte semántica gasta tokens**, en contra del presupuesto de US$ 25 del semestre.
4. **Agrega una dependencia externa** en la pieza base del pipeline (EN-02, del Sprint 1), con riesgo para el MVP.
5. **Su salida no encaja con los contratos** y obligaría a mantener un traductor.
6. **Su única ventaja real, el mapa de llamadas, se obtiene con `ast`** sin tokens ni dependencias.

## 7. Validación empírica (pendiente)

La decisión se basa en la documentación de Graphify y en el análisis del diseño de QAgent. Para cerrar los criterios 1 a 3 de SPK-02, se completa esta tabla cuando existan el banco propio (EN-12) y el banco API (EN-16):

| Medición | Graphify | `ast` |
|---|---|---|
| Campos requeridos por `estructura.json` que extrae (lista definida en EN-01) | … | … |
| Tiempo de análisis, banco propio (s) | … | … |
| Tiempo de análisis, banco API (s) | … | … |
| Tokens consumidos al construir el mapa | … | 0 |
| Tokens de entrada del Planner, módulo de ejemplo, contexto completo | … | … |
| Tokens de entrada del Planner, módulo de ejemplo, función + `llama_a` | … | … |
| Dependencias que agrega | … | 0 |

Procedimiento:

1. Instalar Graphify en un entorno virtual aparte, no en el del proyecto.
2. Ejecutarlo sobre `bench/` y guardar su salida en `docs/evidencias/spk-02/`.
3. Ejecutar el analizador de EN-02/EN-14 sobre las mismas carpetas y guardar su salida en la misma ruta.
4. Contar los tokens de entrada del Planner sin generar respuestas. Claude Opus 5.5 no tiene tokenizador local: se usa el endpoint `count_tokens` de Anthropic, que es una llamada a la API pero no cobra tokens. Para MiMo se usa su tokenizador si está disponible o, si no, se aproxima y se indica en la tabla.
5. Si la medición contradice la decisión, se registra un ADR nuevo que reemplace a este.

## 8. Consecuencias

- **EN-01:** `estructura.json` incluye el campo `llama_a` y el contrato del Planner incluye `tipo: "funcion" | "endpoint"`.
- **Riesgo en `llama_a`:** `ast` solo da el nombre de lo que se llama, no a qué función corresponde. La resolución es por nombre y *best-effort*: cubre funciones del mismo módulo, `self.metodo()` dentro de la clase e imports del proyecto (incluidos alias `from x import y as z`). Las llamadas que no se resuelvan quedan marcadas como externas y el Planner las trata como candidatas a simular.
- **EN-02 / EN-14:** exponen una interfaz única, `analizar(ruta) -> Estructura`. Si en el futuro se quiere otra fuente (Graphify u otra herramienta), se cambia la implementación sin tocar el Planner ni el orquestador.
- **Sin nuevas dependencias** ni cambios en el plan de gasto del ADR-001.
- **Trabajo futuro:** Graphify u otra herramienta similar se puede reconsiderar si QAgent pasa a analizar repositorios grandes o a soportar otros lenguajes. También puede ser útil para el equipo como herramienta de desarrollo cuando el repositorio de QAgent crezca, fuera del producto.

## 9. Fuentes

- [DEV Community — Graphify: Turn Codebases into Knowledge Graphs to Slash AI Token Costs](https://dev.to/terminalchai/graphify-turn-codebases-into-knowledge-graphs-to-slash-ai-token-costs-3lfb)
- [MindStudio — Graphify for Claude Code](https://www.mindstudio.ai/blog/graphify-claude-code-knowledge-graph-large-codebase-70x)
- [CLSkills Hub — Graphify + Claude Code](https://clskillshub.com/blog/graphify-claude-code-integration)
- [Python — módulo `ast`](https://docs.python.org/3/library/ast.html)
