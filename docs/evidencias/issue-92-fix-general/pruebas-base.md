# Pruebas base — issue #92

Fecha: 2026-10-17

## Entorno

- Windows, PowerShell.
- Python 3.14.7 (el proyecto requiere Python 3.10+).
- Git 2.55.0.windows.5.
- Node 24.20.0.
- Docker CLI 29.7.2; daemon de Docker Desktop no iniciado.
- QAgent 0.1.0.
- IA forzada a simulada con `QAGENT_FAKE_LLM=1`.
- Microsoft Edge controlado con Playwright para el frontend estático.
- Browser plugin: no disponible; se aplicó el fallback de Playwright.

## Resultados

### Frontend

```text
python -m pytest tests/frontend -q
179 passed in 5.06s
```

### Suite rápida

```text
python test.py --rapido
1314 passed, 25 deselected in 69.10s
```

Coincide con la referencia funcional de 1314 casos aprobados y 25 excluidos.

### Suite oficial completa

```text
python test.py
All checks passed!                         # ruff check
201 files already formatted               # ruff format --check
1316 passed, 23 skipped in 56.30s          # pytest
```

Los dos casos adicionales respecto de la suite rápida corresponden a pruebas
marcadas `red` que terminaron correctamente. No se llamó a proveedores LLM: el
propio ejecutor fija `QAGENT_FAKE_LLM=1`.

### Diagnóstico de pruebas Docker

```text
python -m pytest -q -m docker -rs
23 skipped, 1316 deselected in 1.36s
```

Todos los casos se omitieron con el mensaje de que Docker Desktop no está
iniciado. No constituye un fallo del código, pero deja pendientes la ejecución
real, aislamiento, mutación y regresión dentro del contenedor.

## Validación renderizada

- URL local: `http://127.0.0.1:8765/`.
- Viewports: 1440×900 y 1024×700.
- Identidad: título `QAgent`, URL correcta y contenido no vacío.
- Overlay de framework: ninguno; el frontend no usa framework/bundler.
- Interacción: Funciones → Endpoints cambió correctamente `aria-selected`; una
  casilla individual pasó de marcada a desmarcada.
- Tabla de endpoints: 10 filas y 9 casillas habilitadas en la demo.
- Consola: un error por favicon 404; sin excepciones JavaScript.
- Evidencias temporales: `%TEMP%/qagent-issue92/`.

## Pendiente para cerrar la auditoría ambiental

1. Iniciar Docker Desktop y repetir `python test.py` y `pytest -m docker -q`.
2. Abrir `qagent` con `QAGENT_FAKE_LLM=1` y validar manualmente pywebview en
   1400×900, 1024×700 y el mínimo declarado 960×600.
3. Confirmar diálogos nativos de carpeta, clonación y exportación.
4. Comprobar una corrida simulada completa desde la ventana hasta Historial.
