# ADR-003: Frontend separado y modular por componentes

- **Estado:** Aceptado
- **Fecha:** 2026-10-08
- **Ítem:** refactor de modularidad y buenas prácticas (sin ID de backlog asignado)
- **Responsable:** Oncoy Patricio, Angel
- **Relacionado:** EN-08 (aplicación de escritorio), HU-01, HU-02, HU-03, ADR-001, ADR-002

## 1. Contexto

La interfaz vivía en un único archivo, `src/pyagent/app/ui/index.html`, de 2070 líneas: CSS (~415 líneas), HTML de ocho pantallas y tres modales, y ~1200 líneas de JavaScript con variables globales. Cualquier cambio de una pantalla obligaba a tocar ese archivo, y el frontend estaba dentro del paquete Python del backend.

Además:

- El logo cambió y estaba escrito en línea en el HTML, con colores fijos en el CSS; no había un lugar único para colores, tipografía y logo.
- Las pruebas manipulaban `sys.path` en varias `conftest.py`, no reflejaban la estructura de `src/`, y no había un comando único para ejecutarlas todas.
- `src/pyagent/app/` mezclaba el puente pywebview con lógica de negocio (clonar, abrir, recientes, vista previa).
- Faltaba `pyproject.toml`, aunque AGENTS.md ya documentaba `pip install -e .[dev]`.

## 2. Decisión

1. **Frontend fuera del backend.** La interfaz pasa a `frontend/` en la raíz. `src/pyagent/` queda como backend; `desktop.py` solo la carga (`FRONTEND_DIR`).
2. **Un componente por pantalla o modal**, en `frontend/componentes/<carpeta>/`, con su JavaScript (que incluye su HTML como plantilla y se registra con `registrarComponente`) y, si hace falta, su CSS. `index.html` queda como esqueleto con marcadores `data-componente`.
3. **Scripts clásicos, sin bundler ni módulos ES.** Todos los scripts comparten el ámbito global y su orden de carga es explícito en `index.html`.
4. **Tokens de diseño en `frontend/css/tokens.css`**: estructura, paleta, marca, tipografía y rutas del logo. Ningún componente escribe colores literales: todos usan `var(--token)`. El logo se vectoriza en `frontend/assets/logo/`.
5. **Lógica de proyectos en `src/pyagent/proyectos/`** (`clonador`, `proyecto_local`, `recientes`, `vista_previa`), sin dependencia de pywebview. `app/` conserva solo `desktop.py`.
6. **Pruebas que reflejan `src/`** (`tests/analysis`, `llm`, `proyectos`, `app`, …), sin `sys.path` manual; los marcadores `docker` y `red` se registran una vez en `pyproject.toml`; el runner `python test.py` ejecuta lint, formato y todas las pruebas con la IA simulada. `tests/frontend/` verifica la estructura del frontend.
7. **`pyproject.toml`** con las dependencias, el extra `dev`, la configuración de pytest y ruff, y el script `qagent`. El paquete se instala en modo editable.

## 3. Alternativas evaluadas

| Alternativa | Resultado |
|---|---|
| **Dejar el archivo único** | Descartada: es el problema de partida. |
| **Framework (React, Vue) con bundler (Vite, webpack)** | Descartada: agrega herramientas, Node y un paso de compilación a una interfaz de escritorio local; AGENTS.md pide no sumar herramientas sin un ADR y esta no se justifica por tamaño. |
| **Módulos ES (`import`/`export`)** | Descartada: bloqueados con `file://` en WebView2 y obligan a reescribir los `onclick="…"` del HTML. |
| **Un `.html` por componente cargado con `fetch`** | Probada y descartada. Funcionaba en la aplicación, pero `fetch` no funciona con `file://`: abrir `index.html` con doble clic dejaba de servir y la demo exigía levantar un servidor HTTP. |
| **Un `.html` por componente unido con un script de compilación** | Descartada: añade un paso que hay que recordar ejecutar. |
| **HTML del componente como plantilla dentro de su `.js` (elegida)** | Funciona con `file://` y con pywebview sin servidor propio; cada componente sigue siendo una carpeta autocontenida. |

## 4. Consecuencias

**Positivas**

- Una pantalla se cambia en su carpeta; el mayor archivo de componente tiene 287 líneas frente a las 2070 originales. `index.html` pasó a ~90 líneas.
- Colores de estructura, paleta y marca, tipografía y logo se cambian en un solo archivo.
- `python test.py` da una respuesta única; `tests/frontend/` impide dejar archivos sin enlazar o componentes sin registrar.
- La lógica de proyectos se prueba sin pywebview, y la dependencia va solo de la interfaz hacia la lógica.
- Sin Node ni compilación: el frontend es editable con cualquier editor.

**Costos y límites**

- Los scripts comparten ámbito global: no hay aislamiento entre componentes y el orden de carga importa (lo vigila `tests/frontend/`).
- El HTML vive dentro de plantillas JavaScript, sin resaltado de HTML en el editor; hay que escapar `` ` `` y `${`.
- `--logo-icono` usa una ruta relativa a `css/`, por lo que la regla `.logo` debe permanecer en `css/layout.css`.
- **Colores solo como tokens.** Los 333 colores literales que había en los componentes (hexadecimales y `rgba`) pasaron a una paleta de unos 130 tokens en `tokens.css`, y una prueba (`tests/frontend/`) falla si reaparece uno. Costo: un truco como `` `${color}33` `` (opacidad en hexadecimal) ya no funciona con `var(--…)`; se usan tokens con opacidad (`-aNN`).
- Las fuentes (Inter, JetBrains Mono) siguen cargándose desde Google Fonts; sin internet se usa la fuente del sistema.
- El paquete requiere instalación editable: `config.toml` y `contracts/` se buscan relativos a la raíz del repositorio.
- `python src/pyagent/app/desktop.py` ya no funciona sin instalar el paquete (`pip install -e .[dev]`); se usa `qagent` o `python -m pyagent`.

## 5. Seguimiento

- Incluir las fuentes localmente.
- Unificar la paleta: hoy hay valores casi iguales con nombres distintos (por ejemplo varios tonos de rojo y de rosa para estados) que podrían reducirse a un conjunto menor.
- Valorar módulos ES si algún día se abandona `file://` como forma de abrir la demostración.
