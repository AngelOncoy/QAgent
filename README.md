# PyAgent

Sistema multiagente que genera y valida automáticamente pruebas unitarias
(pytest) para código Python 3.10+, usando LLMs y la metodología GAIA.

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
.venv\Scripts\activate
pip install -e .[dev]      # disponible cuando se agregue pyproject.toml
copy .env.example .env     # completar las claves
pytest
```

Para desarrollar sin gastar tokens: `set PYAGENT_FAKE_LLM=1`.

## Estructura

| Carpeta | Contenido |
|---|---|
| `src/pyagent/` | Código del sistema (agentes, orquestador, sandbox, app) |
| `contracts/` | JSON Schema de los contratos entre agentes |
| `docs/` | Arquitectura y decisiones (ADR) |
| `bench/` | Banco de pruebas con bugs sembrados |
| `tests/` | Pruebas del propio sistema |

## Equipo

Castillo Pezo, Mateo · Oncoy Patricio, Angel · Rodríguez Malca, Rodrigo · Sanchez Vargas, Adrián