# ADR-010: Arquitectura y alcance del Sprint 2 — multilenguaje y Agente Explicador

- **Estado:** Propuesto (pendiente de aprobación del equipo)
- **Fecha:** 2026-10-27
- **Ítem:** EN-20 — Definir la arquitectura del sistema para el Sprint 2 (multilenguaje y Agente Explicador)
- **Responsable:** Oncoy Patricio, Angel
- **Relacionado:** ADR-001 (modelos y costos), ADR-002 (análisis con `ast`), ADR-005 (distribución), ADR-007 (adaptadores por lenguaje, EN-17), ADR-008 (orquestador y Explicador, SPK-03), ADR-009 (parser por lenguaje, SPK-04), `docs/arquitectura.md`

---

## 1. Contexto

El docente confirmó una ampliación de alcance para el Sprint 2 y se sumó un quinto integrante. El plan de mejoras del Sprint 2 propone cuatro frentes:

1. un Agente Explicador que traduzca los hallazgos a lenguaje simple;
2. soporte para JavaScript y TypeScript, con sus frameworks por niveles;
3. soporte para Java;
4. nuevos tipos de prueba: componentes, E2E y arquitectura.

Varias piezas ya avanzaban por separado (EN-17, SPK-03 y SPK-04), pero `docs/arquitectura.md` seguía describiendo el sistema del Sprint 1, solo para Python. Sin un modelo común, cada integrante decidía por su cuenta dónde va su pieza, con riesgo de duplicar el pipeline por lenguaje o de romper reglas que hoy se cumplen (oráculo, tope de intentos, sandbox sin red).

## 2. Pregunta

¿Cómo se amplía QAgent a varios lenguajes, nuevos tipos de prueba y un Agente Explicador sin rehacer la arquitectura, sin duplicar agentes y sin comprometer el comportamiento ni los datos guardados que existen hoy?

## 3. Opciones evaluadas

| Opción | Descripción | A favor | En contra |
|---|---|---|---|
| **A. Ampliar la arquitectura actual con una capa de adaptadores** | Se mantiene el monolito modular y el pipeline. Lo que depende del lenguaje se separa detrás de una interfaz común; el Explicador se agrega como etapa final. | Los agentes y el orquestador se reutilizan; cada lenguaje se desarrolla en paralelo; Python no cambia. | Hay que mantener una interfaz y contratos versionados. |
| **B. Un pipeline por lenguaje** | Copiar Planner, Generator, Reviewer y orquestador para cada lenguaje. | Cada equipo avanza sin depender de los demás. | Triplica la lógica compartida (reintentos, oráculo, métricas, guardrail); las reglas se desincronizan; contradice EN-17. |
| **C. Rediseñar la coordinación alrededor de un LLM** | Un orquestador LLM que decide el flujo y explica, con agentes por lenguaje como herramientas. | Flexible ante casos raros. | Descartada en ADR-008: no hay decisiones sin regla, se pierde la reproducibilidad y aumenta la superficie de ataque. |

## 4. Decisión

**Se adopta la opción A.** La arquitectura del Sprint 2 es la de `docs/arquitectura.md`, que integra las decisiones de esta tabla:

| Pieza | Decisión | Registro |
|---|---|---|
| Estilo | Sigue siendo un monolito modular de escritorio con un pipeline multiagente orquestado. | `docs/arquitectura.md`, sección 1 |
| Lenguajes | Capa de adaptadores (`LanguageAdapter` y registro). Lo específico de cada lenguaje vive solo en su adaptador; los agentes y el orquestador no conocen lenguajes. | ADR-007 |
| Contratos | Versiones nuevas (`planner_contract.v3`, `generated_test.v2`) con lenguaje y framework, al lado de las actuales. Los contratos existentes y la persistencia de `.qagent/` no cambian. | ADR-007 |
| Análisis | `ast` para Python; tree-sitter para JavaScript, TypeScript y Java; sin Graphify. | ADR-002, ADR-009 |
| Coordinación | El orquestador sigue siendo determinista. El único punto híbrido es `_clasificar_con_llm` del Reviewer. | ADR-008 |
| Explicador | Etapa posterior al veredicto, fuera de la máquina de estados, de solo lectura, con plantillas deterministas y un LLM opcional. Pensado sobre todo para usuarios con poca experiencia en desarrollo. | ADR-008 |
| Sandbox | Una imagen por lenguaje (`qagent-sandbox:base` para Python; `node`, `java` y `navegador` propuestas), con las mismas reglas: efímera, sin red al ejecutar y con límites de recursos. Los runtimes de Node y Java solo viven en las imágenes, nunca en la PC del usuario. | `docs/arquitectura.md`, sección 7 |
| Tipos de prueba | Por prioridad: TS/JS puro y Java (Must); React, servicios de Angular, mutación con Stryker y PIT, arquitectura y E2E de humo (Should); componentes de Angular (Could); Astro, E2E de flujos completos, carga y estrés quedan fuera. | `docs/arquitectura.md`, sección 10.6 |

### 4.1 Ampliación del alcance

AGENTS.md limitaba el alcance a pruebas unitarias de Python y de endpoints FastAPI. Este ADR registra la ampliación aprobada para el Sprint 2 con tres reglas:

1. **Cada tipo de prueba entra al alcance cuando su ítem se implementa**, no antes. Mientras tanto, la documentación lo marca como propuesto.
2. **Sigue fuera de alcance:** integración contra servicios reales, E2E de flujos que el usuario no declaró, carga y estrés, Astro (solo investigación) y pruebas de propiedades.
3. **El oráculo no cambia:** en todos los lenguajes y tipos de prueba, el valor esperado sale de la especificación (docstring, JSDoc, Javadoc, tipos, declaración de la ruta, reglas declaradas por el usuario o rutas detectadas por el análisis), nunca de ejecutar el código.

### 4.2 Lo que no cambia

Orquestador sin LLM; máximo 3 intentos y un reintento nunca vuelve al Planner; corte por hash repetido; tope de gasto y límite de tokens; toda ejecución en Docker sin red; Assertion Laundering detectado sin IA antes de ejecutar; mutación solo en funciones críticas; agentes que no se llaman entre sí; las 5 métricas por prueba, ahora con la columna lenguaje. Detalle en `docs/arquitectura.md`, sección 13.1.

## 5. Consecuencias

### Positivas

- Hay un solo modelo de referencia para los cinco integrantes; cada pieza tiene su lugar y su decisión registrada.
- JS/TS y Java se desarrollan en paralelo sin tocar los agentes ni el orquestador.
- El flujo de Python, sus métricas y sus datos guardados no cambian.
- El Explicador agrega valor para usuarios no técnicos sin arriesgar los resultados.

### Negativas y riesgos

- **Capacidad:** según el plan del Sprint 2, el núcleo Must suma ~62 SP frente a un margen de ~65 SP, así que solo entra una parte de lo Should. E2E, Angular y la mutación de TS y Java son los primeros candidatos a salir.
- **Costo en tokens:** Java y TypeScript generan prompts más largos que Python, y el Explicador con LLM agrega llamadas. Se controla con el tope por corrida y con las plantillas sin IA del Explicador.
- **Sandbox más pesado:** las imágenes de Java y con navegador necesitan más memoria y tiempo; sus límites se miden antes de fijarlos.
- **Más piezas que mantener:** la interfaz del adaptador, las versiones de los contratos y una gramática con sus consultas por lenguaje.

### Seguimiento

Las decisiones abiertas, con su responsable sugerido, están en `docs/arquitectura.md`, sección 13.2. Cada una que cambie el alcance, un modelo o una dependencia se registra en su propio ADR.
