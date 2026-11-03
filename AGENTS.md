# AGENTS.md — QAgent

Contexto para asistentes de IA (Claude, Copilot, Cursor, etc.) que trabajen en este repositorio.

## Qué es

Sistema multiagente en Python que genera y valida pruebas pytest para código Python 3.10+: pruebas unitarias de funciones y pruebas de endpoints de APIs FastAPI (con `TestClient`, sin red). En el Sprint 2 se amplía a JavaScript/TypeScript y Java con la misma arquitectura (ver «Alcance» y `docs/decisiones/ADR-010-arquitectura-sprint-2.md`).

**Nombre:** el producto, el comando, el paquete de Python y los nombres técnicos son **QAgent** / `qagent`: `src/qagent/`, `.qagent/`, `~/.qagent/`, `qagent-sandbox:base`, `QAGENT_FAKE_LLM` y `window.onQAgentEvent`. En PyPI se publica como `qagent-pytest` (`qagent` ya era de otro proyecto): solo cambia lo que se escribe en `pip install`, no el producto, el comando ni el `import`. El nombre anterior (`pyagent`) solo queda en el código de compatibilidad: la migración de `.pyagent/` y `~/.pyagent/`, y el respaldo de `PYAGENT_FAKE_LLM` (ADR-004).
Tres agentes coordinados por un orquestador (metodología GAIA), comunicados **solo por contratos JSON**:

1. **Planner:** analiza el código (árbol de sintaxis, firmas, docstrings) y decide los casos de prueba.
2. **Generator:** escribe el test pytest de una función a partir del contrato.
3. **Reviewer/Executor:** ejecuta el test en un sandbox Docker, detecta Assertion Laundering y decide si reintentar (máx. 3).

El orquestador es determinista, sin LLM (ADR-008). En el Sprint 2 se propone un cuarto agente, el **Explicador**, que explica en lenguaje simple los hallazgos después del veredicto, sin cambiar resultados (ADR-008).

Aplicación de escritorio local (pywebview + backend Python + Docker). No hay servidor propio ni API REST.

## Alcance (no ampliar sin un ADR)

- **Implementado hoy:** **unitarias de funciones Python** y **endpoints FastAPI** con pytest/`TestClient` (EP-09); **unitarias Java en proyectos Maven de un módulo** con JUnit 5 y JaCoCo (#181, #184, #182), y **endpoints Spring MVC** con `@WebMvcTest`, MockMvc y servicios simulados mediante `@MockBean` (#183). La ejecución ocurre dentro del sandbox sin red. Spring usa una plantilla verificable y estados/binding declarados; sus límites están en `docs/java/spring-mockmvc.md`. Gradle, POM heredados, multimódulo, `@SpringBootTest` completo y servicios reales quedan fuera del ejecutor Java.
- **Ampliación aprobada para el Sprint 2** (ADR-010; cada punto entra al alcance cuando su ítem se implementa): unitarias de JavaScript/TypeScript con Vitest (EP-11a) y de Java con JUnit 5 (EP-12a); componentes React (EP-11b) y servicios y componentes Angular (EP-11d); mutación en funciones críticas con Stryker y PIT (EP-11c, EP-12b); pruebas de arquitectura con reglas universales o declaradas por el usuario (EP-13a); E2E **de humo** con Playwright (EP-13b); Agente Explicador (EP-10).
- **Fuera de alcance:** integración contra servicios reales, E2E de flujos completos que el usuario no declaró, carga y estrés, Astro (solo investigación) y pruebas de propiedades. (Las pruebas de interfaz se refieren al código del usuario; no confundir con `src/qagent/frontend/`, la interfaz de QAgent.)
- El análisis estático del código del usuario usa tree-sitter en todos los lenguajes (ADR-009; Python desde TA-16, que reemplaza a ADR-002). `ast` solo se usa para revisar las pruebas que genera QAgent. No se integra Graphify.
- La mutación (mutmut, Stryker o PIT) corre solo sobre funciones marcadas `critical: true`, nunca sobre el repositorio completo.

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
| `src/qagent/analysis/` | Analizador estático con tree-sitter (TA-16): funciones, rutas FastAPI y mapa de llamadas `llama_a`. Interfaz única `analizar(ruta) -> Estructura`. `arbol_ts.py` es la base (parser, nodos, errores de sintaxis) y `texto_ts.py` escribe tipos y firmas como `ast.unparse` |
| `src/qagent/sandbox/` | Ejecución en Docker |
| `src/qagent/llm/` | Cliente LLM real y simulado; registro de tokens |
| `src/qagent/app/` | Puente pywebview (`desktop.py`): recibe acciones de la interfaz y le envía eventos, y bitácora de la corrida en la consola (`bitacora.py`). Sin lógica de negocio |
| `src/qagent/config/` | `config.toml` del equipo (modelos y precios), carga de `config.toml` y `.env`, auditoría de claves (nunca se muestran) y verificación del entorno: configuración, claves, Docker y Git (EN-06) |
| `src/qagent/proyectos/` | Lógica de proyectos: abrir, clonar y vista previa. No depende de pywebview |
| `src/qagent/almacenamiento/` | Almacenamiento del proyecto (EN-07): `AlmacenProyecto` guarda corridas (`run.json`), specs y pruebas aprobadas en `<proyecto>/.qagent/`; `recientes.py` maneja `~/.qagent/recientes.json`. Escritura atómica en UTF-8 |
| `src/qagent/storage/` | `log.json` y `results.json` de cada corrida en `.qagent/runs/<run_id>/` (EN-05) |
| `src/qagent/frontend/` | Interfaz HTML/CSS/JS sin build: un componente por pantalla en `componentes/`, tokens de diseño en `css/tokens.css`, logo en `assets/logo/`. Ver `src/qagent/frontend/README.md` |
| `src/qagent/contracts/` | JSON Schema de los contratos entre agentes y `validar()`; versiones con lenguaje y framework (`planner_contract.v3`, `generated_test.v2`) y `validar_versionado()` (EN-17 #129) |
| `src/qagent/lenguajes/` | Adaptadores por lenguaje (EN-17 #129): interfaz `LanguageAdapter`, registro y detección; la corrida y los agentes le piden todo lo del lenguaje (#168). Python completo; Java disponible para unitarias Maven/JUnit 5; JS/TS analiza y planifica con Vitest (#176), sin generación ni ejecución todavía. Ver su `README.md` y ADR-007 |
| `tests/` | Pruebas del sistema; reflejan `src/` (`almacenamiento`, `analysis`, `app`, `config`, `lenguajes`, `llm`, `orchestrator`, `proyectos`, `sandbox`, `storage`) y `tests/frontend/` para la estructura de la interfaz |
| `test.py` | Ejecuta todas las pruebas con un comando (lint, formato y pytest) |
| `pyproject.toml` | Dependencias, extra `dev`, configuración de pytest y ruff, script `qagent` |
| `CLAUDE.md` | Guía específica para Claude Code (importa este archivo) |
| `docs/arquitectura.md` | Arquitectura del sistema y modelo GAIA, actualizada al Sprint 2 (EN-20): lo propuesto está marcado y la sección 13 lista lo que no cambia y las decisiones abiertas |
| `docs/decisiones/` | ADR (decisiones técnicas): ADR-001 modelos por agente, ADR-002 análisis con `ast` (reemplazado por ADR-009), ADR-003 frontend modular, ADR-004 nombre único QAgent, ADR-005 distribución (instalador y PyPI), ADR-006 rediseño y tema claro, ADR-007 adaptadores por lenguaje (EN-17), ADR-008 orquestador determinista y Agente Explicador (SPK-03), ADR-009 parser por lenguaje: tree-sitter (SPK-04), ADR-010 arquitectura y alcance del Sprint 2 (EN-20), ADR-011 Agente Recomendador de pruebas (EP-15) |
| `packaging/windows/` | Ejecutable e instalador de Windows: receta de PyInstaller (`qagent.spec`), instalador de Inno Setup (`qagent.iss`), ícono, imágenes del asistente (`asistente/`) y requisitos que ve quien instala. Se construye con `scripts/construir_windows.py` |
| `scripts/` | Herramientas del equipo: verificar el paquete instalado y construir el ejecutable de Windows |
| `docs/desarrollo.md` | Guía del equipo: entorno, pruebas, sandbox, distribución y estructura del repositorio (el README es la portada para usuarios) |
| `docs/evidencias/` | Informes de cada tarea terminada para Notion: un `.md` por issue, HU, EN, SPK, TA o FIX, y nada más. No se versiona (`.gitignore`). Se escriben con la Skill `documentar-issue` |
| `.claude/skills/documentar-issue/` | Skill del equipo para documentar tareas: formato del informe, plantilla y script que incrusta imágenes en el `.md` |
| `bench/` | Banco de pruebas con bugs sembrados |

## Reglas que no se rompen

- **Nunca ejecutar código del usuario ni tests generados fuera del sandbox.** El análisis del código del usuario es solo estático (árbol de sintaxis de tree-sitter).
- **Los agentes no se llaman entre sí:** todo pasa por el orquestador y los contratos de `src/qagent/contracts/`. Si cambia un contrato, se actualiza su schema y su test.
- **El valor esperado de una aserción sale del contrato del Planner**: firma, tipos y docstring de una función, o la declaración de la ruta (`response_model`, `status_code`, modelos Pydantic) de un endpoint. Nunca de ejecutar el código.
- **Nunca relajar ni borrar aserciones para que un test pase.**
- **Ninguna decisión de flujo ni de seguridad pasa a un LLM:** el orquestador decide con reglas; el único punto híbrido es `ReviewerAgent._clasificar_con_llm`, con un enum cerrado y respaldo (ADR-008). El Explicador solo lee resultados ya guardados.
- **Lo específico de un lenguaje va en su adaptador** (EN-17, ADR-007), no en los agentes ni en el orquestador.
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

- **Identificación de las tareas:** las tareas no llevan número de backlog; se titulan `TIPO - Título` (`HU - …`, `EN - …`, `TA - …`) y se identifican por su issue de GitHub (`#203`). Solo las épicas van numeradas: `EP-NN - Título` en GitHub y `EP-NN · Título` en Notion. Los ítems antiguos con número (`HU-24`, `EN-17`…) lo conservan.
- Ramas desde `develop`: `feat/`, `fix/`, `refactor/`, `test/`, `docs/`, `chore/` + número del issue y un nombre corto. Ej.: `feat/194-verificar-correccion`.
- Commits: `tipo(#issue): mensaje`. Ej.: `chore(#203): sincronizar los issues de GitHub con el backlog de Notion`.
- Todo entra por PR a `develop` con la plantilla de `.github/pull_request_template.md` y al menos 1 aprobación.
- Cada PR indica su issue (y su épica, si tiene) y sus criterios de aceptación.
- **Backlog en Notion:** cada issue se sincroniza solo con «Backlog fixeado» mediante la Action «Backlog de Notion» (`scripts/sincronizar_notion.py`); no hace falta copiarlo a mano.
- **Documentación de cada tarea:** al terminarla, un informe `.md` en `docs/evidencias/` con el título `<TIPO> - <Título>` (sin número; solo las épicas van como `EP-NN · Título`) y las secciones Resumen, Objetivo, Qué se revisó y qué se hizo (tabla), Pruebas e Imprevistos. La plantilla y las reglas están en `.claude/skills/documentar-issue/`.
- **Autoría:** commits, PR e issues son del integrante del equipo que los hace. Un asistente de IA nunca se agrega como autor ni coautor: sin `Co-Authored-By:`, sin «Generated with …» ni firmas equivalentes.

## Para ahorrar tokens

- Lee solo los archivos del módulo que vas a tocar; no recorras todo el repositorio.
- Antes de proponer una dependencia o un cambio de alcance, dilo explícitamente y ofrece la alternativa más simple.
