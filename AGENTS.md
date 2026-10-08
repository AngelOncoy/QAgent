# AGENTS.md — QAgent

Contexto para asistentes de IA (Claude, Copilot, Cursor, etc.) que trabajen en este repositorio.

## Qué es

Sistema multiagente en Python que genera y valida pruebas pytest para código Python 3.10+: pruebas unitarias de funciones y pruebas de endpoints de APIs FastAPI (con `TestClient`, sin red).

**Nombre:** el producto se llama **QAgent**. El paquete interno de Python se mantiene como `pyagent` (`src/pyagent/`, `PYAGENT_FAKE_LLM`, `~/.pyagent/`) para no romper imports; no renombrarlo.
Tres agentes coordinados por un orquestador (metodología GAIA), comunicados **solo por contratos JSON**:

1. **Planner:** analiza el código (AST, firmas, docstrings) y decide los casos de prueba.
2. **Generator:** escribe el test pytest de una función a partir del contrato.
3. **Reviewer/Executor:** ejecuta el test en un sandbox Docker, detecta Assertion Laundering y decide si reintentar (máx. 3).

Aplicación de escritorio local (pywebview + backend Python + Docker). No hay servidor propio ni API REST.

## Alcance (no ampliar)

- Solo dos tipos de prueba, ambos con pytest: **unitarias de funciones Python** y **de endpoints FastAPI** con `TestClient` dentro del sandbox, sin red y simulando `Depends` (EP-09).
- Fuera de alcance (Fase 2): integración contra servicios reales, extremo a extremo, carga y estrés, pruebas del frontend del código del usuario y pruebas de propiedades. (No confundir con `frontend/`, la interfaz de QAgent.)
- El análisis estático usa solo el módulo `ast` de la biblioteca estándar; no se integra Graphify (ver `docs/decisiones/ADR-002-mapa-de-codigo.md`).
- mutmut solo sobre funciones marcadas `critical: true`, nunca sobre el repositorio completo.

## Comandos

```bash
pip install -e .[dev]           # instalación editable, una vez por máquina (pyproject.toml)
python test.py                  # lint + formato + TODAS las pruebas (IA simulada, 0 tokens)
python test.py --rapido         # sin lint y sin pruebas de Docker ni de red
pytest                          # solo pytest (con IA simulada: set PYAGENT_FAKE_LLM=1; en bash: export)
ruff check . && ruff format .   # lint y formato (bench/ está excluido a propósito)
qagent                          # abre la aplicación de escritorio (o: python -m pyagent)
```

El paquete requiere instalación editable: `config.toml` y `contracts/` se buscan relativos a la raíz del repositorio.

## Estructura

| Ruta | Contenido |
|---|---|
| `src/pyagent/agents/` | Planner, Generator, Reviewer |
| `src/pyagent/orchestrator/` | Máquina de estados de la corrida |
| `src/pyagent/analysis/` | Analizador AST (estático): funciones, rutas FastAPI y mapa de llamadas `llama_a`. Interfaz única `analizar(ruta) -> Estructura` |
| `src/pyagent/sandbox/` | Ejecución en Docker |
| `src/pyagent/llm/` | Cliente LLM real y simulado; registro de tokens |
| `src/pyagent/app/` | Puente pywebview (`desktop.py`): recibe acciones de la interfaz y le envía eventos. Sin lógica de negocio |
| `src/pyagent/config/` | Carga de `config.toml` y `.env`, auditoría de claves (nunca se muestran) y verificación del entorno: configuración, claves, Docker y Git (EN-06) |
| `src/pyagent/proyectos/` | Lógica de proyectos: abrir, clonar, recientes y vista previa. No depende de pywebview |
| `frontend/` | Interfaz HTML/CSS/JS sin build: un componente por pantalla en `componentes/`, tokens de diseño en `css/tokens.css`, logo en `assets/logo/`. Ver `frontend/README.md` |
| `contracts/` | JSON Schema de los contratos entre agentes |
| `tests/` | Pruebas del sistema; reflejan `src/` (`analysis`, `app`, `config`, `llm`, `orchestrator`, `proyectos`, `sandbox`, `storage`) y `tests/frontend/` para la estructura de la interfaz |
| `test.py` | Ejecuta todas las pruebas con un comando (lint, formato y pytest) |
| `pyproject.toml` | Dependencias, extra `dev`, configuración de pytest y ruff, script `qagent` |
| `CLAUDE.md` | Guía específica para Claude Code (importa este archivo) |
| `docs/arquitectura.md` | Arquitectura del sistema y modelo GAIA |
| `docs/decisiones/` | ADR (decisiones técnicas): ADR-001 modelos por agente, ADR-002 análisis con `ast`, ADR-003 frontend modular |
| `docs/evidencias/` | Salidas y mediciones de los spikes (ej. `spk-02/`) |
| `bench/` | Banco de pruebas con bugs sembrados |

## Reglas que no se rompen

- **Nunca ejecutar código del usuario ni tests generados fuera del sandbox.** El análisis del código del usuario es solo estático (AST).
- **Los agentes no se llaman entre sí:** todo pasa por el orquestador y los contratos de `contracts/`. Si cambia un contrato, se actualiza su schema y su test.
- **El valor esperado de una aserción sale del contrato del Planner**: firma, tipos y docstring de una función, o la declaración de la ruta (`response_model`, `status_code`, modelos Pydantic) de un endpoint. Nunca de ejecutar el código.
- **Nunca relajar ni borrar aserciones para que un test pase.**
- **Claves solo en `.env`.** Nunca en código, logs, tests, commits ni dentro del contenedor.
- **Modelos y precios solo desde `config.toml`** (se versiona, sin claves), nunca hardcodeados (ver `docs/decisiones/ADR-001-modelos.md`).
- **Tests del sistema con la IA simulada:** ningún test de `tests/` debe llamar a una API real.
- **Los tests no dependen de Docker ni de internet**, salvo los marcados `docker` o `red` (se omiten si no hay). Docker se simula en las demás.
- **La lógica no depende de la interfaz:** `app/` llama a `proyectos/`, `analysis/`, `sandbox/`…, nunca al revés (la lógica no importa `pyagent.app` ni `webview`).
- **Frontend:** un componente por pantalla o modal en `frontend/componentes/`; colores, tipografía y logo en `frontend/css/tokens.css` (sin colores literales: todo es `var(--token)`, lo verifica `tests/frontend/`); sin bundler, sin módulos ES ni `fetch` de HTML (ver ADR-003).
- **Nombres técnicos fijos:** `pyagent-sandbox:base`, `.pyagent/`, `pyagent` y `window.onPyAgentEvent` no se renombran aunque el producto sea QAgent.

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