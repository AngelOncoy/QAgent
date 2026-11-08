# ADR-014: Pruebas de integración interna (piloto en Python)

- **Estado:** Aprobado por el equipo (2026-11-08)
- **Fecha:** 2026-11-08
- **Ítem:** #245 — HU · Probar la integración entre funciones del mismo proyecto
- **Responsable:** Oncoy Patricio, Angel
- **Relacionado:** ADR-007 (adaptadores por lenguaje), ADR-008 (orquestador determinista), ADR-010 (alcance del Sprint 2), ADR-011 (Recomendador), ADR-012 (grafo de dependencias), AGENTS.md («Alcance»)

---

## 1. Contexto

QAgent genera hoy pruebas unitarias de funciones y de endpoints. En una unitaria el Generator simula las dependencias del proyecto, así que un fallo que solo aparece cuando dos funciones trabajan juntas (un tipo que una devuelve y la otra no espera, un orden de llamadas, un valor límite que cruza la frontera) no se ve.

El análisis ya conoce qué funciones llaman a cuáles (`llama_a`) y el grafo de imports entre archivos (ADR-012), pero solo los usa como contexto del prompt. Esta decisión los usa para elegir cadenas de llamadas y probarlas juntas.

ADR-010 deja fuera la «integración contra servicios reales». Esto **no** la reabre: la integración interna prueba funciones del mismo proyecto y simula todo lo que sale de él.

## 2. Pregunta

¿Qué es una prueba de integración interna en QAgent, de dónde sale su valor esperado, qué se simula y cómo se integra al pipeline sin cambiar el orquestador ni los agentes?

## 3. Opciones evaluadas

| Opción | Descripción | A favor | En contra |
|---|---|---|---|
| **A. Tipo de prueba propio `integracion`** | Nuevo valor de `tipo` en el contrato del Planner, declarado por el adaptador de Python y ofrecido en Preparar y por el Recomendador. | Se elige, se mide y se apaga por separado; no toca las unitarias; encaja en ADR-007 y ADR-011. | Un valor más en el vocabulario de contratos y en `recommendation.v1`. |
| **B. Unitarias con menos mocks** | Pedir al Generator que simule menos en las unitarias existentes. | Sin tipo nuevo. | Rompe la independencia de las unitarias (regla 1 de la arquitectura): un bug en C haría fallar el test de D. |
| **C. No hacerlo** | Mantener solo unitarias. | Cero costo. | Los fallos de composición siguen sin detectarse. |

## 4. Decisión

**Se adopta la opción A**, como piloto solo en Python.

### 4.1 Qué es una integración interna

Una prueba que llama a una función **raíz** del proyecto y deja que se ejecuten de verdad las funciones internas que esta invoca, para comprobar el resultado de la cadena completa.

- **Candidata:** función con al menos una llamada a otra función interna del proyecto (`llama_a` resuelto con el grafo de imports). Sin candidatas, el tipo no se ofrece ni se recomienda.
- **Cadena:** la raíz más sus llamadas internas, hasta profundidad 2 y 4 funciones como máximo (valores en `config.toml`, no en la lógica). Si la cadena real es mayor se recorta y el informe lo dice.
- Un objetivo = una raíz = una prueba de integración. Su nombre es `integracion_<raíz>` para no chocar con la unitaria de la misma función (el pipeline identifica cada objetivo por su nombre); la raíz es el primer elemento de `cadena`. Los métodos de clase y las funciones sin cuerpo analizable no son candidatos.
- Solo entran en la cadena las funciones internas **puras**; las de efecto se simulan y no cuentan. Una función cuyas internas son todas de efecto no es candidata.
- El Planner no hace una llamada nueva: el contrato de integración se deriva del contrato unitario de la raíz (mismos casos y mismo oráculo, sacados de su firma y documentación). Si la raíz no tiene contrato unitario verificable, no hay integración.

### 4.2 De dónde sale el valor esperado (oráculo)

Igual que en todo QAgent: de la **firma, los tipos y la documentación de la raíz**, nunca de ejecutar el código. Las firmas de las funciones internas solo se usan para saber qué tipos cruzan cada frontera, no para calcular resultados. Una raíz sin documentación suficiente se marca con oráculo débil, como las unitarias, y el informe lo muestra.

### 4.3 Qué se simula y qué no

| Se llama de verdad | Se simula |
|---|---|
| Funciones internas puras: sin entrada/salida, red, base de datos, reloj ni azar | Servicios externos y efectos: red, base de datos, sistema de archivos, subprocesos, hora y aleatoriedad |
| | Funciones internas «de efecto»: las que, según el análisis estático, usan módulos de esos efectos |

La clasificación es estática (imports y llamadas conocidas) y vive en el adaptador de Python. Una función ambigua se trata como de efecto (se simula), nunca al revés. Todo corre en el sandbox sin red.

### 4.4 Contratos y vocabulario

- `planner_contract.v3`: el enum `tipo` agrega `integracion`, con un campo `cadena` (lista ordenada de funciones) obligatorio solo para ese tipo. Es aditivo: los contratos y datos guardados existentes no cambian.
- `recommendation.v1`: `integracion` entra al vocabulario de tipos. Se actualiza su schema y su prueba de compatibilidad; los tipos actuales no cambian.
- `LanguageAdapter.tipos_prueba` de Python agrega `integracion` solo cuando la implementación esté completa; mientras tanto va en `tipos_prueba_previstos`.

### 4.5 Reviewer y Assertion Laundering

Sin cambios de reglas: el guardrail sin IA corre antes de ejecutar y **nunca se relaja una aserción para que la prueba pase**. Una prueba de integración que falla porque la composición está mal es un hallazgo, no un error de la prueba. Máximo 3 intentos, como siempre.

### 4.6 Flujo de usuario

Se elige en Preparar como un tipo más; la estimación de tokens y tiempo lo incluye. El Recomendador (reglas) lo propone solo si hay candidatas y con su motivo. El orquestador no cambia.

### 4.7 Medición y apagado por defecto

Se agrega un banco en `bench/` con al menos un defecto sembrado que **solo** se ve al combinar funciones. Se compara con las unitarias: si la integración no encuentra nada que las unitarias no encuentren, el tipo queda **apagado por defecto** y se anota aquí.

## 5. Consecuencias

### Positivas
- Detecta fallos de composición que hoy pasan inadvertidos.
- Reutiliza el análisis, el adaptador, el Reviewer y el sandbox existentes; sin cambios en el orquestador.
- Se puede apagar sin afectar lo demás.

### Negativas y riesgos
- **Más tokens por corrida:** el prompt incluye la cadena. Se controla con el tope por corrida y la estimación en Preparar.
- **Clasificación pura/efecto aproximada:** una función mal clasificada produce una prueba lenta o frágil. Mitigación: ante la duda se simula.
- **Alcance:** solo Python. JS/TS y Java quedan para ítems propios.

### Fuera de alcance
Integración contra servicios reales, E2E de flujos completos y cualquier lenguaje distinto de Python.

## 6. Plan de implementación (tras la aprobación)

1. Contratos y vocabulario (`planner_contract.v3`, `recommendation.v1`) con sus pruebas.
2. Candidatas y cadenas desde `llama_a` y el grafo de imports; clasificación pura/efecto.
3. Planner y Generator de Python para el tipo `integracion` (prompt con cadena y regla de simulación).
4. Selección en Preparar, estimación y regla del Recomendador.
5. Banco en `bench/` y comparación con las unitarias; decisión del valor por defecto.
6. Documentación (`docs/arquitectura.md`, AGENTS.md, README del adaptador).

Cada fase con sus pruebas, con la IA simulada y sin Docker ni red (salvo las marcadas `docker`).

## 7. Aprobación

- [x] Castillo Pezo, Mateo
- [x] Oncoy Patricio, Angel
- [x] Rodríguez Malca, Rodrigo
- [x] Sanchez Vargas, Adrián
- [x] Nuevo integrante (Java)
