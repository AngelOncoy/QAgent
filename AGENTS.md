# AGENTS.md — QAgent

Contexto para asistentes de IA (Claude, Copilot, Cursor, etc.) que trabajen en este repositorio.

## Qué es

Sistema multiagente en Python que genera y valida pruebas unitarias pytest para código Python 3.10+: funciones y endpoints de APIs REST con FastAPI.
Tres agentes coordinados por un orquestador (metodología GAIA), comunicados **solo por contratos JSON**:

1. **Planner:** analiza el código (AST, firmas, docstrings) y decide los casos de prueba.
2. **Generator:** escribe el test pytest de una función a partir del contrato.
3. **Reviewer/Executor:** ejecuta el test en un sandbox Docker, detecta Assertion Laundering y decide si reintentar (máx. 3).

Aplicación de escritorio local (pywebview + backend Python + Docker). No hay servidor propio ni API REST.

## Alcance (no ampliar)

- Solo pruebas **unitarias** con pytest de **funciones Python** y **endpoints FastAPI** (EP-09). Nada de frontend, pruebas de integración contra servicios reales ni pruebas de propiedades.
- El análisis estático usa solo el módulo `ast` de la biblioteca estándar; no se integra Graphify (ver `docs/decisiones/ADR-002-graphify.md`).
- mutmut solo sobre funciones marcadas `critical: true`, nunca sobre el repositorio completo.

## Comandos

```bash
pip install -e .[dev]
pytest                          # pruebas del sistema
ruff check . && ruff format .   # lint y formato
set PYAGENT_FAKE_LLM=1          # IA simulada: 0 tokens (Windows; en bash: export)
```

## Estructura

| Ruta | Contenido |
|---|---|
| `src/pyagent/agents/` | Planner, Generator, Reviewer |
| `src/pyagent/orchestrator/` | Máquina de estados de la corrida |
| `src/pyagent/analysis/` | Analizador AST (estático): funciones, rutas FastAPI y mapa de llamadas `llama_a`. Interfaz única `analizar(ruta) -> Estructura` |
| `src/pyagent/sandbox/` | Ejecución en Docker |
| `src/pyagent/llm/` | Cliente LLM real y simulado; registro de tokens |
| `src/pyagent/app/` | Interfaz pywebview |
| `contracts/` | JSON Schema de los contratos entre agentes |
| `docs/arquitectura.md` | Arquitectura del sistema y modelo GAIA |
| `docs/decisiones/` | ADR (decisiones técnicas): ADR-001 modelos por agente, ADR-002 análisis con `ast` |
| `docs/evidencias/` | Salidas y mediciones de los spikes (ej. `spk-02/`) |
| `bench/` | Banco de pruebas con bugs sembrados |

## Reglas que no se rompen

- **Nunca ejecutar código del usuario ni tests generados fuera del sandbox.** El análisis del código del usuario es solo estático (AST).
- **Los agentes no se llaman entre sí:** todo pasa por el orquestador y los contratos de `contracts/`. Si cambia un contrato, se actualiza su schema y su test.
- **El valor esperado de una aserción sale del contrato del Planner** (firma, tipos, docstring), nunca de ejecutar el código.
- **Nunca relajar ni borrar aserciones para que un test pase.**
- **Claves solo en `.env`.** Nunca en código, logs, tests, commits ni dentro del contenedor.
- **Modelos y precios solo desde `config.toml`**, nunca hardcodeados (ver `docs/decisiones/ADR-001-modelos.md`).
- **Tests del sistema con la IA simulada:** ningún test de `tests/` debe llamar a una API real.

## Estilo de código

- Python 3.10+, type hints en funciones públicas y docstrings en español.
- Ruff como linter y formateador; no agregar otras herramientas sin un ADR.
- Funciones pequeñas y puras donde se pueda: facilita los tests y el mutation testing.

## Flujo de trabajo

- Ramas desde `develop`: `feat/`, `fix/`, `refactor/`, `test/`, `docs/`, `chore/` + ID del backlog. Ej.: `feat/en-01-contratos`.
- Commits: `tipo(ID): mensaje`. Ej.: `feat(EN-01): add planner contract schema`.
- Todo entra por PR a `develop` con la plantilla de `.github/pull_request_template.md` y al menos 1 aprobación.
- Cada PR indica el ítem del backlog (HU, EN, SPK, EV, DO) y sus criterios de aceptación.

## Para ahorrar tokens

- Lee solo los archivos del módulo que vas a tocar; no recorras todo el repositorio.
- Antes de proponer una dependencia o un cambio de alcance, dilo explícitamente y ofrece la alternativa más simple.