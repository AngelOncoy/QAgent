# Correcciones Implementadas â€” Issue #92

Fecha: 2026-10-17
Rama: `fix/issue-92-correcciones-generales`
Commit base: `0172b804f2631180327614ab1dbb3e9608c77ffd`

---

## 1. Contexto de RecuperaciÃ³n

La implementaciÃ³n de la Fase 3 de la Issue #92 fue iniciada por Codex y recuperada por OpenCode tras una interrupciÃ³n. Durante la auditorÃ­a inicial de recuperaciÃ³n se constatÃ³ que Codex habÃ­a preparado la estructura de las correcciones en el cÃ³digo fuente frontend y habÃ­a redactado una suite de regresiÃ³n (`tests/frontend/test_issue_92_fix_general.py`).

OpenCode auditÃ³ minuciosamente el estado existente, confirmÃ³ la integridad del diff, validÃ³ que ninguna correcciÃ³n rompe funcionalidades previas (#63, #65, #66) y ejecutÃ³ las suites completas y las pruebas visuales multirresoluciÃ³n con Playwright.

---

## 2. Detalle por Defecto

### Q92-001 â€” Desbordamiento horizontal de Vista previa

- **Severidad:** MEDIA.
- **Causa raÃ­z:** `.grid2` mantenÃ­a 2 columnas fijas (`300px 1fr`) con breakpoint en `max-width: 960px`. En viewports de 1024Ã—700, descontando la barra lateral (236 px), el contenedor Ãºtil mide 788 px, lo que forzaba a la tabla de endpoints (`min-width: 860px`) a empujar `.grid2` y desplazar el contenedor `.scroll` hacia `scrollLeft = 414px`, ocultando el Ã¡rbol del proyecto.
- **SoluciÃ³n implementada:**
  1. En `src/qagent/frontend/componentes/vista-previa/vista-previa.css`:
     - Se actualizÃ³ `.grid2` con `grid-template-columns: minmax(260px, 300px) minmax(0, 1fr)` y `min-width: 0`.
     - Se fijÃ³ `min-width: 0` en hijos `.card`, `.obj-vista` y `.objs-head`.
     - Se asignÃ³ scroll horizontal interno contenido a `.grid2 .table-scroll` (`max-width: 100%; min-width: 0; overflow-x: auto; overscroll-behavior-inline: contain`).
     - Se subiÃ³ el breakpoint responsivo a `@media(max-width:1180px){.grid2{grid-template-columns:1fr}}`.
- **Efecto verificado:** En 1024Ã—700, la cuadrÃ­cula se apila verticalmente de forma limpia; la tabla contiene su propio scroll horizontal interno (`scrollWidth: 860px, clientWidth: 738px, overflowX: auto`), y el contenedor de la pantalla `#s-preview .scroll` permanece con `scrollLeft: 0, scrollWidth: 788px, clientWidth: 788px` sin desbordamiento. En resoluciones superiores (1280Ã—720, 1366Ã—768, 1440Ã—900, 1920Ã—1080), la cuadrÃ­cula mantiene dos columnas sin desbordar el contenedor exterior.

### Q92-002 â€” Undefined en columna Decisiones

- **Severidad:** MEDIA.
- **Causa raÃ­z:** En la vista de demostraciÃ³n (`estado.js`), los objetos de endpoint no declaraban la propiedad `ramas`. En `vista-previa.js`, la plantilla interpolaba directamente `${e.br}`, que resultaba en `undefined` cuando la propiedad no existÃ­a o no estaba tipada como nÃºmero entero.
- **SoluciÃ³n implementada:**
  1. En `src/qagent/frontend/componentes/vista-previa/vista-previa.js`:
     - Se crearon las funciones puras `normalizarDecisiones(valor)` y `textoDecisiones(valor)`.
     - `normalizarDecisiones`: valida estrictamente que el valor sea un nÃºmero entero finito no negativo (`valor >= 0`). Cualquier otro valor (incluyendo `undefined`, `null`, `NaN`) devuelve `null` sin inventar mÃ©tricas ni asumir ceros falsos.
     - `textoDecisiones`: traduce `null` al sÃ­mbolo de dato ausente `â€”` (em-dash) y valores numÃ©ricos a cadena de texto.
     - En `cargarDatosVistaPrevia`: se normalizan las ramas antes de asignarlas a `e.br`.
     - En `renderEndpoints`: se renderiza `<td class="mono">${decisiones}</td>` usando `textoDecisiones(e.br)`.
- **Efecto verificado:** Ninguna fila muestra `undefined`, `null` ni `NaN`. En los endpoints demo se visualiza `â€”` de forma elegante y consistente; cuando un anÃ¡lisis AST real entrega ramas, se muestra el entero correspondiente (validado por `test_analizador_real_entrega_decisiones_numericas`).

### Q92-003 â€” Control Â«Seleccionar todosÂ» desbordado del encabezado del Ã¡rbol

- **Severidad:** BAJA.
- **Causa raÃ­z:** En el encabezado del panel izquierdo (`.card h4`), el tÃ­tulo Â«Ãrbol del proyectoÂ», el contador de mÃ³dulos y el control Â«Seleccionar todosÂ» competÃ­an en una sola lÃ­nea flex sin reglas de envoltura (`flex-wrap`). En anchos de panel de 300 px (como en 1440Ã—900), el contenido requerÃ­a 360 px, desbordando el contenedor.
- **SoluciÃ³n implementada:**
  1. En `src/qagent/frontend/componentes/vista-previa/vista-previa.css`:
     - `.tree-head`: se configurÃ³ con `display: flex; flex-wrap: wrap; justify-content: space-between`.
     - `.tree-head-title`: contenedor flex con `min-width: 0` y `flex: 1 1 auto; flex-wrap: wrap`.
     - `.select-all`: `flex: 0 0 auto; white-space: nowrap; margin-left: 0`.
  2. En `src/qagent/frontend/componentes/vista-previa/vista-previa.js`:
     - Se actualizÃ³ el marcado HTML del componente para agrupar el tÃ­tulo y contador bajo `.tree-head-title` y estructurar `.tree-head`.
- **Efecto verificado:** En 1440Ã—900, el encabezado mide `scrollWidth: 298px, clientWidth: 298px` (0 px de desbordamiento), envolviendo ordenadamente el control debajo del tÃ­tulo si el espacio lo requiere, manteniendo la casilla accesible, legible y funcional.

### Q92-004 â€” Error HTTP 404 por recurso favicon.ico ausente

- **Severidad:** BAJA.
- **Causa raÃ­z:** `index.html` no tenÃ­a declarado un elemento `<link rel="icon">`. Al abrir la aplicaciÃ³n en el navegador o entornos basados en webview, el motor realizaba una peticiÃ³n predeterminada a `/favicon.ico`, resultando en un error de red HTTP 404 y advertencias en la consola.
- **SoluciÃ³n implementada:**
  1. En `src/qagent/frontend/index.html`:
     - Se aÃ±adiÃ³ `<link rel="icon" type="image/svg+xml" href="assets/logo/qagent-icono.svg">`.
     - Se reutilizÃ³ el icono SVG oficial ya empaquetado en el repositorio (`src/qagent/frontend/assets/logo/qagent-icono.svg`), sin aÃ±adir dependencias ni recursos ajenos.
- **Efecto verificado:** La peticiÃ³n al favicon resuelve con HTTP 200 OK; se eliminÃ³ el error 404 de la consola en todas las resoluciones evaluadas.

---

## 3. Matriz de Estado Final de los Errores

| ID | Defecto | Estado Inicial AuditorÃ­a | Estado Final | AcciÃ³n Realizada por OpenCode |
|---|---|---|---|---|
| **Q92-001** | Desbordamiento horizontal Vista previa | Implementado sin validar | **Validado y corregido** | Verificadas medidas DOM (sl=0, sw<=cw) en 5 viewports con Playwright. |
| **Q92-002** | Undefined en columna Decisiones | Implementado sin validar | **Validado y corregido** | Verificadas celdas y ejecuciÃ³n del harness Node; ausencia absoluta de `undefined`. |
| **Q92-003** | Seleccionar todos desbordado | Implementado sin validar | **Validado y corregido** | Verificadas medidas DOM (sw <= cw) en panel de 300 px y vista apilada. |
| **Q92-004** | Favicon 404 | Implementado sin validar | **Validado y corregido** | Verificada carga SVG con HTTP 200 y ausencia de 404 en consola y red. |

---

## 4. Archivos Modificados

| Archivo | Tipo de Cambio | JustificaciÃ³n |
|---|---|---|
| `src/qagent/frontend/componentes/vista-previa/vista-previa.css` | Modificado | Breakpoint 1180px, scroll interno `.table-scroll`, wrap en `.tree-head`. |
| `src/qagent/frontend/componentes/vista-previa/vista-previa.js` | Modificado | NormalizaciÃ³n y renderizado de decisiones, estructura `.tree-head`. |
| `src/qagent/frontend/index.html` | Modificado | DeclaraciÃ³n de favicon SVG oficial. |
| `tests/frontend/test_issue74_endpoints_profundizar.py` | Modificado | ActualizaciÃ³n de aserciones para reflejar `normalizarDecisiones` y `${decisiones}`. |
| `tests/frontend/test_issue_92_fix_general.py` | Archivo Nuevo | 8 pruebas unitarias y de regresiÃ³n automatizadas para los 4 defectos. |
