# ADR-015: Contrato inferido para funciones sin docstring

- **Estado:** Propuesto (2026-11-11)
- **Fecha:** 2026-11-11
- **Ítem:** #275 — HU · Probar funciones sin docstring con un contrato inferido
- **Responsable:** Oncoy Patricio, Angel
- **Relacionado:** ADR-007 (adaptadores por lenguaje), ADR-008 (orquestador determinista), ADR-009 (tree-sitter), ADR-010 (alcance del Sprint 2), ADR-012 (grafo de dependencias), ADR-014 (integración interna), AGENTS.md («Reglas que no se rompen»)

---

## 1. Contexto

El Planner deduce el valor esperado de cada caso **solo** de la firma, los tipos y el docstring (AGENTS.md). Cuando ninguno basta (código sin tipos ni docstring), la función queda **omitida** con el aviso «la función no tiene docstring y no se pudo deducir…» (`planner.py::_omitir`).

La mayoría de los repositorios reales no documentan sus funciones. En ellos QAgent omite casi todo y el producto queda fuera de alcance para su público principal. Es un problema de adopción, no de un caso raro.

Hoy el contexto del código (`analysis/contexto.py`) y el grafo de dependencias (`analysis/grafo_imports.py`, ADR-012) solo llegan al **Generator**. El Planner no los ve. Además el grafo mira hacia abajo (firmas y docstrings de lo que la función usa) y no hacia arriba (quién la llama y con qué valores).

## 2. Pregunta

¿De dónde puede salir el valor esperado de una función sin contrato documentado, sin ejecutar su código, sin exigir una aprobación por función y sin presentar las pruebas resultantes como más fuertes de lo que son?

## 3. Opciones evaluadas

| Opción | Descripción | A favor | En contra |
|---|---|---|---|
| **A. Solo reportar mejor lo omitido** | Categoría «no verificable» y sugerencia de agregar docstring. | Sin riesgo; honesto. | No amplía el alcance: el usuario sigue sin pruebas. |
| **B. Contrato inferido por lectura estática (esta decisión)** | El Planner infiere la intención leyendo cuerpo, nombres, dependencias del grafo, llamadores y tests existentes; el caso lleva origen `inferido` y evidencia. Automático por defecto. | Cubre repositorios sin docstrings; el análisis sigue siendo estático; nada se oculta. | La prueba tiende a repetir el código: es de regresión, no de corrección. Más tokens. |
| **C. Inferido con confirmación por función** | Igual que B, pero cada contrato lo aprueba una persona. | Máxima garantía. | Con cientos de funciones es inviable. Se deja como interruptor opcional. |
| **D. Caracterización por ejecución** | Ejecutar la función en el sandbox y fijar lo que devuelve. | Red de regresión exacta. | Contradice la regla de no sacar el valor esperado de ejecutar el código. Queda fuera. |
| **E. Pruebas sin valor esperado** | Solo «no lanza» y «devuelve el tipo». | Honesto. | Débil; roza las pruebas de propiedades (fuera de alcance). |

## 4. Decisión

**Se adopta la opción B** con el interruptor de la C, como piloto en Python. D y E no se adoptan.

### 4.1 Niveles de respaldo

| Nivel | Cuándo | Origen de los casos | Cómo se presenta |
|---|---|---|---|
| **A. Contrato** | Hay docstring o tipos que determinan el resultado | `firma`, `tipo`, `docstring` | Como hoy |
| **B. Inferido** | No hay contrato suficiente, pero sí código analizable | `inferido` | «Prueba de regresión, sin contrato documentado» |
| **C. Omitida** | Ni siquiera hay evidencia estática | — | Aviso accionable: qué falta y cómo resolverlo |

El Nivel B solo se usa cuando el A no alcanza. Una función con contrato nunca pasa a inferido.

### 4.2 Fuentes de la inferencia (todas estáticas, nunca se ejecuta código)

1. **Cuerpo de la función** (`contexto_de_funcion`).
2. **Dependencias hacia abajo** con el grafo de imports (ADR-012): firma y docstring de las funciones internas que usa, y las que se encadenan (`llamadas_transitivas`).
3. **Llamadores hacia arriba** (nuevo): un índice inverso construido con `llama_a` de todos los módulos —el mismo recorrido de `analysis/integracion.py`—, que da cómo y con qué argumentos se usa la función en el resto del proyecto.
4. **Tests existentes del repositorio**, leídos con tree-sitter: lo que otros ya afirmaron sobre esa función.
5. **Nombre de la función y de sus parámetros**.

El **Planner recibe este contexto** (hoy solo lo recibe el Generator). Es la forma de no perder el contexto real del proyecto: el contrato inferido se apoya en cómo se usa la función, no solo en su cuerpo.

### 4.3 Contrato y trazabilidad

- `planner_contract.v3`: el enum `origen` de un caso agrega `inferido` (aditivo; los contratos y datos guardados no cambian).
- Un caso `inferido` lleva obligatoriamente `evidencia`: lista de fuentes (`cuerpo`, `llamador:<ruta>::<función>`, `test_existente:<ruta>::<test>`, `dependencia:<símbolo>`). Un caso `inferido` sin evidencia se descarta con aviso. Un caso `inferido` no puede declararse de límite si ninguna fuente lo respalda.
- El Reviewer mantiene el guardrail sin IA antes de ejecutar y **nunca se relaja una aserción para que la prueba pase**.

### 4.4 Reglas que cambian (AGENTS.md)

La regla «El valor esperado sale del contrato del Planner… Nunca de ejecutar el código» se amplía: puede salir también de la **lectura estática** del código y su contexto (origen `inferido`), siempre etiquetado. **Sigue prohibido ejecutarlo para obtener el valor esperado.** Las demás reglas no cambian.

### 4.5 Honestidad del resultado

- El informe separa las cifras: «N con contrato · M de regresión sin contrato documentado». Nunca se suman como «funciones verificadas».
- Un fallo de una prueba inferida se muestra como **hallazgo a revisar** («el código se comporta distinto a lo que se infería de su uso»), no como bug confirmado: puede ser un contrato mal inferido.
- El Explicador lo dice con esas palabras y no cambia resultados.
- En funciones `critical` la mutación sigue corriendo: una prueba inferida que no mata mutantes queda a la vista como débil.

### 4.6 Flujo de usuario

- **Automático por defecto:** sin pasos intermedios. En Vista previa cada función del Nivel B lleva la marca «Sin docstring: contrato inferido por QAgent».
- **Interruptor «Revisar contratos inferidos»** (apagado por defecto): activa la opción C, con aceptar/editar/descartar y la posibilidad de aceptar todo un archivo de una vez.
- **Control de costo:** Preparar estima tokens y tiempo del Nivel B por separado y permite elegir qué funciones entran (*Incluir*). Topes en `config.toml` (funciones inferidas por corrida, tamaño del contexto), no en la lógica.
- Sin cambios en el orquestador: sigue siendo determinista (ADR-008); el Nivel B es una fuente más del Planner.

### 4.7 Medición y apagado

Se agrega un banco en `bench/` con funciones sin docstring y defectos sembrados, para medir cuántos detecta el Nivel B frente a omitir. Si no detecta nada, o produce más falsos hallazgos que útiles, queda **apagado por defecto** y se anota aquí.

## 5. Consecuencias

### Positivas
- Los repositorios sin docstrings dejan de quedar fuera de alcance.
- El análisis sigue siendo estático y el valor esperado siempre tiene origen y evidencia visibles.
- Reutiliza el grafo, el contexto, el Reviewer y el sandbox; sin cambios en el orquestador.

### Negativas y riesgos
- **Pruebas circulares:** si el código tiene un bug, una prueba inferida puede darlo por bueno. Mitigación: etiqueta permanente, cifras separadas, evidencia obligatoria, mutación en críticas y revisión opcional.
- **Falsos hallazgos:** un contrato mal inferido hace fallar una prueba correcta. Mitigación: se presentan como «a revisar».
- **Más tokens por corrida** (el Planner recibe cuerpo y contexto). Mitigación: topes, estimación en Preparar y selección de funciones.
- **Índice de llamadores:** nuevo recorrido del proyecto; se calcula una vez por corrida y se reutiliza con ADR-014.
- **Alcance:** solo Python. JS/TS y Java quedan para ítems propios.

### Fuera de alcance
Caracterización por ejecución (opción D), pruebas de propiedades y cualquier lenguaje distinto de Python.

## 6. Plan de implementación (tras la aprobación)

1. Contrato: `origen: inferido` y `evidencia`, con sus pruebas y compatibilidad hacia atrás.
2. Índice de llamadores y lector de tests existentes (análisis estático, 0 tokens).
3. Contexto del Planner de Python: cuerpo, dependencias del grafo, llamadores y tests; prompt y validación de origen `inferido` con evidencia.
4. Informe, Vista previa y Explicador: etiqueta, cifras separadas y «hallazgo a revisar».
5. Preparar: estimación, selección de funciones e interruptor «Revisar contratos inferidos».
6. Banco en `bench/` y decisión del valor por defecto.
7. Documentación (`docs/arquitectura.md`, AGENTS.md —la regla del §4.4—, README del adaptador).

Cada fase con sus pruebas, con la IA simulada y sin Docker ni red (salvo las marcadas `docker`).

### 6.1 Estado de la implementación (#275)

| Fase | Estado |
|---|---|
| 1. Contrato (`origen: inferido`, `evidencia`) | Hecha (`planner_contract.v3`, `contracts.es_contrato_inferido`) |
| 2. Índice de llamadores y tests existentes | Hecha (`analysis/inferencia.py`) |
| 3. Contexto del Planner y validación | Hecha (segundo paso del Planner; la evidencia solo vale si QAgent la entregó) |
| 4. Informe, Vista previa y Explicador | Hecha (`respaldo`, `texto_respaldo`, «hallazgo a revisar», marca en Vista previa y en el detalle) |
| 5. Preparar: estimación aparte y selección | **Pendiente**: hoy se controla con `[inferencia]` en `config.toml` (`activa`, `max_funciones_por_modulo`, `max_caracteres_contexto`) |
| 5b. Interruptor «Revisar contratos inferidos» (opción C) | **Pendiente**: la revisión humana no está en la interfaz todavía |
| 6. Banco en `bench/sin_docstring/` | Banco creado; **medición pendiente** (necesita Docker y un modelo real) |
| 7. Documentación | Hecha (AGENTS.md, este ADR); falta `docs/arquitectura.md` |

## 7. Aprobación

- [ ] Castillo Pezo, Mateo
- [ ] Oncoy Patricio, Angel
- [ ] Rodríguez Malca, Rodrigo
- [ ] Sanchez Vargas, Adrián
- [ ] Nuevo integrante (Java)
