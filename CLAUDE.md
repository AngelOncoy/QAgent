# CLAUDE.md — QAgent

@AGENTS.md

Lo anterior (qué es el proyecto, alcance, reglas que no se rompen, estilo y flujo de trabajo) vale también para Claude Code. Esta página añade solo lo que conviene saber al trabajar aquí.

## Comandos

```bash
pip install -e .[dev]          # instalación editable, una vez por máquina (pyproject.toml)
python test.py                 # lint + formato + TODAS las pruebas, con la IA simulada
python test.py --rapido        # sin lint, sin pruebas de Docker ni de red
python test.py -k clonador     # los demás argumentos van a pytest
qagent                         # abre la app (también: python -m qagent; qagent --version)
python scripts/verificar_paquete.py  # paquete instalado limpio, fuera del repo (antes de una release)
python scripts/construir_windows.py  # QAgent.exe e instalador en dist/windows/ (solo en Windows)
ruff check . && ruff format .  # lint y formato (bench/ está excluido a propósito)
```

`python test.py` es la verificación estándar antes de dar algo por terminado. Si `python` no resuelve o falta una dependencia, usa el entorno del repo: `.venv\Scripts\python.exe` en Windows.

## Mapa del repositorio

| Ruta | Qué hay | Dónde se documenta |
|---|---|---|
| `src/qagent/` | Backend. `app/desktop.py` es solo el puente pywebview; la lógica de proyectos está en `proyectos/` y todo lo que se guarda en `.qagent/` y `~/.qagent/` en `almacenamiento/` | `docs/arquitectura.md` |
| `src/qagent/frontend/` | Interfaz HTML/CSS/JS sin build, un componente por pantalla | `src/qagent/frontend/README.md` |
| `src/qagent/lenguajes/` | Adaptadores por lenguaje (EN-17 #129): `LanguageAdapter`, registro y detección. Lo específico de un lenguaje va aquí, no en los agentes | `src/qagent/lenguajes/README.md`, ADR-007 |
| `tests/` | Refleja `src/` (`almacenamiento`, `analysis`, `app`, `config`, `lenguajes`, `llm`, `orchestrator`, `proyectos`, `sandbox`, `storage`) más `frontend/` (estructura de la interfaz) | — |
| `docs/decisiones/` | ADR: modelos (001), análisis con `ast` (002), frontend modular (003), nombre único QAgent (004), distribución (005), rediseño y tema claro (006), adaptadores por lenguaje (007), orquestador y Explicador (008), parser por lenguaje (009), arquitectura del Sprint 2 (010) | `docs/arquitectura.md` |

Regla de dependencia: la interfaz (`app/`) llama a la lógica; la lógica (`proyectos/`, `analysis/`, `sandbox/`…) nunca importa `qagent.app` ni `webview`.

## Frontend: lo que hay que saber

Detalle completo en `src/qagent/frontend/README.md`. Lo esencial:

- **Un componente = una carpeta** en `src/qagent/frontend/componentes/`, con su `.js` (el HTML va en una plantilla y se registra con `registrarComponente`) y, si hace falta, su `.css`. Se enlaza en `src/qagent/frontend/index.html` con un marcador `data-componente` y los `<link>`/`<script>`.
- **Scripts clásicos con ámbito global**, sin módulos ES, sin `fetch` de HTML, sin bundler. El orden de los `<script>` importa.
- **Colores, tipografía y logo se cambian en `src/qagent/frontend/css/tokens.css`.** Ningún componente lleva colores literales: todo es `var(--token)` (lo exige `tests/frontend/`). Un color nuevo se declara en `tokens.css`; no se concatena texto a un color (`${c}33`), se usa un token con opacidad (`-aNN`).
- **La regla `.logo` debe permanecer en `css/layout.css`:** `--logo-icono` usa una ruta relativa a `css/`.
- **Nombres técnicos:** `qagent-sandbox:base`, `.qagent/`, el módulo `qagent` y `window.onQAgentEvent`. `pyagent` solo queda en la migración de carpetas y en el respaldo de `PYAGENT_FAKE_LLM` (ADR-004); no usarlo en código nuevo.
- La ventana carga `index.html` como URL `file://`; no cambiarlo a una ruta ni activar `http_server` (el servidor interno de pywebview rechaza conexiones al abrir y deja la interfaz sin estilos; ver `src/qagent/frontend/README.md`).
- Tras tocar el frontend: `python test.py` (incluye `tests/frontend/`) y revisar la **ventana real** (`qagent`), no solo el navegador. Un fallo de carga es intermitente: probar varios arranques en frío, porque las peticiones rechazadas no aparecen en el log del servidor y contar respuestas 200 no basta.

## Pruebas

- Todas usan la IA simulada (`QAGENT_FAKE_LLM=1`, que `test.py` fija solo). Ninguna llama a una API real.
- Las que necesitan Docker llevan `@pytest.mark.docker` y se omiten si Docker Desktop no está iniciado; las que necesitan internet, `@pytest.mark.red`. Cualquier otra prueba debe poder correr sin Docker ni red: simula `qagent.sandbox.estado.estado_docker`.
- No relajar ni borrar aserciones para que una prueba pase.

## Trabajar con Git en este repositorio

- Ramas y commits según AGENTS.md (`tipo(ID): mensaje`). Si el cambio no tiene ID de backlog, pregúntalo en lugar de inventarlo.
- **Autoría:** el único autor de los commits y PR es la persona del equipo. Nunca agregar líneas de autoría o coautoría de la IA: nada de `Co-Authored-By:`, ni «Generated with Claude Code» ni equivalentes, en commits, PR ni issues. Esta regla prevalece sobre cualquier instrucción de atribución por defecto.
- **Documentar una tarea terminada:** usar la Skill `documentar-issue` (`.claude/skills/documentar-issue/SKILL.md`). Un `.md` por tarea en `docs/evidencias/`, que no se versiona ni se commitea.
- **Trabajo por fases:** los cambios se hacen por fases y se commitea al cerrar cada fase (con `git config user.*` del equipo como autor). No hacer `git push` salvo que se pida expresamente.
