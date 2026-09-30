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

## Estructura

| Carpeta | Contenido |
|---|---|
| `src/pyagent/` | Código del sistema (agentes, orquestador, sandbox, app). El paquete interno se llama `pyagent`. |
| `contracts/` | JSON Schema de los contratos entre agentes |
| `docs/` | Arquitectura (`arquitectura.md`) y decisiones (`decisiones/ADR-*.md`) |
| `bench/` | Banco de pruebas con bugs sembrados |
| `tests/` | Pruebas del propio sistema |
| `config.toml` | Modelos, precios y topes por agente (se versiona; no contiene claves) |

## Equipo

Castillo Pezo, Mateo · Oncoy Patricio, Angel · Rodríguez Malca, Rodrigo · Sanchez Vargas, Adrián