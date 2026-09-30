# QAgent

Sistema multiagente que genera y valida automáticamente pruebas pytest para código Python 3.10+ (pruebas unitarias de funciones y pruebas
de endpoints FastAPI), usando LLMs y la metodología GAIA.

> En desarrollo - Demo no disponible

## Cómo funciona

1. **Planner**: analiza el código (AST, firmas, docstrings) y decide qué casos probar.
2. **Generator**: escribe el test pytest de cada función.
3. **Reviewer/Executor**: ejecuta el test en un sandbox Docker sin red, verifica
   que las aserciones sean legítimas (sin *Assertion Laundering*) y decide si
   reintentar (máx. 3 intentos).

Métricas por test: Pass Rate, cobertura de líneas/ramas, iteraciones,
tokens por agente y Mutation Score (solo en funciones críticas).

## Requisitos

- Windows 10/11 · Python 3.10+ · Docker Desktop · Git

## Desarrollo

```bash
python -m venv .venv
.venv\Scripts\activate       # en Linux: source .venv/bin/activate
pip install -r requirements.txt   # en Linux para GUI: pip install "pywebview[qt]"
copy .env .env              # completar las claves (en Linux: cp .env.example .env)
pytest
```

Para desarrollar sin gastar tokens: `set PYAGENT_FAKE_LLM=1` (en Linux: `export PYAGENT_FAKE_LLM=1`).

## Ejecución de la aplicación

Para iniciar la aplicación de escritorio:

```bash
python src/pyagent/app/desktop.py
```

## Estructura del repositorio

```text
QAgent/
├── .github/
│   └── pull_request_template.md   Plantilla que GitHub carga en cada PR nuevo
├── bench/                         Banco de pruebas propio con bugs sembrados (EN-12, EN-16)
├── contracts/                     JSON Schema de los mensajes entre agentes (EN-01)
├── docs/
│   ├── arquitectura.md            Arquitectura del sistema, pipeline y modelo GAIA (EN-01)
│   └── decisiones/                Decisiones técnicas (ADR)
│       ├── ADR-001-modelos.md         Modelo por agente, precios y plan de gasto (SPK-01)
│       └── ADR-002-mapa-de-codigo.md  Análisis con ast frente a Graphify (SPK-02)
├── src/pyagent/                   Código de QAgent (paquete interno `pyagent`)
│   ├── agents/                    Planner, Generator y Reviewer (EN-04)
│   ├── analysis/                  Analizador estático con ast: funciones, endpoints FastAPI, llama_a (EN-02, EN-14)
│   ├── app/                       Aplicación de escritorio pywebview y puente JS ↔ Python (EN-08)
│   ├── llm/                       Cliente LLM real y simulado; registro de tokens y costo (EN-05, EN-11)
│   ├── orchestrator/              Máquina de estados de la corrida (EN-04)
│   └── sandbox/                   Ejecución de pruebas en Docker, sin red (EN-03)
├── tests/                         Pruebas del propio sistema, siempre con la IA simulada
│   └── test_smoke.py              Prueba mínima para verificar que pytest corre; se borra cuando haya tests reales
├── .gitignore                     Archivos que no se suben (.env, .venv, cachés, .pyagent/, .idea)
├── AGENTS.md                      Reglas y contexto para asistentes de IA (Claude, Copilot, Cursor)
├── config.toml                    Modelos, precios, topes de gasto y reintentos por agente (se versiona, sin claves)
└── README.md                      Este archivo
```

**Archivos que existen en tu carpeta pero no se suben al repositorio:**

| Archivo o carpeta | Para qué sirve |
|---|---|
| `.env` | Claves de las APIs de IA. Cada integrante tiene el suyo (ver "Desarrollo"). |
| `.venv/` | Entorno virtual de Python de cada integrante. |
| `.pyagent/` | Se crea dentro del proyecto que QAgent analiza: corridas, specs y pruebas aprobadas (EN-07). |
| `~/.pyagent/recientes.json` | Lista de proyectos recientes de la Bienvenida (HU-01, HU-03). Vive en la carpeta del usuario. |

**Notas:**

- Los archivos `__init__.py` vacíos de `src/pyagent/` indican a Python que cada carpeta es un paquete importable.
- Los archivos `.gitkeep` solo sirven para que Git guarde carpetas vacías. Se borran cuando la carpeta tenga su primer archivo real.
- `pyproject.toml` (dependencias e instalación con `pip install -e .[dev]`) se agrega con EN-08.

## Equipo

Castillo Pezo, Mateo · Oncoy Patricio, Angel · Rodríguez Malca, Rodrigo · Sanchez Vargas, Adrián