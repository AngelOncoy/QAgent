# AGENTS.md — QAgent

Contexto para asistentes de IA (Claude, Copilot, Cursor, etc.) que trabajen en este repositorio.

## Qué es

Sistema multiagente en Python que genera y valida pruebas pytest para código Python 3.10+: pruebas unitarias de funciones y pruebas de endpoints de APIs FastAPI (con `TestClient`, sin red).

**Nombre:** el producto, el comando, el paquete de Python y los nombres técnicos son **QAgent** / `qagent`: `src/qagent/`, `.qagent/`, `~/.qagent/`, `qagent-sandbox:base`, `QAGENT_FAKE_LLM` y `window.onQAgentEvent`. En PyPI se publica como `qagent-pytest` (`qagent` ya era de otro proyecto): solo cambia lo que se escribe en `pip install`, no el producto, el comando ni el `import`. El nombre anterior (`pyagent`) solo queda en el código de compatibilidad: la migración de `.pyagent/` y `~/.pyagent/`, y el respaldo de `PYAGENT_FAKE_LLM` (ADR-004).
Tres agentes coordinados por un orquestador (metodología GAIA), comunicados **solo por contratos JSON**:

1. **Planner:** analiza el código (AST, firmas, docstrings) y decide los casos de prueba.
2. **Generator:** escribe el test pytest de una función a partir del contrato.
3. **Reviewer/Executor:** ejecuta el test en un sandbox Docker, detecta Assertion Laundering y decide si reintentar (máx. 3).

Aplicación de escritorio local (pywebview + backend Python + Docker). No hay servidor propio ni API REST.

## Alcance (no ampliar)

- Solo dos tipos de prueba, ambos con pytest: **unitarias de funciones Python** y **de endpoints FastAPI** con `TestClient` dentro del sandbox, sin red y simulando `Depends` (EP-09).
- Fuera de alcance (Fase 2): integración contra servicios reales, extremo a extremo, carga y estrés, pruebas del frontend del código del usuario y pruebas de propiedades. (No confundir con `src/qagent/frontend/`, la interfaz de QAgent.)
- EN-17 (#129) deja la base para otros lenguajes en `src/qagent/lenguajes/` (adaptadores y contratos versionados, ADR-007), pero **el alcance sigue siendo Python** hasta que un lenguaje esté completo y tenga su propio ADR. JS/TS y Java hoy solo se detectan.
- El análisis estático usa solo el módulo `ast` de la biblioteca estándar; no se integra Graphify (ver `docs/decisiones/ADR-002-mapa-de-codigo.md`).
- mutmut solo sobre funciones marcadas `critical: true`, nunca sobre el repositorio completo.

## Comandos

```bash
pip install -e .[dev]           # instalación editable, una vez por máquina (pyproject.toml)
python test.py                  # lint + formato + TODAS las pruebas (IA simulada, 0 tokens)
python test.py --rapido         # sin lint y sin pruebas de Docker ni de red
pytest                          # solo pytest (con IA simulada: QAGENT_FAKE_LLM=1 en ~/.qagent/.env o set/export en el sistema)
ruff check . && ruff format .   # lint y formato (bench/ está excluido a propósito)
qagent                          # abre la aplicación de escritorio (o: python -m qagent; qagent --version)
python scripts/verificar_paquete.py  # construye el paquete, lo instala limpio fuera del repo y lo prueba (TA-06)
python scripts/construir_windows.py  # QAgent.exe + instalador (Windows; pip install -e .[dev,empaquetar] e Inno Setup 6.6 o superior)
```

La interfaz, los contratos y `config.toml` viajan dentro del paquete (`src/qagent/`), así que el programa también funciona instalado sin `-e` (TA-06). Para desarrollar se usa la instalación editable.

## Estructura

| Ruta | Contenido |
|---|---|
| `src/qagent/agents/` | Planner, Generator, Reviewer |
| `src/qagent/orchestrator/` | Máquina de estados de la corrida |
| `src/qagent/analysis/` | Analizador AST (estático): funciones, rutas FastAPI y mapa de llamadas `llama_a`. Interfaz única `analizar(ruta) -> Estructura` |
| `src/qagent/sandbox/` | Ejecución en Docker |
| `src/qagent/llm/` | Cliente LLM real y simulado; registro de tokens |
| `src/qagent/app/` | Puente pywebview (`desktop.py`): recibe acciones de la interfaz y le envía eventos, y bitácora de la corrida en la consola (`bitacora.py`). Sin lógica de negocio |
| `src/qagent/config/` | `config.toml` del equipo (modelos y precios), carga de `config.toml` y `.env`, auditoría de claves (nunca se muestran) y verificación del entorno: configuración, claves, Docker y Git (EN-06) |
| `src/qagent/proyectos/` | Lógica de proyectos: abrir, clonar y vista previa. No depende de pywebview |
| `src/qagent/almacenamiento/` | Almacenamiento del proyecto (EN-07): `AlmacenProyecto` guarda corridas (`run.json`), specs y pruebas aprobadas en `<proyecto>/.qagent/`; `recientes.py` maneja `~/.qagent/recientes.json`. Escritura atómica en UTF-8 |
| `src/qagent/storage/` | `log.json` y `results.json` de cada corrida en `.qagent/runs/<run_id>/` (EN-05) |
| `src/qagent/frontend/` | Interfaz HTML/CSS/JS sin build: un componente por pantalla en `componentes/`, tokens de diseño en `css/tokens.css`, logo en `assets/logo/`. Ver `src/qagent/frontend/README.md` |
| `src/qagent/contracts/` | JSON Schema de los contratos entre agentes y `validar()`; versiones con lenguaje y framework (`planner_contract.v3`, `generated_test.v2`) y `validar_versionado()` (EN-17 #129) |
| `src/qagent/lenguajes/` | Adaptadores por lenguaje (EN-17 #129): interfaz `LanguageAdapter`, registro y detección; Python completo, JS/TS y Java solo detectan. Ver su `README.md` y ADR-007 |
| `tests/` | Pruebas del sistema; reflejan `src/` (`almacenamiento`, `analysis`, `app`, `config`, `lenguajes`, `llm`, `orchestrator`, `proyectos`, `sandbox`, `storage`) y `tests/frontend/` para la estructura de la interfaz |
| `test.py` | Ejecuta todas las pruebas con un comando (lint, formato y pytest) |
| `pyproject.toml` | Dependencias, extra `dev`, configuración de pytest y ruff, script `qagent` |
| `CLAUDE.md` | Guía específica para Claude Code (importa este archivo) |
| `docs/arquitectura.md` | Arquitectura del sistema y modelo GAIA |
| `docs/decisiones/` | ADR (decisiones técnicas): ADR-001 modelos por agente, ADR-002 análisis con `ast`, ADR-003 frontend modular, ADR-004 nombre único QAgent, ADR-005 distribución (instalador y PyPI), ADR-007 adaptadores por lenguaje |
| `packaging/windows/` | Ejecutable e instalador de Windows: receta de PyInstaller (`qagent.spec`), instalador de Inno Setup (`qagent.iss`), ícono, imágenes del asistente (`asistente/`) y requisitos que ve quien instala. Se construye con `scripts/construir_windows.py` |
| `scripts/` | Herramientas del equipo: verificar el paquete instalado y construir el ejecutable de Windows |
| `docs/desarrollo.md` | Guía del equipo: entorno, pruebas, sandbox, distribución y estructura del repositorio (el README es la portada para usuarios) |
| `docs/evidencias/` | Informes de cada tarea terminada para Notion: un `.md` por issue, HU, EN, SPK, TA o FIX, y nada más. No se versiona (`.gitignore`). Se escriben con la Skill `documentar-issue` |
| `.claude/skills/documentar-issue/` | Skill del equipo para documentar tareas: formato del informe, plantilla y script que incrusta imágenes en el `.md` |
| `bench/` | Banco de pruebas con bugs sembrados |

## Reglas que no se rompen

- **Nunca ejecutar código del usuario ni tests generados fuera del sandbox.** El análisis del código del usuario es solo estático (AST).
- **Los agentes no se llaman entre sí:** todo pasa por el orquestador y los contratos de `src/qagent/contracts/`. Si cambia un contrato, se actualiza su schema y su test.
- **El valor esperado de una aserción sale del contrato del Planner**: firma, tipos y docstring de una función, o la declaración de la ruta (`response_model`, `status_code`, modelos Pydantic) de un endpoint. Nunca de ejecutar el código.
- **Nunca relajar ni borrar aserciones para que un test pase.**
- **Claves solo en `~/.qagent/.env`.** Nunca en código, logs, tests, commits ni dentro del contenedor.
- **Datos del usuario solo en `~/.qagent/`** (`.env`, `config.local.toml`, recientes, demostración): el programa nunca escribe en su propia carpeta, que instalado puede ser de solo lectura (TA-06). La pantalla Configuración guarda en `config.local.toml`; el `config.toml` del equipo solo se cambia a mano y se versiona.
- **Modelos y precios solo desde `src/qagent/config/config.toml`** (se versiona, sin claves), nunca hardcodeados (ver `docs/decisiones/ADR-001-modelos.md`).
- **Tests del sistema con la IA simulada:** ningún test de `tests/` debe llamar a una API real.
- **Los tests no dependen de Docker ni de internet**, salvo los marcados `docker` o `red` (se omiten si no hay). Docker se simula en las demás.
- **La lógica no depende de la interfaz:** `app/` llama a `proyectos/`, `analysis/`, `sandbox/`…, nunca al revés (la lógica no importa `qagent.app` ni `webview`).
- **Frontend:** toda la interfaz (HTML, CSS y JS) vive en `src/qagent/frontend/`; el resto de `src/` no guarda pantallas ni demos (lo verifica `tests/frontend/`). Un componente por pantalla o modal en `src/qagent/frontend/componentes/`; colores, tipografía y logo en `src/qagent/frontend/css/tokens.css` (sin colores literales: todo es `var(--token)`, lo verifica `tests/frontend/`); sin bundler, sin módulos ES ni `fetch` de HTML (ver ADR-003).
- **Un solo nombre:** todo identificador nuevo usa `qagent` / QAgent. No introducir `pyagent` fuera del código de compatibilidad (ADR-004).

## Estilo de código

- Python 3.10+, type hints en funciones públicas y docstrings en español.
- Ruff como linter y formateador; no agregar otras herramientas sin un ADR.
- Funciones pequeñas y puras donde se pueda: facilita los tests y el mutation testing.

## Flujo de trabajo

- Ramas desde `develop`: `feat/`, `fix/`, `refactor/`, `test/`, `docs/`, `chore/` + ID del backlog. Ej.: `feat/en-01-contratos`.
- Commits: `tipo(ID): mensaje`. Ej.: `feat(EN-01): add planner contract schema`.
- Todo entra por PR a `develop` con la plantilla de `.github/pull_request_template.md` y al menos 1 aprobación.
- Cada PR indica el ítem del backlog (HU, EN, SPK, EV, DO) y sus criterios de aceptación.
- **Documentación de cada tarea:** al terminarla, un informe `.md` en `docs/evidencias/` con el título `<TIPO>-<NN> - <Título>` (`###` si no tiene número de backlog) y las secciones Resumen, Objetivo, Qué se revisó y qué se hizo (tabla), Pruebas e Imprevistos. La plantilla y las reglas están en `.claude/skills/documentar-issue/`.
- **Autoría:** commits, PR e issues son del integrante del equipo que los hace. Un asistente de IA nunca se agrega como autor ni coautor: sin `Co-Authored-By:`, sin «Generated with …» ni firmas equivalentes.

## Para ahorrar tokens

- Lee solo los archivos del módulo que vas a tocar; no recorras todo el repositorio.
- Antes de proponer una dependencia o un cambio de alcance, dilo explícitamente y ofrece la alternativa más simple.