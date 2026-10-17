# Bitácora de pruebas · Issue #65 (nueva vista de Vista previa)

Fecha: 16 de octubre de 2026. Entorno: Windows, Python 3.14, Node 22+, Microsoft Edge.
Rama: `feat/issue-65-nueva-vista-previa` (base `origin/develop` = `6d990da`).

## 1. Pruebas automatizadas ejecutadas

| Comando | Resultado real |
|---|---|
| `python -m pytest tests/frontend/test_issue_65_vista_previa.py -v` | **32 passed** en 0.36 s |
| `python -m pytest tests/frontend -q` | **117 passed** en 1.48 s |
| `python test.py --rapido` | **1079 passed, 19 deselected** en 40.56 s |
| `python test.py` (completo) | Lint **OK**; Formato **FALLA** (ver nota); pytest **1098 passed** en 141.17 s |
| `node --check src/qagent/frontend/componentes/vista-previa/vista-previa.js` | **OK** (sin errores de sintaxis) |
| `python -m ruff check src tests scripts test.py` | **All checks passed!** |
| `python -m ruff format --check <archivos tocados>` | **ya formateados** |
| `git diff --check` | **OK** (sin espacios en blanco problemáticos) |

Salidas completas guardadas en esta carpeta: `salida-pytest-issue65.txt`, `salida-pytest-frontend.txt`,
`salida-test-rapido.txt`, `salida-node-calidad.txt`, `salida-node-plegado.txt`.

### Nota sobre `python test.py` (completo)

El comando ejecuta lint, formato y **todas** las pruebas. El único paso que falla es el de formato, por el
archivo `src/qagent/app/desktop.py:88`, que **no se modificó en esta issue** y que Ruff 0.17.1 quiere
reformatear (agregar una línea en blanco tras un `import`). No se tocó porque el alcance excluye el backend y
porque sería un cambio ajeno. Todas las pruebas (1098) pasan; no hay llamadas reales a proveedores de IA
(`QAGENT_FAKE_LLM=1`). Las 19 pruebas omitidas en `--rapido` son las marcadas `docker`/`red`.

**Comprobación de que el fallo es preexistente (solo lectura):**

- El archivo `src/qagent/app/desktop.py` está **sin modificar** en esta rama: `git status` no lo lista y su
  blob es el mismo en `HEAD` y en `origin/develop`.
- `python -m ruff format --check` falla igual sobre la copia temporal del archivo tomada de `HEAD`
  (`git show HEAD:src/qagent/app/desktop.py`), es decir, sobre la versión base, sin relación con la issue #65.
- Conclusión: lo provoca la versión de Ruff instalada (0.17.1), no este cambio. Corresponde una corrección
  independiente sobre `develop` (en otro PR) si se desea dejar el paso de formato en verde.

## 2. Cobertura de los 30 puntos pedidos por la issue

Todos verificados por `tests/frontend/test_issue_65_vista_previa.py` (sin navegador):

| # | Punto | Test |
|---|---|---|
| 1 | Orden exacto de columnas | `test_orden_exacto_de_las_columnas` |
| 2 | Calidad Lista | `test_calidad_lista_cuando_hay_tipos_y_docstring` |
| 3 | Calidad Mejorable | `test_calidad_mejorable_cuando_falta_tipos_pero_hay_docstring` |
| 4 | Calidad Incierto | `test_calidad_incierto_cuando_falta_docstring` |
| 5 | Prioridad de Incierto | `test_incierto_tiene_prioridad_sobre_los_tipos` |
| 6 | Render de ✓ y ✗ | `test_indicadores_tipos_y_docstring` |
| 7 | Condicionales con el campo existente | `test_condicionales_usan_el_campo_br_existente` |
| 8 | Crítica → Profundizar | `test_la_columna_critica_se_renombra_a_profundizar` |
| 9 | Se conserva `crit` | `test_se_conserva_la_variable_interna_crit` |
| 10 | Valor inicial de `critica_propuesta` | `test_valor_inicial_de_profundizar_viene_de_critica_propuesta` |
| 11 | Profundizar editable | `test_profundizar_es_editable_manualmente` |
| 12 | Tooltips de cabeceras | `test_tooltips_explicativos_en_las_cabeceras`, `test_tooltips_accesibles_con_mouse_y_teclado` |
| 13 | Agrupación por archivo | `test_agrupacion_por_archivo_con_encabezado_plegable` |
| 14 | Conteo de funciones por archivo | `test_conteo_de_funciones_por_archivo` |
| 15 | Conteo «por revisar» | `test_conteo_por_revisar_excluye_las_listas` |
| 16 | Etiquetas de spec | `test_se_conservan_las_etiquetas_de_spec` |
| 17 | Despliegue inicial por revisar | `test_archivos_con_funciones_por_revisar_abren_por_defecto` |
| 18 | Plegado inicial sin revisar | `test_archivos_sin_funciones_por_revisar_quedan_plegados` |
| 19 | Expansión/plegado manual | `test_el_usuario_puede_abrir_y_cerrar_manual` |
| 20 | Selección al plegar | `test_plegar_no_altera_la_seleccion` |
| 21-22 | Incluir/desmarcar archivo | `test_checkbox_de_archivo_marca_desmarca_todas_las_funciones` |
| 23 | Indeterminado | `test_estado_indeterminado_del_checkbox_de_archivo` |
| 24 | Sincronización del encabezado | `test_encabezado_sincronizado_con_las_casillas_individuales` |
| 25 | Errores de sintaxis | `test_los_errores_de_sintaxis_se_siguen_mostrando` |
| 26 | Archivos sin funciones | `test_archivos_sin_funciones` |
| 27 | Selección AST | `test_conserva_la_seleccion_ast` |
| 28 | Tabla de endpoints | `test_conserva_la_tabla_de_endpoints` |
| 29 | Compatibilidad #63 | `test_compatibilidad_con_las_regresiones_de_63` |
| 30 | Ausencia de errores JS | `test_sin_errores_de_sintaxis_javascript` |

## 3. Verificación lógica real (Node)

Se extrajo el código real de la pantalla y se ejecutó con Node:

- **Calidad:** `typed+doc → Lista`, `noTyped+doc → Mejorable`, `typed+noDoc → Incierto`,
  `noTyped+noDoc → Incierto`.
- **Plegado:** un archivo con 1 función por revisar abre por defecto (`true`); uno sin funciones por revisar
  queda plegado (`false`); una decisión manual del usuario se respeta por encima del valor por defecto.

## 4. Validación visual (capturas reales)

Las capturas de interfaz se hicieron con el navegador **Edge en modo sin ventana (headless)** abriendo la
pantalla **real** del frontend del proyecto en **modo demostración** (sin Python), recorriendo la misma ruta en
la versión anterior y en la nueva. **No son capturas de QAgent en pywebview** (la app de escritorio); esa
validación sigue pendiente (ver sección 5). Las capturas de terminal se generaron a partir del **texto real**
de las salidas guardadas en esta carpeta.

| Imagen | Procedencia | Qué demuestra |
|---|---|---|
| `img/prueba-1a-antes-tabla.png` | Edge headless · frontend real · modo demo · versión `origin/develop` | Tabla anterior: 6 columnas planas, fila de archivo sin plegar |
| `img/prueba-3-columnas-completas.png` | Edge headless · frontend real · modo demo · rama #65 | 7 columnas con Calidad y archivos agrupados/plegables |
| `img/prueba-4-tooltip-calidad.png` | Edge headless · frontend real · modo demo · rama #65 | Tooltip real de la cabecera «Calidad» |
| `img/prueba-5-pytest-issue65.png` | Render del texto real → `salida-pytest-issue65.txt` | 32 pruebas nuevas pasan |
| `img/prueba-6-test-rapido.png` | Render del texto real → `salida-test-rapido.txt` | Suite rápida: 1079 passed, 19 deselected |
| `img/prueba-7-calidad-node.png` | Render del texto real → `salida-node-calidad.txt` | Los 4 casos del cálculo de Calidad |
| `img/prueba-8-pytest-frontend.png` | Render del texto real → `salida-pytest-frontend.txt` | 117 pruebas de la interfaz pasan |

Comprobado en las capturas de interfaz: las 7 columnas y su orden; el semáforo de Calidad con texto; ✓/✗; el
número de condicionales; los encabezados de archivo con «por revisar» y las etiquetas de spec; archivos
desplegados (`inventory.py`, `pricing.py`, con funciones por revisar) y plegados (`cart.py`, `discounts.py`); y
el tooltip.

> Las capturas muestran datos de la **demostración** del propio QAgent. El nombre de proyecto y la ruta
> (`E:/Proyectos/ecommerce-core`) son los de ejemplo del programa.
>
> En los archivos `salida-*.txt` se reemplazaron las rutas personales de la máquina (`C:\Users\...`) por
> `python` / `QAgent` para no exponer datos del equipo. No contienen claves ni credenciales.
>
> `manifiesto-sha256.txt` registra el SHA-256 de cada archivo tal como queda **guardado en el repositorio**
> (finales de línea LF). En Windows con `core.autocrlf`, al descargar los archivos de texto pueden verse con
> CRLF; para reproducir los hashes hay que calcularlos sobre el contenido del repositorio (`git show :ruta`).

## 5. Guía para la validación manual en la aplicación de escritorio

Para repetir la validación en la aplicación real (no se pudo automatizar aquí porque pywebview abre una
ventana interactiva):

1. `qagent` (o `python -m qagent`).
2. Abrir un proyecto Python 3.10+ (de preferencia uno con varios archivos y funciones sin docstring).
3. Ir a **Vista previa** (barra lateral izquierda).
4. Comprobar, en la tabla «Funciones detectadas»:
   - El orden de columnas: Función · Calidad · Tipos declarados · Docstring · Condicionales · Profundizar ·
     Incluir.
   - Que cada archivo es un encabezado con ícono, ruta, «N funciones», «M por revisar» y, si aplica, la
     etiqueta de spec (Vigente / Cambió / Sin spec previo).
   - Que los archivos con «por revisar» ≥ 1 abren solos y los de «0 por revisar» salen plegados.
   - Que la flecha ▸/▾ abre y cierra cada archivo.
   - Pasar el mouse y enfocar con **Tab** el ícono ⓘ de cada cabecera: debe verse el texto de ayuda.
   - Marcar/desmarcar **Incluir** en un archivo: todas sus funciones cambian; con selección parcial debe verse
     el estado indeterminado (guion) y la barra superior debe reflejar el cambio.
   - Marcar **Profundizar** no debe cambiar **Incluir**.
   - Abrir un archivo con error de sintaxis: debe mostrar la fila roja «no se pudo analizar» con la
     explicación, sin inventar funciones.
5. Pulsar **Continuar: configuración de pruebas** y comprobar que el alcance elegido coincide con lo marcado.
