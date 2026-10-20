# HU-22 · Descargar el informe como evidencia

**Informe de lo realizado** · 11 de octubre de 2026 · Responsable: Castillo Pezo, Mateo Salvador Vincenzo

## En pocas palabras

El botón «Exportar informe» solo funcionaba con los datos fijos de la demostración (y en una corrida real se ocultaba). Además, la opción PDF solo mostraba un aviso simulado sin generar ningún archivo. Ahora el botón está activo tanto en la demostración como tras una corrida del sistema, y exporta el informe real en **PDF interactivo** (con pestañas clicables, tarjetas KPI, gráficas vectoriales y síntesis estadística), **Markdown**, **JSON** o **HTML Interactivo** en `<proyecto>/.pyagent/runs/<run_id>/` (o en la carpeta que elija el auditor) con las 5 métricas comparadas frente a sus metas, modelos usados, costo por agente, specs reutilizados y filtro estricto contra claves de IA (RN-07).

**Historia:** como auditor, quiero descargar el informe de la corrida en un archivo, para usarlo como evidencia formal de la evaluación.

## Qué se revisó y qué se hizo

**1. Elección de formato (PDF, Markdown, JSON o HTML Interactivo) y contenido opcional.**
*Se revisó:* el modal «Exportar informe» solo armaba texto en el navegador con datos de demostración y deshabilitaba opciones o simulaba el PDF.
*Se hizo:* `exportar_informe()` en `src/pyagent/storage/exportar_informe.py` genera los formatos (`informe_<run_id>.pdf`, `informe_<run_id>.md`, `results_<run_id>.json` e `informe_<run_id>.html`). El PDF incorpora una barra superior de 5 pestañas clicables (`/Link` y `/Outlines`), tarjetas KPI ejecutivas, 3 gráficas estadísticas vectoriales y síntesis analítica. El resumen de las 5 métricas va siempre; el detalle por función, las trazas de incidentes, el código de las pruebas generadas y los contratos JSON del Planner se incluyen u omiten según las casillas marcadas.

**2. Carpeta por defecto y cambio de carpeta.**
*Se revisó:* el botón «Cambiar…» solo mostraba un mensaje simulado.
*Se hizo:* por defecto propone `<proyecto>/.pyagent/runs/<run_id>/` con el nombre `informe_<run_id>.pdf`, `.md` o `.html`, o `results_<run_id>.json`. Al pulsar «Cambiar…» en la aplicación de escritorio, se abre el selector nativo de carpetas (`DesktopAPI.select_folder`) y el archivo se guarda en la ruta elegida.

**3. Las 5 métricas con meta y estado, modelos, costo por agente y specs reutilizados.**
*Se revisó:* faltaba reunir en el documento exportado el estado de cada métrica frente a su meta (`Cumple` / `No cumple`), el desglose de costo por agente y el conteo de specs reutilizados de corridas previas.
*Se hizo:* el exportador calcula las 5 métricas (`Pass Rate`, `Cobertura de líneas / ramas`, `Iteraciones promedio`, `Tokens y costo de la corrida` y `Mutation Score`) con su meta de `config.toml` y su estado (`Cumple` / `No cumple`), lista los modelos y precios de Planner, Generator y Reviewer, detalla los tokens y costo en dólares por agente, y lee de `run.json` y `.pyagent/specs/` cuántos specs fueron reutilizados, regenerados o generados.

**4. Coincidencia exacta con la pantalla y `results.json`.**
*Se revisó:* el exportador de la demostración recalculaba cifras en JavaScript a partir de un arreglo fijo.
*Se hizo:* el exportador reutiliza `leer_results()`, `vista_ejecucion()` y `vista_reporte()`, de modo que cada cifra del archivo exportado sale del mismo `results.json` que alimenta las pantallas de Ejecución (HU-18) y Reporte (HU-21).

**5. Protección contra filtración de claves de IA (RN-07).**
*Se revisó:* si una traza o fragmento contuviera por accidente una clave o token, no debía llegar nunca al archivo descargado por el auditor.
*Se hizo:* todo el contenido pasa por `sanitizar_secretos()`, que redacta tanto los valores cargados en `Claves` (`.env`) como cualquier patrón de `pyagent.config.auditoria.PATRONES` (`sk-ant-...`, `sk-proj-...`, `AIza...`, `xai-...`, `ghp_...` y asignaciones de `API_KEY`/`SECRET`/`TOKEN`). Además, `verificar_archivo_sin_claves()` inspecciona el archivo final (incluido el texto extraído del PDF) para comprobar que no queda ningún patrón de clave.

## Criterios de aceptación

| # | Criterio | Cómo se cumple | Prueba |
|---|---|---|---|
| 1 | Elegir formato (PDF, Markdown o JSON) y qué incluir: resumen siempre; detalle, trazas, código y contratos opcionales | Modal `#m-export` conectado a `exportar_informe(formato, opciones)` con `resumen: True` fijo y las 4 secciones opcionales | `test_criterio1_resumen_va_siempre_y_secciones_opcionales_se_controlan` |
| 2 | Guardar por defecto en `<proyecto>/.pyagent/runs/<run_id>/` como `informe_<run_id>.pdf`/`.md` o `results_<run_id>.json`; permitir cambiar carpeta | `carpeta_por_defecto()`, `nombre_archivo_informe()` y parámetro `carpeta_destino` conectado a `select_folder()` | `test_criterio2_guarda_por_defecto_en_carpeta_de_la_corrida_con_nombres_oficiales`, `test_criterio2_permite_cambiar_la_carpeta_de_destino` |
| 3 | Incluye las 5 métricas con meta y estado (Cumple / No cumple), modelos usados, costo por agente y specs reutilizados | `construir_cinco_metricas()`, `resumen_specs_corrida()` y desglose por agente en PDF, Markdown y JSON | `test_criterio3_y_4_incluye_5_metricas_modelos_costo_por_agente_specs_y_coincide_con_pantalla` |
| 4 | Las cifras coinciden con la pantalla porque salen del mismo `results.json` | Lectura única desde `leer_results()`, `vista_ejecucion()` y `vista_reporte()` | `test_criterio3_y_4_incluye_5_metricas_modelos_costo_por_agente_specs_y_coincide_con_pantalla` |
| 5 | El informe nunca incluye claves de IA | Redacción recursiva con `Claves.redactar()` y `auditoria.PATRONES` antes de escribir el archivo | `test_criterio5_y_6_evidencia_aceptacion_sin_claves_rn07_y_pdf_valido` |
| 6 | Evidencia de aceptación: el archivo abre, contiene las 5 métricas con meta y estado, 0 patrones de clave (RN-07) y cifras iguales a `results.json` | Verificación de estructura PDF-1.4, extracción de texto, comparación contra `results.json` y escaneo con `buscar_claves()` | `test_criterio5_y_6_evidencia_aceptacion_sin_claves_rn07_y_pdf_valido` |

## Para qué se hizo

- Entregar al auditor un archivo formal (`.pdf`, `.md` o `.json`) que sirva como evidencia verificable de la corrida sin depender de capturas manuales.
- Permitir adaptar el nivel de detalle del informe (desde un resumen ejecutivo de una página hasta el detalle completo con trazas, pruebas pytest y contratos del Planner).
- Garantizar por construcción que todas las cifras coincidan con `results.json` y que ninguna clave de API pueda filtrarse en la evidencia (RN-07).
