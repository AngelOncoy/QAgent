# Bitácora de pruebas · Issue #66 (selector Funciones/Endpoints)

Fecha: 17 de octubre de 2026. Entorno: Windows, Python 3.14, Node 22+, Microsoft Edge.
Rama: `feat/issue-66-selector-funciones-endpoints` (base `origin/develop` = `756eafe`).

## 1. Pruebas automatizadas ejecutadas

| Comando | Resultado real |
|---|---|
| `python -m pytest tests/frontend/test_issue_66_selector_objetivos.py -v` | **33 passed** en 1.49 s |
| `python -m pytest tests/frontend -q` | **161 passed** en 1.11 s |
| `python test.py --rapido` | **1123 passed, 19 deselected** en ~33 s |
| `python test.py` (completo) | Lint **OK**; Formato **OK**; pytest **1142 passed** en 126.05 s |
| `node --check src/qagent/frontend/componentes/vista-previa/vista-previa.js` | **OK** (sin errores de sintaxis) |
| `python -m ruff check .` | **All checks passed!** |
| `python -m ruff format --check .` | **191 files already formatted** |
| `git diff --check` | **OK** (sin espacios en blanco problemáticos) |

Salidas completas guardadas en esta carpeta: `salida-pytest-issue66.txt`,
`salida-pytest-frontend.txt`, `salida-test-rapido.txt`, `salida-node-endpoints.txt`,
`salida-regresiones-frontend.txt`.

Regresiones específicas verificadas en un solo comando (53 pruebas):

```
python -m pytest tests/frontend/test_issue_65_vista_previa.py \
  tests/frontend/test_hu28_endpoints.py tests/frontend/test_fase2_seleccion_clonado.py \
  tests/frontend/test_issue69_configuracion.py -q   ->  53 passed
```

## 2. Cobertura de la lista de requisitos

Verificada por `tests/frontend/test_issue_66_selector_objetivos.py`. La tabla punto por punto
está en el informe (`informe-issue-66-selector-funciones-endpoints.md`, sección 12).

## 3. Verificación lógica real (Node)

Se extrajo el código real de la pantalla (`vista-previa.js`) y se ejecutó con Node sobre datos
simulados (no sobre texto, sino ejecutando las funciones puras):

- **Calidad:** modelo + estado declarado → `lista`; solo modelo → `mejorable`; solo estado →
  `mejorable`; ninguno → `incierto`; **200 por defecto (no declarado) → `mejorable`**.
- **Elegibilidad:** `GET /a` (ruta resuelta) → `true`; sin objetivo (ruta no resuelta) → `false`.
- **Conteos:** 5 endpoints detectados (incluye el no resuelto), 3 «por revisar» en el archivo A.
- **Inclusión:** el archivo A entrega `GET /a, POST /a` (deja fuera el no incluido y el no resuelto);
  el archivo B entrega `DELETE /c`; un módulo con endpoint sin ruta queda **no seleccionado**.

## 4. Validación visual (capturas reales)

Las capturas de interfaz se hicieron con el navegador **Edge en modo sin ventana (headless)**
abriendo la pantalla **real** del frontend del proyecto en **modo demostración** (sin Python). La
versión «antes» se tomó del **código base** `origin/develop` extraído con `git archive` (solo
lectura). **No son capturas de QAgent en pywebview** (la app de escritorio); esa validación sigue
pendiente (ver sección 5). Las capturas de terminal se generaron a partir del **texto real** de las
salidas guardadas en esta carpeta.

| Imagen | Procedencia | Qué demuestra |
|---|---|---|
| `img/prueba-1-antes-sin-selector.png` | Edge headless · frontend real · modo demo · `origin/develop` | Sin selector; endpoint en 3 columnas planas |
| `img/prueba-2-despues-funciones-y-selector.png` | Edge headless · frontend real · modo demo · rama #66 | Selector Funciones/Endpoints; tabla de funciones #65 intacta |
| `img/prueba-3-despues-tabla-endpoints.png` | Edge headless · frontend real · modo demo · rama #66 | Tabla de endpoints: 7 columnas, agrupada, endpoint sin ruta deshabilitado |
| `img/prueba-4-pytest-issue66.png` | Render del texto real → `salida-pytest-issue66.txt` | 33 pruebas nuevas pasan |
| `img/prueba-5-pytest-frontend.png` | Render del texto real → `salida-pytest-frontend.txt` | 161 pruebas de la interfaz pasan |
| `img/prueba-6-test-rapido.png` | Render del texto real → `salida-test-rapido.txt` | Suite rápida: 1123 passed, 19 deselected |
| `img/prueba-7-node-endpoints.png` | Render del texto real → `salida-node-endpoints.txt` | Verificación real de Calidad, elegibilidad e inclusión |

Comprobado en las capturas de interfaz: el selector con los totales detectados (19 funciones / 7
endpoints) y el aviso ⚠; las 7 columnas de endpoints y su orden; el semáforo de Calidad con texto;
el Estado en gris para el 200 no declarado; «—» en Respuesta cuando falta; el número de Errores; las
dependencias en «Simula»; la agrupación por archivo con «N endpoints · M por revisar»; la casilla
**Incluir** deshabilitada en el endpoint «Ruta no disponible»; y el pie «15 objetivos seleccionados
(9 funciones · 6 endpoints)».

> Las capturas muestran datos de la **demostración** del propio QAgent. El nombre de proyecto y la
> ruta (`E:/Proyectos/ecommerce-core`) son los de ejemplo del programa.
>
> En los archivos `salida-*.txt` se reemplazaron las rutas personales de la máquina por `python` /
> `QAgent` para no exponer datos del equipo. No contienen claves ni credenciales.
>
> `manifiesto-sha256.txt` registra el SHA-256 de cada archivo de este cambio. Como los archivos
> todavía no están en el repositorio (la issue no se ha commiteado), los hashes de texto se
> calcularon sobre el contenido con finales de línea **LF** (como quedará guardado al commitear);
> los `.png` se hashearon tal cual.

## 5. Guía para la validación manual en la aplicación de escritorio

Para repetir la validación en la aplicación real (no se pudo automatizar aquí porque pywebview abre
una ventana interactiva):

1. `qagent` (o `python -m qagent`).
2. Abrir un proyecto Python 3.10+ que tenga **endpoints FastAPI** (de preferencia con y sin
   `response_model` / `status_code`, para ver las tres Calidades).
3. Ir a **Vista previa**.
4. En **Objetivos detectados**, comprobar el selector:
   - Dos botones, **Funciones (N)** y **Endpoints (N)**, con N = total detectado.
   - Si el proyecto no tiene endpoints, **Endpoints** sale deshabilitado con su explicación.
   - El botón de la vista con objetivos «por revisar» muestra **⚠**.
   - Cambiar de pestaña **no** debe recargar el proyecto ni perder lo marcado.
5. En la pestaña **Endpoints**, comprobar la tabla:
   - Orden de columnas: Endpoint · Calidad · Estado · Respuesta · Errores · Simula · Incluir.
   - Cada archivo es un encabezado con «N endpoints · M por revisar» y su casilla **Incluir**.
   - La flecha ▸/▾ abre y cierra (independiente del plegado de funciones).
   - Pasar el mouse y enfocar con **Tab** el ícono ⓘ de cada columna: debe verse la ayuda.
   - Calidad: Lista si hay modelo y estado declarado; Mejorable si hay solo uno; Incierto si no hay
     ninguno. Un 200 sin declarar **no** debe verse como estado declarado (celda en gris).
   - Un endpoint con ruta no resuelta aparece como «Ruta no disponible», con la casilla **Incluir**
     deshabilitada; al marcarlo **no** debe contar ni enviarse.
   - Marcar/desmarcar **Incluir** en el archivo cambia todos sus endpoints analizables; con
     selección parcial debe verse el estado indeterminado (guion).
6. En la pestaña **Funciones**, comprobar que todo sigue como en la issue #65 (no se debe haber
   roto el plegado ni la selección).
7. Pulsar **Continuar: configuración de pruebas** y comprobar que el alcance elegido coincide con lo
   marcado: el pie debe decir «… objetivos seleccionados (F funciones · E endpoints)», donde **E**
   no incluye los endpoints sin ruta.
