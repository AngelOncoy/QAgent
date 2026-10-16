# Pruebas ejecutadas — selección de objetivos y directorio de clonación

Fecha: 16 de octubre de 2026<br>
Rama: `fix/seleccion-objetivos-directorio-clon`<br>
Rama de destino futura: `develop`<br>
Commit base: `7dc800d73da6af5cc0a4de336bbc455809b8898d`<br>
IA: `QAGENT_FAKE_LLM=1` (sin proveedores reales, 0 tokens)

Este documento registra las verificaciones de la Fase 3 y sirve como bitácora
complementaria del informe definitivo
`informe-fix-seleccion-objetivos-directorio-clon.md`. No implica commit, push ni Pull
Request.

## Entorno

- Windows 11, zona horaria `America/Lima`.
- Python `3.14.7` de 64 bits.
- QAgent `0.1.0`, aplicación de escritorio pywebview.
- Backend visual: pywebview WinForms/Chromium.
- Git disponible; Docker no fue necesario para estas verificaciones.
- Plugin Browser y Playwright: no disponibles en esta sesión.
- Forma normal de inicio comprobada: `$env:QAGENT_FAKE_LLM='1'; python -m qagent`.
- Para no alterar `~/.qagent/` ni proyectos personales, la validación visual invocó la
  entrada real `qagent.app.desktop.main()` con `Path.home()` aislado únicamente dentro
  del proceso de validación.
- Área controlada, fuera de Temp:
  `C:\Users\Rodrigo\Desktop\QAgent-validacion-fase3`.

## Verificación inicial de Git

- Repositorio: `C:/Users/Rodrigo/Desktop/Codigos/QAgent`.
- Rama activa confirmada: `fix/seleccion-objetivos-directorio-clon`.
- Se encontraron los 14 archivos modificados o nuevos esperados antes de agregar estas
  evidencias.
- `develop` local, `origin/develop` y el commit base seguían en `7dc800d`.
- No se hizo merge ni rebase.
- La issue #61 continúa en `origin/fix/issue-61-clon-recientes`, commit `7b7ac4c`.

### Riesgo de integración con la issue #61

Las dos ramas modifican `src/qagent/app/desktop.py` y
`src/qagent/frontend/componentes/inicio/modal-clonar.js`.

- Esta rama agrega el selector de carpeta antes de `doClone()` y transmite la selección
  de objetivos en `start_run()`.
- La rama de la issue #61 registra el clon exitoso en Recientes y modifica
  `finClonado()` para esperar `cargarRecientes()`, escapar la ruta y mostrar una posible
  advertencia.
- Los cambios son funcionalmente complementarios y están en zonas distintas, pero el
  mismo componente puede requerir resolución manual al integrar.
- La resolución futura debe conservar el botón Examinar y, además, todo el comportamiento
  de Recientes, `await cargarRecientes()`, `escHtml(r.destino)` y `r.advertencia` de #61.

## Proyecto controlado

`proyecto-mixto` contiene:

| Archivo | Funciones ordinarias | Endpoints | Resultado esperado |
|---|---:|---:|---|
| `__init__.py` | 0 | 0 | Desmarcado, deshabilitado y atenuado |
| `vacio.py` | 0 | 0 | Desmarcado, deshabilitado y atenuado |
| `funciones.py` | 2 | 0 | Habilitado y seleccionable |
| `api.py` | 0 | 2 | Habilitado y seleccionable |

También se utilizó `proyecto-solo-endpoints`, con 0 funciones ordinarias y 2 endpoints.
Los archivos fueron analizados estáticamente; no se ejecutó su código.

## Validación A — archivos sin objetivos

| Criterio | Resultado | Evidencia |
|---|---|---|
| Vacíos desmarcados por defecto | Aprobado | Estado pywebview: `sel=false` para `__init__.py` y `vacio.py` |
| Checkbox deshabilitado | Aprobado | 2 controles `#tree input:disabled`; CAP-01 |
| Apariencia atenuada | Aprobado | CAP-01 |
| Texto “sin objetivos analizables” | Aprobado | 2 notas DOM; CAP-01 |
| Seleccionar todos ignora vacíos | Aprobado | `vaciosSeleccionados=0`; CAP-04 |
| Archivo con funciones habilitado | Aprobado | CAP-02 |
| Archivo con endpoints y 0 funciones habilitado | Aprobado | CAP-03 |
| Contadores solo con objetivos válidos | Aprobado | `2 módulos · 4 objetivos`; CAP-04 |
| Proyecto solo-endpoints continúa | Aprobado | 0 funciones, 2 endpoints, `toTests.disabled=false`, Configuración visible |
| Selección enviada con identidades reales | Aprobado | `funciones.py`: `sumar`, `absoluto`; `api.py`: `GET /salud`, `POST /items` |
| Objetivo inexistente rechazado | Aprobado | `status=seleccion_invalida`; mensaje “Objetivos inexistentes…” |
| Regresión respeta selección | Aprobado | Test aislado: total 1, aceptada 1, una llamada al ejecutor |

La pantalla real no presentó página en blanco, overlay de error, recortes críticos ni
solapamientos. La tabla usa scroll vertical cuando corresponde.

## Validación B — botón Examinar

| Criterio | Resultado | Evidencia |
|---|---|---|
| Botón Examinar visible | Aprobado | CAP-05 |
| Selector nativo de Windows | Aprobado | CAP-06 |
| Selección de carpeta padre | Aprobado | `...\QAgent-validacion-fase3\clones`; CAP-06 |
| Nombre sugerido agregado | Aprobado | destino `...\clones\Hello-World`; CAP-07 |
| Ruta editable manualmente | Aprobado | `C:\editado-manualmente`, `dirEditado=true` |
| Cancelar conserva valor anterior | Aprobado | permaneció `C:\destino-anterior` |
| Elegir carpeta no clona | Aprobado | `clonando=false`; destino aún no existía tras CAP-07 |
| Rama y clonado superficial | Aprobado | `master`, checkbox `--depth 1` activo |
| Destino ocupado protegido | Aprobado | `tipo_error=destino_ocupado`; Git no se ejecutó y `README` no cambió |
| Sin solapamientos visuales | Aprobado | CAP-05 y CAP-07 |

### Clonación controlada real

Se realizó una única clonación desde la interfaz:

- URL: `https://github.com/octocat/Hello-World.git`.
- Rama: `master`.
- Destino aislado: `C:\Users\Rodrigo\Desktop\QAgent-validacion-fase3\clones\Hello-World`.
- Resultado visual: aviso verde “Repositorio clonado…” (CAP-08).
- `README`: presente.
- `git branch --show-current`: `master`.
- `git rev-list --count HEAD`: `1`.
- `git remote get-url origin`: URL esperada.

El repositorio de ejemplo no contiene Python; por ello la Vista previa posterior muestra
0 módulos y el botón Continuar queda deshabilitado. Eso no afecta el resultado del clonado.

### Advertencia de compatibilidad de pywebview

pywebview 6.2.1 abrió correctamente el selector, pero emitió la advertencia:
`FOLDER_DIALOG is deprecated ... Use 'FileDialog.FOLDER' instead`. No se modificó código
en esta fase. Como mantenimiento futuro conviene usar `webview.FileDialog.FOLDER` con una
compatibilidad controlada para versiones anteriores de pywebview.

## Pruebas automatizadas

Los resultados siguientes se informan por suite; no se suman porque algunas suites son
subconjuntos de la suite rápida.

| Comando | Resultado real |
|---|---|
| `python test.py --rapido` | `1038 passed, 19 deselected` |
| `python -m pytest tests/frontend -q` | `81 passed` |
| `python -m pytest tests/proyectos/test_clonador.py -m "not red" -q` | `74 passed, 2 deselected` |
| `python -m pytest tests/proyectos/test_seleccion.py tests/app/test_desktop_selector_clonado.py tests/frontend/test_fase2_seleccion_clonado.py tests/app/test_desktop_corrida.py -q` | `19 passed` |
| Test aislado de selección en Regresión | `1 passed` |

CAP-09 registra la suite rápida y la suite frontend en una consola real.

## Ruff y verificaciones finales

| Comando | Resultado |
|---|---|
| `python -m ruff check src tests scripts test.py` | `All checks passed!` |
| `python -m ruff format --check src tests scripts test.py` | `168 files already formatted` |
| `node --check` sobre los 4 JavaScript modificados | Correcto |
| `git diff --check` | Correcto |

CAP-10 registra estos resultados en una consola real.

## Investigación de WinError 50

El fallo observado ocurrió en la prueba de red
`test_integracion_clona_repositorio_publico_pequeno`, después de que la clonación hubiera
terminado y fuera del flujo de QAgent. El comando exacto que falló fue:

```text
git -C <destino>/Hello-World rev-list --count HEAD
```

La llamada era un `subprocess.run(..., capture_output=True, text=True, check=True)` del
propio test. La traza terminó en `subprocess.Popen._get_handles()` /
`_winapi.DuplicateHandle()` con `WinError 50` bajo Python 3.14.7 en Windows.

Antes del fallo ya se había comprobado:

- `clonador.clonar()` devolvió `ok=True`;
- la carpeta destino existía;
- `README` existía.

En ese intento solo quedó sin comprobar el conteo de commits. No falló el `Popen` que usa
QAgent para clonar: este ya configura `stdin=DEVNULL`, `stdout=DEVNULL` y `stderr=PIPE`.

La limitación se considera del entorno/procedimiento de prueba porque:

- ocurrió en el `subprocess.run` posterior del test, no en `clonador.clonar()`;
- el mismo comando Git directo devolvió después `1`;
- una variante de Python con `stdin=subprocess.DEVNULL` y captura devolvió `1`;
- la clonación real desde la interfaz volvió a concluir correctamente y produjo CAP-08;
- las pruebas offline cubren comando, `--depth 1`, rama, entorno, progreso y destinos
  ocupados.

Corrección futura propuesta, solo para robustecer el test de red: pasar
`stdin=subprocess.DEVNULL` al `subprocess.run` de `rev-list` o ejecutar la verificación
Git sin heredar el handle de entrada del PTY. No se modificó código en esta fase.

## Inventario de evidencias

| Captura | Contenido | Estado |
|---|---|---|
| CAP-01 | Archivos sin objetivos deshabilitados y contador en cero | Obtenida |
| CAP-02 | Archivo con funciones seleccionable | Obtenida |
| CAP-03 | Archivo con endpoints seleccionable | Obtenida |
| CAP-04 | Seleccionar todos y contador de 4 objetivos | Obtenida |
| CAP-05 | Modal Clonar con Examinar | Obtenida |
| CAP-06 | Selector nativo en la carpeta aislada | Obtenida |
| CAP-07 | Destino final con nombre sugerido | Obtenida |
| CAP-08 | Clonación real correcta | Obtenida |
| CAP-09 | Pruebas automatizadas | Obtenida |
| CAP-10 | Ruff, JavaScript y `git diff --check` | Obtenida |

No se observaron claves, tokens ni credenciales en las imágenes. Las rutas visibles
corresponden al repositorio y al área controlada de validación.

## Evidencias pendientes

No quedan capturas ni documentos técnicos pendientes para esta fase. Continúan
pendientes de autorización el staging explícito de las evidencias ignoradas, el commit,
el push, el Pull Request y la decisión sobre cómo integrar posteriormente la rama de la
issue #61.
