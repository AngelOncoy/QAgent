# Auditoría inicial — issue #92

Fecha: 2026-10-17

## Base auditada

- Rama: `fix/issue-92-correcciones-generales`
- Base: `0172b804f2631180327614ab1dbb3e9608c77ffd`
- Referencia: `origin/develop` en el mismo commit al crear la rama.
- Modo de IA: `QAGENT_FAKE_LLM=1`.
- No se mezcló la rama de la issue #67 ni se modificó código funcional.

## Resultado ejecutivo

No se confirmaron errores críticos ni altos. Las suites oficiales, el lint y el
formato pasan. Se confirmaron cuatro defectos en la interfaz de demostración y
su adaptación a ventanas pequeñas: dos de severidad media y dos de severidad
baja. La ejecución real dentro de Docker y la ventana pywebview real quedan
pendientes porque Docker Desktop no está iniciado y el entorno de auditoría no
permite controlar una ventana pywebview.

## Áreas auditadas

| Área | Verificación | Resultado |
|---|---|---|
| Inicio y estabilidad | `python -m qagent --version`, importaciones y suite completa | Correcto; QAgent 0.1.0 |
| Navegación y frontend | Ocho pantallas de la demo, consola, capturas y suite frontend | Cuatro hallazgos visuales/demo |
| Apertura y clonación | Pruebas de `proyectos/` y `app/` incluidas en la suite completa | Sin fallo automatizado |
| Proyectos recientes | Pruebas de almacenamiento/app y pantalla de demo | Sin fallo automatizado |
| Árbol y selección AST | `proyectos/seleccion.py` y sus pruebas | Correcto |
| Funciones y endpoints | Selector, tablas, plegado y selección individual | Funcional; ver Q92-001 a Q92-003 |
| Calidad y Profundizar | Datos, selección y propiedad `critical` | Correcto en pruebas |
| Configuración de pruebas | Navegación y pruebas frontend/orquestador | Correcto |
| Frontend/backend | Correspondencia entre llamadas JS y métodos `DesktopAPI` | Sin llamadas directas faltantes |
| IA simulada | Planner, Generator, Reviewer y clientes fake | Correcto; sin proveedor real |
| Generación y revisión | Suites de agentes y orquestador | Correcto fuera de Docker |
| Sandbox | Pruebas unitarias; pruebas Docker recolectadas | 23 omitidas: daemon no iniciado |
| Resultados e historial | `storage/`, `almacenamiento/` y pantallas demo | Sin fallo automatizado |
| Manejo de errores | Casos automatizados de entorno, contratos y corrida | Sin fallo confirmado |
| Diseño y legibilidad | 1440×900 y 1024×700 con Microsoft Edge/Playwright | Hallazgos Q92-001 a Q92-004 |
| Compatibilidad con develop | Suite completa sobre la base del PR #91 | Correcto |

## Validación visual

Flujo probado en la interfaz HTML de demostración:

1. Cargar la aplicación.
2. Abrir el proyecto reciente `ecommerce-core`.
3. Mostrar Vista previa.
4. Alternar de Funciones a Endpoints.
5. Desmarcar un endpoint individual y comprobar el cambio de estado.
6. Recorrer Configuración de pruebas, Monitor, Ejecución, Reporte, Historial y Configuración.

En 1440×900 la aplicación carga contenido significativo y el selector conserva
su estado. En 1024×700 la Vista previa puede desplazarse horizontalmente al
llevar el selector Endpoints a la vista, ocultando el comienzo del contenido.
Las capturas usadas como evidencia son capturas reales del frontend servido en
Microsoft Edge, no capturas de pywebview, y se conservaron fuera del repositorio
en `%TEMP%/qagent-issue92/`.

## Riesgos y dependencias

- La rama de la issue #67 no está integrada y modifica varios de los mismos
  archivos de frontend, Planner, orquestador y persistencia. No debe mezclarse
  durante las correcciones de #92 sin una integración separada.
- Los cambios de layout pueden afectar las tablas de funciones y endpoints; se
  necesitan pruebas en el ancho mínimo declarado por pywebview (`960×600`).
- Añadir un valor por defecto a las decisiones de endpoints debe cubrir tanto
  los datos demo como los datos reales entregados por el analizador AST.
- La validación del sandbox real necesita Docker Desktop y puede descubrir
  defectos que la suite sin daemon no cubre.

## Orden recomendado

1. Corregir Q92-001 y añadir regresión para 1024×700 y 960×600.
2. Corregir Q92-002 y añadir una prueba de renderizado de decisiones.
3. Ajustar Q92-003 junto con el cambio responsive para evitar dos retoques del mismo encabezado.
4. Resolver Q92-004 incorporando el favicon empaquetado.
5. Repetir las tres suites base y la validación visual.
6. Con Docker Desktop iniciado, ejecutar los 23 casos `docker`.
7. Realizar una pasada manual en la ventana pywebview antes del commit.
