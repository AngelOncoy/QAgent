# Matriz de errores — issue #92

Solo se registran defectos reproducidos. Las limitaciones ambientales se
separan al final y no se cuentan como errores.

## Resumen

| Severidad | Cantidad |
|---|---:|
| Crítico | 0 |
| Alto | 0 |
| Medio | 2 |
| Bajo | 2 |

## Q92-001 — desplazamiento horizontal de Vista previa

- **Módulo:** frontend / Vista previa.
- **Severidad:** MEDIO.
- **Error:** en una ventana de 1024×700, al abrir Endpoints el contenedor de la
  pantalla se desplaza horizontalmente hasta `scrollLeft=414`. El inicio de la
  cabecera, el árbol y las primeras columnas quedan ocultos detrás de la barra
  lateral.
- **Reproducción:** servir `src/qagent/frontend/`, abrir `ecommerce-core` con
  viewport 1024×700 y pulsar `Endpoints (7)`.
- **Esperado:** árbol, cabecera y tabla permanecen accesibles; las tablas pueden
  tener scroll horizontal propio sin desplazar toda la pantalla.
- **Real:** el ancestro `.scroll` mide 788 px de cliente, 1202 px de contenido y
  termina con desplazamiento horizontal de 414 px.
- **Causa comprobada:** `.grid2` conserva dos columnas porque el breakpoint usa
  el ancho total de viewport (`max-width:960px`), aunque la barra lateral deja
  solo 788 px al contenido. La tabla tiene además `min-width:860px`.
- **Archivo:** `src/qagent/frontend/componentes/vista-previa/vista-previa.css` y
  reglas compartidas de `src/qagent/frontend/css/componentes.css`.
- **Corrección recomendada:** activar antes el layout de una columna o usar una
  condición basada en el ancho útil; mantener el overflow en `.table-scroll` y
  evitar overflow horizontal de `.page`/`.grid2`.
- **Prueba necesaria:** prueba renderizada a 1400×900, 1024×700 y al mínimo
  pywebview 960×600; comprobar que el scroll exterior permanece en cero tras
  cambiar de pestaña.
- **Evidencia:** captura real de navegador
  `%TEMP%/qagent-issue92/endpoints-small.png` y métricas DOM de Playwright.

## Q92-002 — “undefined” en Decisiones de endpoints demo

- **Módulo:** frontend / datos de demostración y Vista previa.
- **Severidad:** MEDIO.
- **Error:** todos los endpoints de demostración muestran el texto `undefined`
  en la columna Decisiones.
- **Reproducción:** abrir `ecommerce-core`, seleccionar Endpoints y observar la
  columna Decisiones.
- **Esperado:** un entero, normalmente `0` si no hay información de ramas.
- **Real:** se renderiza `undefined`.
- **Causa comprobada:** los endpoints declarados en `frontend/js/estado.js` no
  incluyen `br`; el render usa `${e.br}` sin valor por defecto. El camino de
  datos reales sí normaliza `e.ramas` a `br` con `|| 0`.
- **Archivos:** `src/qagent/frontend/js/estado.js` y
  `src/qagent/frontend/componentes/vista-previa/vista-previa.js`.
- **Corrección recomendada:** normalizar también los endpoints demo o renderizar
  `e.br ?? 0`; preferiblemente aplicar ambas defensas en el límite de datos.
- **Prueba necesaria:** ampliar el harness Node/frontend para afirmar que la
  columna contiene un número y nunca `undefined`.
- **Evidencia:** captura `%TEMP%/qagent-issue92/endpoints-desktop.png` y texto DOM.

## Q92-003 — encabezado del árbol desbordado

- **Módulo:** frontend / Vista previa.
- **Severidad:** BAJO.
- **Error:** a 1440×900, el encabezado del panel de 300 px no contiene
  completamente título, contador y `Seleccionar todos`.
- **Reproducción:** abrir la Vista previa en el tamaño predeterminado aproximado.
- **Esperado:** todos los controles del encabezado quedan visibles o se
  distribuyen en más de una línea.
- **Real:** el `h4` tiene 298 px de cliente y 360 px de contenido; parte del
  control queda recortada.
- **Causa comprobada:** el panel izquierdo tiene 300 px fijos, mientras `.card
  h4` es flex y `.select-all` intenta ocupar el extremo derecho sin una regla de
  ajuste suficiente.
- **Archivos:** `src/qagent/frontend/componentes/vista-previa/vista-previa.css`
  y `src/qagent/frontend/css/componentes.css`.
- **Corrección recomendada:** permitir wrap explícito, separar el control en una
  segunda fila o aumentar el ancho de la columna sin perjudicar la tabla.
- **Prueba necesaria:** aserción renderizada `scrollWidth <= clientWidth` para
  el encabezado en los tamaños admitidos.
- **Evidencia:** métricas DOM y captura `%TEMP%/qagent-issue92/preview-desktop.png`.

## Q92-004 — recurso favicon ausente

- **Módulo:** distribución del frontend.
- **Severidad:** BAJO.
- **Error:** cada carga en navegador registra un error de consola por
  `GET /favicon.ico` con HTTP 404.
- **Reproducción:** servir `src/qagent/frontend/` y abrir `/`.
- **Esperado:** sin recursos fallidos ni errores de consola.
- **Real:** el servidor registra 404 y Edge emite `Failed to load resource`.
- **Causa comprobada:** `index.html` no declara favicon y no existe
  `frontend/favicon.ico`; sí existe el logo SVG y el icono de empaquetado.
- **Archivo:** `src/qagent/frontend/index.html` y assets de frontend.
- **Corrección recomendada:** declarar como favicon un asset incluido en el
  paquete, idealmente el SVG existente, y añadir prueba estructural del enlace.
- **Prueba necesaria:** cargar la interfaz y afirmar que no hay respuestas 4xx.
- **Evidencia:** consola de Playwright y log HTTP.

## Limitaciones y sospechas no clasificadas como defectos

- **Docker:** 23 pruebas fueron omitidas porque Docker Desktop no está iniciado.
- **pywebview:** no se controló una ventana real; la validación visual se hizo en
  Microsoft Edge sobre los mismos assets estáticos.
- **Issue #67:** su rama permanece pendiente y solapa archivos actuales; es un
  riesgo de integración, no un defecto de esta base.
- No se observaron overlays, excepciones JavaScript ni errores de consola aparte
  del favicon ausente.
