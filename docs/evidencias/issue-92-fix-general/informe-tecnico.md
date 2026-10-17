# Informe TÃ©cnico â€” CorrecciÃ³n General de Errores, Estabilidad y Funcionamiento de QAgent (Issue #92)

Fecha: 2026-10-17
Rama: `fix/issue-92-correcciones-generales`
Commit base: `0172b804f2631180327614ab1dbb3e9608c77ffd`
AutorÃ­a: OpenCode (continuaciÃ³n y cierre de la Fase 3 iniciada por Codex)

---

## 1. Resumen Ejecutivo

Este informe consolida los resultados de la auditorÃ­a, recuperaciÃ³n, implementaciÃ³n y validaciÃ³n de la **Issue #92**. La tarea se centrÃ³ en subsanar cuatro defectos confirmados en la interfaz de usuario de QAgent que afectaban la experiencia de visualizaciÃ³n, la legibilidad de datos y la compatibilidad con diferentes resoluciones de pantalla (desde 1024Ã—700 hasta 1920Ã—1080).

Tras auditar el estado dejado por Codex, se verificaron e integraron las correcciones necesarias sin descartar ningÃºn avance vÃ¡lido. Se incorporaron 8 pruebas automatizadas de regresiÃ³n (`tests/frontend/test_issue_92_fix_general.py`), se ejecutÃ³ la suite frontend (187 passed), la suite rÃ¡pida (1322 passed, 25 deselected) y la suite oficial completa (1347 passed, ruff check y format limpios). Adicionalmente, se ejecutÃ³ una validaciÃ³n visual cuantitativa mediante Playwright comprobando mÃ©tricas DOM (ancho de cliente vs. ancho de scroll) y generando capturas reales para 5 resoluciones. Los cuatro defectos quedan **100% resueltos y verificados**.

---

## 2. IntroducciÃ³n

QAgent es un sistema multiagente en Python (diseÃ±ado bajo metodologÃ­a GAIA) para la generaciÃ³n y validaciÃ³n de pruebas pytest orientadas a funciones Python y endpoints FastAPI. Su interfaz de escritorio se ejecuta mediante pywebview consumiendo activos HTML/CSS/JavaScript vanilla sin empaquetadores externos.

Durante una auditorÃ­a integral del frontend en vista de demostraciÃ³n y con proyectos reales, se detectaron desalineaciones visuales en ventanas reducidas, valores sin formatear en tablas de endpoints y peticiones de recursos 404 al navegador. La Issue #92 se abriÃ³ con el objetivo de corregir estos defectos manteniendo estricta compatibilidad con las issues previas ya integradas (#63, #65, #66).

---

## 3. DescripciÃ³n de los Errores

| CÃ³digo | Defecto | Severidad | Impacto |
|---|---|---|---|
| **Q92-001** | Desbordamiento horizontal en Vista previa al mostrar Endpoints | MEDIA | En pantallas 1024Ã—700, el contenedor principal experimentaba un desplazamiento horizontal (`scrollLeft=414px`), ocultando el Ã¡rbol de navegaciÃ³n detrÃ¡s de la barra lateral. |
| **Q92-002** | Texto literal `undefined` en columna Decisiones | MEDIA | En la tabla de endpoints de demostraciÃ³n, la columna Decisiones renderizaba el string `undefined` en lugar de una representaciÃ³n formal de dato ausente o numÃ©rico. |
| **Q92-003** | Control Â«Seleccionar todosÂ» desbordado del encabezado del Ã¡rbol | BAJA | En viewports estÃ¡ndar (1440Ã—900) con panel de 300 px, el tÃ­tulo y el checkbox competÃ­an en un flex unidimensional, provocando que el control se saliera del panel. |
| **Q92-004** | PeticiÃ³n fallida HTTP 404 por `/favicon.ico` | BAJA | Al cargar la interfaz web, el navegador emitÃ­a una peticiÃ³n a `/favicon.ico` que resultaba en un error 404 y una advertencia en la consola. |

---

## 4. Objetivos

1. **Garantizar la adaptabilidad responsiva:** Permitir que la Vista previa funcione sin desbordamiento global en pantallas desde 1024Ã—700 (e incluso el mÃ­nimo de pywebview 960Ã—600), asegurando scroll horizontal exclusivo para las tablas anchas.
2. **Normalizar la presentaciÃ³n de datos:** Tratar las ramas condicionales como enteros estrictos o representar datos no disponibles mediante guion largo (`â€”`), eliminando artefactos JavaScript (`undefined`, `null`, `NaN`).
3. **Optimizar la disposiciÃ³n visual del Ã¡rbol:** Permitir envoltura (`flex-wrap`) en el encabezado del panel de mÃ³dulos sin romper la alineaciÃ³n ni recortar controles.
4. **Eliminar errores de consola:** Declarar el favicon oficial en formato SVG para que cualquier navegador o webview resuelva el recurso con HTTP 200.
5. **Cero regresiones:** Mantener intactas las funcionalidades de selecciÃ³n AST (#63), tablas plegables de funciones con semÃ¡foro de Calidad (#65) y tablas de endpoints FastAPI (#66).

---

## 5. Alcance

- **Dentro de alcance:**
  - Archivos frontend CSS, JS y HTML relacionados con la Vista previa y cabecera de la aplicaciÃ³n (`src/qagent/frontend/componentes/vista-previa/`, `src/qagent/frontend/index.html`).
  - Pruebas automatizadas de frontend y regresiÃ³n en `tests/frontend/`.
  - DocumentaciÃ³n de auditorÃ­a, evidencias visuales y bitÃ¡cora en `docs/evidencias/issue-92-fix-general/`.
- **Fuera de alcance:**
  - Modificaciones al analizador AST o agentes (`src/qagent/analysis/`, `src/qagent/agents/`).
  - FusiÃ³n de la Issue #67 (pendiente en rama separada).
  - ModificaciÃ³n de contratos backend o configuraciÃ³n del equipo.

---

## 6. Arquitectura Revisada

La arquitectura de la interfaz se rige por el principio de **cero dependencias externas y cero bundlers** (ADR-003).
- Los componentes se registran mediante cadenas de plantilla (`registrarComponente`) y se montan sincrÃ³nicamente.
- El diseÃ±o visual se basa en variables semÃ¡nticas (`css/tokens.css`).
- Los datos fluyen desde `estado.js` (en modo demo) o mediante `DesktopAPI` (en ejecuciÃ³n pywebview) hacia funciones puras de renderizado (`renderTree`, `renderEndpoints`, `renderFns`).
- La correcciÃ³n arquitectÃ³nica clave residiÃ³ en desacoplar el ancho del contenedor de la cuadrÃ­cula (`.grid2`) del ancho total del viewport, obligando a las tablas con gran densidad de informaciÃ³n (`.table-scroll`) a contener su propio desbordamiento mediante `overflow-x: auto; min-width: 0`.

---

## 7. DiagnÃ³stico y Causa RaÃ­z

### Q92-001 â€” Desbordamiento horizontal
- **DiagnÃ³stico:** `.grid2` tenÃ­a una regla fija `grid-template-columns: 300px 1fr` con breakpoint en `max-width: 960px`. En una ventana de 1024Ã—700, el ancho del viewport es 1024 px, pero al restar la barra lateral fija (236 px), el ancho disponible para el Ã¡rea principal es de solo 788 px. Dado que 1024 > 960, la cuadrÃ­cula conservaba dos columnas. Al tener la tabla de endpoints un `min-width: 860px`, la segunda columna requerÃ­a mÃ¡s espacio del disponible, obligando al ancestro `.scroll` a expandirse hasta `scrollWidth: 1202px` y desplazarse a `scrollLeft: 414px`.
- **Causa raÃ­z:** Punto de quiebre responsivo calculado contra el viewport completo en lugar de considerar el ancho neto del panel de contenido, sumado a la falta de `min-width: 0` en las celdas de la cuadrÃ­cula.

### Q92-002 â€” Undefined en Decisiones
- **DiagnÃ³stico:** Los objetos de endpoint definidos en `frontend/js/estado.js` no declaraban `ramas` ni `br`. En `vista-previa.js`, la plantilla interpolaba `${e.br}`.
- **Causa raÃ­z:** Ausencia de una funciÃ³n de sanitizaciÃ³n y formateo para valores condicionales ausentes en el lÃ­mite de presentaciÃ³n.

### Q92-003 â€” Seleccionar todos desbordado
- **DiagnÃ³stico:** `.card h4` utilizaba `display: flex` sin `flex-wrap`. El tÃ­tulo Â«Ãrbol del proyectoÂ» y el checkbox Â«Seleccionar todosÂ» ocupaban conjuntamente mÃ¡s de 300 px.
- **Causa raÃ­z:** Falta de contenedor flex secundario y directiva `flex-wrap: wrap` en el encabezado del panel izquierdo.

### Q92-004 â€” Favicon 404
- **DiagnÃ³stico:** Ausencia de `<link rel="icon">` en `index.html`.
- **Causa raÃ­z:** OmisiÃ³n de la referencia al recurso grÃ¡fico en la plantilla HTML base.

---

## 8. Correcciones Realizadas

1. **`src/qagent/frontend/componentes/vista-previa/vista-previa.css`:**
   - Se estableciÃ³ `.grid2 { grid-template-columns: minmax(260px, 300px) minmax(0, 1fr); min-width: 0; }`.
   - Se aplicÃ³ `min-width: 0` en hijos `.card`, `.obj-vista`, `.objs-head`.
   - Se confinÃ³ el scroll a `.grid2 .table-scroll { max-width: 100%; min-width: 0; overflow-x: auto; overscroll-behavior-inline: contain; }`.
   - Se elevÃ³ el breakpoint de apilamiento a `@media(max-width:1180px){.grid2{grid-template-columns:1fr}}`.
   - Se diseÃ±Ã³ `.tree-head` con `flex-wrap: wrap; justify-content: space-between` y `.select-all` con `white-space: nowrap`.
2. **`src/qagent/frontend/componentes/vista-previa/vista-previa.js`:**
   - Se agregaron las funciones `normalizarDecisiones(valor)` y `textoDecisiones(valor)`.
   - Se actualizÃ³ el marcado del Ã¡rbol para utilizar `.tree-head` y `.tree-head-title`.
   - Se modificÃ³ `renderEndpoints()` para emplear `${decisiones}` en lugar de `${e.br}`.
3. **`src/qagent/frontend/index.html`:**
   - Se agregÃ³ `<link rel="icon" type="image/svg+xml" href="assets/logo/qagent-icono.svg">`.

---

## 9. Compatibilidad con Otras Issues

- **Issue #63 (SelecciÃ³n AST):** Los filtros de mÃ³dulos, el Ã¡rbol de archivos y las casillas de selecciÃ³n conservan su funcionalidad y sincronizaciÃ³n con el estado global.
- **Issue #65 (Funciones, Calidad y Plegado):** La agrupaciÃ³n por archivo, el plegado interactivo de filas y el semÃ¡foro de Calidad (`Lista`, `Mejorable`, `Incierto`) permanecen completamente intactos.
- **Issue #66 (Endpoints FastAPI):** La alternancia Funciones/Endpoints mediante `cambiarVistaObjetivos`, la visualizaciÃ³n de dependencias simuladas, cÃ³digos de error y la marca de endpoints no elegibles operan segÃºn la especificaciÃ³n original.
- **Issue #67:** No fue mezclada ni incorporada; no existe conflicto con dicha rama.

---

## 10. Pruebas y ValidaciÃ³n

### 10.1. Pruebas Automatizadas
- **`tests/frontend/test_issue_92_fix_general.py`:** 8 pruebas de regresiÃ³n cubriendo valores numÃ©ricos vÃ¡lidos, cero explÃ­cito, valores nulos/indefinidos, compatibilidad con AST real, estructura flex del encabezado y validaciÃ³n XML del SVG del favicon.
- **`tests/frontend/test_issue74_endpoints_profundizar.py`:** Pruebas adaptadas a la nueva normalizaciÃ³n de decisiones.
- **Suite Frontend (`pytest tests/frontend -q`):** 187 pasadas (100% Ã©xito).
- **Suite RÃ¡pida (`python test.py --rapido`):** 1322 pasadas, 25 deselected.
- **Suite Completa Oficial (`python test.py`):** 1347 pasadas, 0 fallos.
- **Calidad de CÃ³digo:** Ruff check (0 advertencias), Ruff format (202 archivos limpios), `node --check` (sintaxis JS vÃ¡lida en todos los ficheros).

### 10.2. ValidaciÃ³n Visual Cuantitativa (Playwright)
Se ejecutaron pruebas en 5 viewports obteniendo mÃ©tricas directas del DOM:

| ResoluciÃ³n | Estado Global | Ancho Contenedor `.scroll` | ScrollLeft Contenedor | Ancho Tabla Interna |
|---|---|---|---|---|
| **1024Ã—700** | PASS | clientWidth: 788px, scrollWidth: 788px | **0 px** | scrollWidth: 860px (scroll interno) |
| **1280Ã—720** | PASS | clientWidth: 1044px, scrollWidth: 1044px | **0 px** | scrollWidth: 860px (scroll interno) |
| **1366Ã—768** | PASS | clientWidth: 1130px, scrollWidth: 1130px | **0 px** | scrollWidth: 860px (scroll interno) |
| **1440Ã—900** | PASS | clientWidth: 1204px, scrollWidth: 1204px | **0 px** | scrollWidth: 860px (scroll interno) |
| **1920Ã—1080** | PASS | clientWidth: 1684px, scrollWidth: 1684px | **0 px** | scrollWidth: 1318px (cabe completa) |

---

## 11. Evidencias Generadas

Las evidencias fÃ­sicas se conservan en `docs/evidencias/issue-92-fix-general/`:
- **DocumentaciÃ³n:** `auditoria-inicial.md`, `matriz-errores.md`, `pruebas-base.md`, `correcciones-implementadas.md`, `bitacora-pruebas.md`, `informe-tecnico.md`.
- **Datos JSON:** `validacion-visual-resultados.json`.
- **Capturas "Antes":** `img/antes/preview-desktop.png`, `img/antes/endpoints-desktop.png`, `img/antes/endpoints-small.png`, `img/antes/execution-desktop.png`, `img/antes/report-desktop.png`, `img/antes/inicio-desktop.png`.
- **Capturas "DespuÃ©s":** 11 capturas en `img/despues/` documentando Funciones y Endpoints en las 5 resoluciones requeridas, incluyendo `vista-1024x700.png`.
- **Integridad:** `manifiesto-sha256.txt` con el hash SHA-256 de cada archivo de evidencia.

---

## 12. Limitaciones Ambientales

1. **Docker Desktop:** Durante la ejecuciÃ³n, el servicio de Docker Desktop no estuvo iniciado, por lo que 23 pruebas de integraciÃ³n con contenedores reales fueron omitidas por diseÃ±o del sistema de pruebas.
2. **pywebview nativo:** El entorno headless de automatizaciÃ³n ejecutÃ³ las pruebas visuales en motor Chromium; se recomienda una comprobaciÃ³n manual de inicio (`qagent`) en Windows antes del empaquetado final.

---

## 13. Conclusiones y Recomendaciones

La Issue #92 ha sido resuelta en su totalidad. El trabajo incompleto de Codex fue recuperado, complementado con validaciÃ³n rigurosa y respaldado por mÃ©tricas DOM empÃ­ricas y pruebas automatizadas. El cÃ³digo se encuentra formateado, limpio y sin errores de linting.

Se recomienda proceder con el commit y la apertura del Pull Request hacia `develop` siguiendo la convenciÃ³n:
`fix(EN-03): resolucion de defectos visuales y de datos en vista previa (#92)`.
