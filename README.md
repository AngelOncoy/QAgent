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
pip install -e .[dev]       # instalación editable (en Linux para GUI: pip install "pywebview[qt]")
copy .env.example .env     # completar las claves (en Linux: cp .env.example .env)
python test.py
```

`pip install -e .[dev]` es obligatorio una vez por máquina: el paquete `pyagent` se instala apuntando a este repositorio, porque `config.toml` y `contracts/` se buscan junto a él.

### Pruebas

`python test.py` ejecuta **todas** las pruebas del sistema siempre con la IA simulada (no gasta tokens ni llama a ninguna API):

```bash
python test.py                 # lint (ruff) + formato + todas las pruebas
python test.py --rapido        # sin lint y sin las pruebas de Docker ni de internet
python test.py --sin-lint      # solo pytest
python test.py -k clonador     # cualquier otro argumento se pasa a pytest
```

Las pruebas que necesitan Docker (`-m docker`) se omiten solas si Docker Desktop no está iniciado. Las de la interfaz (`tests/frontend/`) comprueban que el frontend esté bien armado: archivos enlazados, componentes registrados y logo presente.

Para ejecutar pytest directamente sin gastar tokens: `set PYAGENT_FAKE_LLM=1` (en Linux: `export PYAGENT_FAKE_LLM=1`).

## Sandbox Docker

Las pruebas generadas se ejecutan solo dentro de un contenedor efímero: sin red, 1 CPU, 256 MB y 60 s como máximo (EN-03).
Con Docker Desktop abierto, construye una vez la imagen base `pyagent-sandbox:base` (necesita internet):

```bash
python -c "from pyagent.sandbox import construir_imagen_base; construir_imagen_base()"
```

Para probar el sandbox:

```bash
python test.py --sin-lint tests/sandbox                 # todo; las pruebas con Docker se omiten si no está iniciado
python test.py --sin-lint tests/sandbox -m "not docker" # solo pruebas unitarias, sin Docker
```

Las pruebas con Docker construyen la imagen base si falta (la primera vez tarda unos minutos).

## Ejecución de la aplicación

Para iniciar la aplicación de escritorio (tras `pip install -e .[dev]`):

```bash
qagent                  # o: python -m pyagent
```

Para ver solo la interfaz, sin Python, abre `frontend/index.html` en el navegador: funciona en modo demostración con datos simulados.

## Personalizar la interfaz

La interfaz (`frontend/`) es HTML, CSS y JavaScript sin compilación, con un componente por pantalla. Colores, tipografía y logo se cambian en un solo lugar, `frontend/css/tokens.css`, y el logo vive en `frontend/assets/logo/`. La guía completa (estructura, cómo agregar un componente, reglas de los tokens de color) está en [`frontend/README.md`](frontend/README.md).

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
│       ├── ADR-002-mapa-de-codigo.md  Análisis con ast frente a Graphify (SPK-02)
│       └── ADR-003-frontend-modular.md  Frontend separado y modular por componentes
├── frontend/                      Interfaz HTML/CSS/JS sin compilación (ver frontend/README.md)
│   ├── assets/                    Logo vectorizado (logo/) y fuentes Inter y JetBrains Mono (fuentes/)
│   ├── componentes/               Un componente por pantalla o modal: inicio, vista previa, monitor, informe…
│   ├── css/                       tokens.css (colores, tipografía, logo), layout.css y componentes.css
│   ├── js/                        Utilidades, estado, navegación y arranque
│   └── index.html                 Esqueleto con los marcadores de componentes
├── src/pyagent/                   Backend de QAgent (paquete interno `pyagent`)
│   ├── agents/                    Planner, Generator y Reviewer (EN-04)
│   ├── analysis/                  Analizador estático con ast: funciones, endpoints FastAPI, llama_a (EN-02, EN-14)
│   ├── app/                       Puente pywebview entre la interfaz y Python (EN-08); sin lógica de negocio
│   ├── config/                    Carga de config.toml y .env, auditoría de claves y verificación del entorno (EN-06)
│   ├── llm/                       Cliente LLM real y simulado; registro de tokens y costo (EN-05, EN-11)
│   ├── orchestrator/              Máquina de estados de la corrida (EN-04)
│   ├── proyectos/                 Abrir, clonar, recientes y vista previa de proyectos (HU-01 a HU-04); sin pywebview
│   ├── sandbox/                   Ejecución de pruebas en Docker, sin red (EN-03)
│   └── storage/                   Registro de corridas en `.pyagent/` (EN-07)
├── tests/                         Pruebas del propio sistema, siempre con la IA simulada; reflejan src/
│   ├── analysis/ · app/ · config/ · llm/ · orchestrator/ · proyectos/ · storage/
│   ├── sandbox/                   Unitarias con Docker simulado e integración (`-m docker`)
│   ├── frontend/                  Estructura de la interfaz: archivos enlazados y componentes registrados
│   └── test_contracts.py          Validación de los contratos JSON
├── .gitignore                     Archivos que no se suben (.env, .venv, cachés, .pyagent/, .idea)
├── AGENTS.md                      Reglas y contexto para asistentes de IA (Claude, Copilot, Cursor)
├── CLAUDE.md                      Guía para Claude Code (importa AGENTS.md)
├── config.toml                    Modelos, precios, topes de gasto y reintentos por agente (se versiona, sin claves)
├── pyproject.toml                 Dependencias, extra `dev`, configuración de pytest/ruff y el comando `qagent`
├── README.md                      Este archivo
├── requirements.txt               Equivale a `pip install -e .[dev]`
└── test.py                        Ejecuta todas las pruebas: `python test.py`
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
- `bench/` está excluido de ruff: tiene bugs sembrados a propósito y no debe reformatearse ni "arreglarse".

## Equipo

Castillo Pezo, Mateo · Oncoy Patricio, Angel · Rodríguez Malca, Rodrigo · Sanchez Vargas, Adrián