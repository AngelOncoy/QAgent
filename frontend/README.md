# Frontend de QAgent

Interfaz de la aplicación de escritorio: HTML, CSS y JavaScript **sin paso de compilación ni dependencias**. La carga pywebview (`src/pyagent/app/desktop.py`); sin pywebview funciona igual en modo demostración, con datos simulados.

Decisión de diseño: [ADR-003](../docs/decisiones/ADR-003-frontend-modular.md).

## Probarlo

| Qué | Cómo |
|---|---|
| Aplicación real | `qagent` (o `python -m pyagent`), tras `pip install -e .[dev]` en la raíz |
| Solo la interfaz, en modo demo | Abrir `frontend/index.html` en el navegador (no necesita servidor) |
| Verificar la estructura | `python test.py` (incluye `tests/frontend/`) |

## Estructura

```text
frontend/
├── index.html            Esqueleto: <div data-componente="..."> y la lista de <link>/<script>
├── assets/
│   ├── logo/             qagent-icono.svg (solo el hexágono) · qagent-logo.svg (completo)
│   └── fuentes/          Inter y JetBrains Mono (woff2, subconjunto latino) con sus licencias OFL
├── css/
│   ├── fuentes.css       @font-face de las fuentes locales (se carga antes que tokens.css)
│   ├── tokens.css        Colores, tipografía y logo: la única fuente de verdad visual
│   ├── layout.css        Reset, área principal, barra superior, botones y logo
│   └── componentes.css   Piezas compartidas: modales, tarjetas, tablas, pills, toast
├── js/
│   ├── utils.js          $, escHtml, toast
│   ├── estado.js         Estado compartido y datos de demostración
│   ├── cargador.js       registrarComponente() y montarComponentes()
│   ├── navegacion.js     go(pantalla), abrir/cerrar modales
│   ├── iconos.js         Catálogo de íconos SVG y paintIcons()
│   ├── datos-corrida.js  Datos de la corrida, métricas y catálogo de estados
│   ├── puente-python.js  Recibe eventos de Python (window.onPyAgentEvent)
│   └── main.js           Arranque
└── componentes/          Un componente por pantalla o modal
    ├── sidebar/          Barra lateral y estado del sandbox
    ├── inicio/           Bienvenida y recientes · modal-abrir · modal-clonar
    ├── vista-previa/     Árbol de módulos y tabla de funciones
    ├── config-pruebas/   Perfiles, comparación de costos y estimación
    ├── barra-corrida/    Barra superior de Monitor, Ejecución e Informe
    ├── monitor/          Línea de tiempo de la corrida
    ├── ejecucion/        KPIs, filtros y detalle por función
    ├── informe/          Informe final · modal-exportar
    ├── configuracion/    Configuración del sistema (solo lectura)
    └── historial/        Corridas y specs del proyecto
```

## Cómo arranca

1. `index.html` carga los CSS y luego los scripts, en un orden que **importa**: `utils` → `estado` → `cargador` → `navegacion` → `iconos` → `datos-corrida` → componentes → `puente-python` → `main`.
2. Cada componente, al cargarse, llama a `registrarComponente('carpeta/nombre', html)`.
3. `main.js` ejecuta `montarComponentes()`, que reemplaza cada marcador `data-componente` por el HTML registrado, y después las funciones `iniciar…()` de los componentes que necesitan cablear eventos tras el montaje. Termina con `go('welcome')`.

Son scripts clásicos que comparten el ámbito global (por eso los `onclick="…"` del HTML pueden llamar a las funciones). No hay `import`/`export`, ni `fetch` de HTML, ni bundler: así funciona con `file://` y con pywebview sin servidor propio.

**La ventana carga `index.html` como URL `file://`** (`desktop.py`, `FRONTEND_DIR.../index.html` con `.as_uri()`). No hay que pasar la ruta como texto ni activar `http_server`: el servidor HTTP interno de pywebview tiene una cola de 5 conexiones y, al abrir la ventana (decenas de CSS, JS y fuentes a la vez), rechaza peticiones al azar; la interfaz queda sin estilos o sin scripts de forma intermitente. `tests/app/test_desktop_arranque.py` lo vigila.

## Anatomía de un componente

```text
componentes/<carpeta>/<nombre>.js     HTML (plantilla) + registro + lógica
componentes/<carpeta>/<nombre>.css    Estilos propios (opcional)
```

El inicio de `<nombre>.js` registra el HTML:

```js
// <nombre>.js — qué hace el componente
registrarComponente('<carpeta>/<nombre>', `<section id="s-algo" class="hide">…</section>`);

function renderAlgo(){ … }
function iniciarAlgo(){ … }   // solo si necesita cablear eventos una vez montado
```

### Agregar un componente

1. Crear `componentes/<carpeta>/<nombre>.js` (y `.css` si hace falta) como arriba.
2. En `index.html`, poner el marcador donde va: `<div data-componente="<carpeta>/<nombre>"></div>`.
3. Enlazar el CSS (en `<head>`) y el script (antes de `puente-python.js`) en `index.html`.
4. Si es una pantalla: usar `id="s-<clave>"`, sumar la clave a la lista de `go()` en `navegacion.js` y llamar a su `render…` desde `go()`.
5. Si necesita cablear eventos tras montarse: crear `iniciar<Nombre>()` y llamarlo desde `main.js`.
6. Ejecutar `python test.py`: `tests/frontend/test_estructura.py` avisa si falta el marcador, el registro, el enlace o un archivo.

Cuidado con el HTML dentro de la plantilla JS: hay que escapar `` ` `` y `${` si aparecen.

## Colores, tipografía y logo

Todo lo visual se cambia en **`css/tokens.css`**:

| Grupo | Variables | Uso |
|---|---|---|
| Estructura | `--bg`, `--side`, `--panel`, `--panel2`, `--inset`, `--line`, `--line2`, `--txt`, `--mut`, `--dim` | Fondos, bordes y textos |
| Semánticos de estado | `--blue`, `--purple`, `--green`, `--red`, `--amber`, cada una con `-t` (texto) y `-s` (fondo suave) | Estados, pills, acentos |
| Paleta | `--<familia>-<tono>` (`--emerald-400`, `--rose-500`, `--slate-950`…), más variantes `-aNN`, `-b` y `-c` (ver abajo) | Todos los colores que usan los componentes |
| Marca | `--marca-1`, `--marca-2`, `--marca-3`, `--marca-gradiente`, `--fondo-marca` | Colores tomados del logo |
| Tipografía | `--fuente-ui`, `--fuente-mono` (`--sans` y `--mono` son alias) | Texto de interfaz y de código |
| Logo | `--logo-icono`, `--logo-completo` | Rutas a los SVG de `assets/logo/` |

**Cambiar el logo:** reemplazar los SVG de `assets/logo/` (mismos nombres) o cambiar las rutas en `tokens.css`. La barra lateral lo usa con `.logo`, que **debe seguir en `css/layout.css`**: la ruta de `--logo-icono` es relativa a `css/`, y si esa regla se mueve a la carpeta de un componente la imagen deja de resolverse. En `qagent-logo.svg` el texto usa la fuente Poppins, que no se incluye (el SVG se dibuja como imagen y no hereda las fuentes de la página): sin ella cae a Segoe UI.

**Cambiar la tipografía:** las fuentes van incluidas en el proyecto (`assets/fuentes/`, unos 140 KB, licencia OFL): la interfaz no depende de internet. Para cambiar de fuente, reemplazar los `woff2`, actualizar los `@font-face` de `css/fuentes.css` y el nombre de la familia en `--fuente-ui` / `--fuente-mono` de `tokens.css`. Hoy se incluyen Inter (400, 500, 600, 700) y JetBrains Mono (400, 600), con el subconjunto latino, que cubre el español; otro alfabeto requeriría añadir su subconjunto. Un peso que no esté incluido (el 800, por ejemplo) se resuelve al más cercano.

### Reglas para los colores

Ningún CSS, JS ni HTML de la interfaz contiene colores literales (`#34d399`, `rgba(…)`): todos son `var(--token)`, y los valores viven solo en `css/tokens.css`. Cambiar un token cambia ese color en toda la aplicación. `tests/frontend/` lo exige: falla si aparece un color suelto o si se usa un `var(--x)` que no está definido.

- **Nombres.** `--<familia>-<tono>` sigue la escala de Tailwind (`--emerald-400`). `-aNN` es el mismo color con NN % de opacidad (`--rose-950-a60`). `-b` es el borde de un estado (`--green-b`, `--red-b`, `--amber-b`, `--blue-b`, `--purple-b`, pareja de `-t` y `-s`). `-c` marca un valor propio del proyecto que no pertenece a la paleta de Tailwind.
- **Color nuevo.** Antes de crearlo, buscar en `tokens.css` uno casi igual y reutilizarlo: la paleta ya se unificó y dos colores a menos de ΔE 3 (diferencia imperceptible sobre los fondos de la interfaz) no se distinguen. Si hace falta uno nuevo, declararlo en `tokens.css` y usar `var(--nombre)`; no escribir hexadecimales en los componentes.
- **No concatenar texto a un color.** Un truco como `` `${color}33` `` (opacidad en hexadecimal) deja de ser válido con `var(--…)`. Usar un token con opacidad: por eso cada estado del catálogo `ST` (`js/datos-corrida.js`) trae su `halo` (`--rose-500-a20`).
- **Atributos SVG.** `stroke="var(--x)"` y `fill="var(--x)"` funcionan en el navegador de pywebview, y los íconos (`I(nombre, color)`) reciben tokens como cualquier otro color.
- **Excepción.** Los SVG de `assets/logo/` son archivos independientes y conservan sus propios colores; si cambia la marca hay que actualizarlos junto con `--marca-*`.

## Nombres técnicos que no se renombran

Aunque el producto se llama QAgent, estos identificadores son del backend y se mantienen: la imagen Docker `pyagent-sandbox:base`, la carpeta `.pyagent/` (y `~/.pyagent/`), el módulo `pyagent` y la función `window.onPyAgentEvent`, que invoca `desktop.py`.

## Datos reales y datos simulados

La interfaz tiene un **modo demostración**: sin pywebview (abriendo `index.html` en el navegador) todo funciona con datos de ejemplo. En la aplicación de escritorio, lo que se muestra sale del backend o no se muestra:

| Pantalla | Con pywebview (aplicación real) | Sin pywebview (demostración) |
|---|---|---|
| Inicio | Proyectos recientes reales (`~/.pyagent/recientes.json`) | Lista simulada de 11 proyectos |
| Vista previa | Nombre, rama (solo si hay Git), módulos, funciones y consistencias del análisis AST. Si el análisis falla, aviso de error y lista vacía | Proyecto de ejemplo `ecommerce-core` |
| Entorno | Verificación real de EN-06: `config.toml`, claves de `.env`, Docker y Git (con la IA simulada no se piden las claves y Docker es opcional). Si falla, bloquea «Continuar» en la configuración de pruebas y el arranque de la corrida | «Modo demostración» |
| Configuración de pruebas | El perfil Regresión solo está disponible si el proyecto ya tuvo una corrida | Disponible |
| Controles «reiniciar demo» y «completar corrida» | Ocultos | Visibles |
| Monitor, Ejecución, Informe, Historial y Configuración del sistema | **Datos simulados** (ver abajo) | Datos simulados |

**Pendiente:** Monitor, Ejecución, Informe, Historial y Configuración del sistema todavía se alimentan de datos simulados (`js/datos-corrida.js` y los `EVENTS` del monitor, la corrida «#8841-B», el historial de ejemplo, los precios de ejemplo de `AGENTS_CFG`), incluso en la aplicación real, porque el orquestador aún no está conectado a la interfaz: `start_run` solo comprueba Docker y emite un aviso. Conectarlos exige enviar eventos reales desde Python (`emit_event`) y leer las corridas guardadas en `.pyagent/runs/`. `tests/frontend/` impide que los datos de ejemplo vuelvan a colarse en las pantallas del flujo real.
