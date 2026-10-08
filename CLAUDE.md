# CLAUDE.md — QAgent

@AGENTS.md

Lo anterior (qué es el proyecto, alcance, reglas que no se rompen, estilo y flujo de trabajo) vale también para Claude Code. Esta página añade solo lo que conviene saber al trabajar aquí.

## Comandos

```bash
pip install -e .[dev]          # instalación editable, una vez por máquina (pyproject.toml)
python test.py                 # lint + formato + TODAS las pruebas, con la IA simulada
python test.py --rapido        # sin lint, sin pruebas de Docker ni de red
python test.py -k clonador     # los demás argumentos van a pytest
qagent                         # abre la app (también: python -m pyagent)
ruff check . && ruff format .  # lint y formato (bench/ está excluido a propósito)
```

`python test.py` es la verificación estándar antes de dar algo por terminado. Si `python` no resuelve o falta una dependencia, usa el entorno del repo: `.venv\Scripts\python.exe` en Windows.

## Mapa del repositorio

| Ruta | Qué hay | Dónde se documenta |
|---|---|---|
| `src/pyagent/` | Backend. `app/desktop.py` es solo el puente pywebview; la lógica de proyectos está en `proyectos/` | `docs/arquitectura.md` |
| `frontend/` | Interfaz HTML/CSS/JS sin build, un componente por pantalla | `frontend/README.md` |
| `tests/` | Refleja `src/` (`analysis`, `app`, `llm`, `orchestrator`, `proyectos`, `sandbox`, `storage`) más `frontend/` | — |
| `docs/decisiones/` | ADR: modelos (001), análisis con `ast` (002), frontend modular (003) | — |

Regla de dependencia: la interfaz (`app/`) llama a la lógica; la lógica (`proyectos/`, `analysis/`, `sandbox/`…) nunca importa `pyagent.app` ni `webview`.

## Frontend: lo que hay que saber

Detalle completo en `frontend/README.md`. Lo esencial:

- **Un componente = una carpeta** en `frontend/componentes/`, con su `.js` (el HTML va en una plantilla y se registra con `registrarComponente`) y, si hace falta, su `.css`. Se enlaza en `frontend/index.html` con un marcador `data-componente` y los `<link>`/`<script>`.
- **Scripts clásicos con ámbito global**, sin módulos ES, sin `fetch` de HTML, sin bundler. El orden de los `<script>` importa.
- **Colores, tipografía y logo se cambian en `frontend/css/tokens.css`.** Ningún componente lleva colores literales: todo es `var(--token)` (lo exige `tests/frontend/`). Un color nuevo se declara en `tokens.css`; no se concatena texto a un color (`${c}33`), se usa un token con opacidad (`-aNN`).
- **La regla `.logo` debe permanecer en `css/layout.css`:** `--logo-icono` usa una ruta relativa a `css/`.
- **Nombres técnicos que no se renombran:** `pyagent-sandbox:base`, `.pyagent/`, el módulo `pyagent` y `window.onPyAgentEvent`.
- Tras tocar el frontend: `python test.py` (incluye `tests/frontend/`) y, si cambió algo visible, revisar la ventana real con `qagent`.

## Pruebas

- Todas usan la IA simulada (`PYAGENT_FAKE_LLM=1`, que `test.py` fija solo). Ninguna llama a una API real.
- Las que necesitan Docker llevan `@pytest.mark.docker` y se omiten si Docker Desktop no está iniciado; las que necesitan internet, `@pytest.mark.red`. Cualquier otra prueba debe poder correr sin Docker ni red: simula `pyagent.sandbox.estado.estado_docker`.
- No relajar ni borrar aserciones para que una prueba pase.

## Trabajar con Git en este repositorio

- Ramas y commits según AGENTS.md (`tipo(ID): mensaje`). Si el cambio no tiene ID de backlog, pregúntalo en lugar de inventarlo.
- No hacer `git commit` ni `git push` salvo que se pida expresamente.
