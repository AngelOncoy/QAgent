# Issue #61 · Pruebas ejecutadas

## Entorno

- Fecha: 16 de octubre de 2026.
- Rama: `fix/issue-61-clon-recientes`.
- Commit base de `develop`: `7dc800d73da6af5cc0a4de336bbc455809b8898d`.
- Copia de trabajo: `C:\Users\Rodrigo\Desktop\Codigos\QAgent-fix-clon-recientes`.
- Python: 3.14.7, desde el entorno virtual existente de QAgent.
- IA: `QAGENT_FAKE_LLM=1`; no se ejecutó el pipeline ni se contactaron proveedores.
- Docker: no utilizado.
- Browser plugin: no disponible.
- Playwright: no instalado; la validación se realizó sobre la aplicación pywebview real.

## Aislamiento de la validación visual

La aplicación normalmente guarda recientes en `C:\Users\Rodrigo\.qagent\recientes.json`.
Para no modificar ese archivo ni los proyectos reales se utilizó esta carpeta estable:

```text
C:\Users\Rodrigo\Desktop\Codigos\QAgent-issue-61-evidencia
```

Contenido relevante:

```text
perfil\.qagent\recientes.json
proyectos\QAgent-clonado-issue-61
```

QAgent se inició con `HOME` y `USERPROFILE` apuntando a `perfil`. El repositorio se
clonó desde `https://github.com/AngelOncoy/QAgent.git`, rama `develop`, en
`proyectos\QAgent-clonado-issue-61`. La carpeta se conserva para revisión y no debe
eliminarse hasta recibir autorización.

## Comandos y resultados automatizados

Todos los comandos se ejecutaron desde la copia FIX.

### Pruebas backend específicas

```powershell
$env:QAGENT_FAKE_LLM = "1"
& C:\Users\Rodrigo\Desktop\Codigos\QAgent\.venv\Scripts\python.exe `
  -m pytest tests/app/test_desktop_clonado_recientes.py -q
```

Resultado real más reciente:

```text
5 passed in 1.17s
```

Incluye un `git clone` real y offline desde una rama específica de un repositorio
temporal local; también comprueba persistencia, ausencia de duplicados, fallo de
clonación y error al escribir recientes.

### Pruebas frontend específicas

```powershell
& C:\Users\Rodrigo\Desktop\Codigos\QAgent\.venv\Scripts\python.exe `
  -m pytest tests/frontend/test_issue_61_clon_recientes.py -q
```

Resultado real más reciente:

```text
4 passed in 0.24s
```

La suite frontend completa también fue ejecutada previamente con resultado
`80 passed in 1.12s`.

### Suite rápida completa

```powershell
$env:QAGENT_FAKE_LLM = "1"
& C:\Users\Rodrigo\Desktop\Codigos\QAgent\.venv\Scripts\python.exe `
  -m pytest -q -m "not docker and not red"
```

Resultado real más reciente:

```text
1033 passed, 19 deselected in 25.29s
```

### Calidad y formato

Las verificaciones realizadas en la fase de implementación permanecen aprobadas:

```text
ruff check: All checks passed!
ruff format --check: 3 files already formatted
git diff --check: sin errores
```

## Validación visual real

1. Se inició QAgent con el perfil aislado vacío: no había proyectos recientes.
2. Se abrió el modal **Abrir repositorio** y se configuraron URL, rama `develop` y
   la ruta estable de evidencia.
3. La clonación terminó correctamente y QAgent conservó la navegación a Vista previa.
4. Al volver a Inicio, el clon apareció automáticamente y el contador mostró
   `1 proyecto`, sin usar antes **Abrir proyecto**.
5. El archivo aislado `recientes.json` confirmó inicialmente `origen: git`, la URL
   remota y la ruta local.
6. Se cerró y reinició QAgent con el mismo perfil: el proyecto persistió.
7. Se abrió la misma carpeta mediante **Abrir proyecto**: el contador permaneció en
   `1 proyecto`, por lo que no se creó un duplicado.

Además, Git confirmó que el clon quedó en la rama `develop` y que `origin` apunta a
`https://github.com/AngelOncoy/QAgent.git`.

## Matriz de resultados

| Escenario | Resultado obtenido | Estado | Evidencia |
|---|---|---|---|
| Estado inicial | Perfil aislado vacío, sin proyectos recientes | Aprobado | `img/CAP-01-inicio-antes-clonacion.png` |
| Configuración | URL oficial, rama `develop` y ruta estable configuradas | Aprobado | `img/CAP-02-configuracion-clonacion.png` |
| Clon exitoso | Navegación conservada a Vista previa | Aprobado | `img/CAP-03-clonacion-exitosa.png` |
| Registro automático | El clon aparece en Inicio sin abrirlo manualmente | Aprobado | `img/CAP-04-proyecto-registrado-automaticamente.png` |
| Contador | El contador cambia de lista vacía a `1 proyecto` | Aprobado | `img/CAP-05-contador-actualizado.png` |
| Persistencia | El proyecto continúa tras cerrar y reiniciar QAgent | Aprobado | `img/CAP-06-persistencia-despues-reinicio.png` |
| Sin duplicados | Abrir la misma carpeta mantiene `1 proyecto` | Aprobado | `img/CAP-07-sin-duplicados.png` |
| Backend | Cinco pruebas específicas aprobadas | Aprobado | `img/CAP-08-pruebas-backend.png` |
| Frontend | Cuatro pruebas específicas aprobadas | Aprobado | `img/CAP-09-pruebas-frontend.png` |
| Calidad final | Ruff lint, formato y `git diff --check` sin errores | Aprobado | `img/CAP-10-verificaciones-finales.png` |

## Incidencias y decisiones

1. Browser y Playwright no estaban disponibles; se utilizó la aplicación pywebview
   real y automatización nativa de Windows para la interacción y las capturas.
2. Las primeras pruebas visuales se habían preparado bajo una ruta temporal. A
   solicitud del usuario, se repitió todo el flujo desde cero en la carpeta estable
   del Escritorio y se sobrescribieron todas las capturas finales.
3. Windows aplicaba escalado DPI al cursor; las coordenadas se ajustaron y cada
   captura se inspeccionó antes de aceptarla.
4. Al reabrir la carpeta con el flujo local, el mecanismo existente actualiza el
   registro único con `origen: local`. No crea duplicados; el registro original como
   `git` quedó comprobado antes de esa reapertura.

## Integridad de las capturas

Los nombres, tamaños y hashes SHA-256 de las diez imágenes están registrados en
[`evidencias_sha256.json`](evidencias_sha256.json). CAP-04, CAP-06 y CAP-07 tienen el
mismo hash porque, después de cada acción, QAgent renderiza exactamente el mismo
estado final: una entrada visible y contador igual a uno.

## Estado documental

- Resultados automatizados: verificados.
- Escenarios visuales: verificados.
- Capturas CAP-01 a CAP-10: creadas e inspeccionadas.
- Informe técnico completo: pendiente de la siguiente fase.
