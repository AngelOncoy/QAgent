# BitÃƒÂ¡cora de Pruebas Ã¢â‚¬â€ Issue #92

Fecha: 2026-10-17
Rama: `fix/issue-92-correcciones-generales`
Commit base: `0172b804f2631180327614ab1dbb3e9608c77ffd`
Entorno: Windows 11, PowerShell, Python 3.14.7, Node v24.20.0, Playwright 1.x

---

## 1. Registro HistÃƒÂ³rico: Fase Previa (Codex)

Antes de la interrupciÃƒÂ³n, Codex ejecutÃƒÂ³ las pruebas de la lÃƒÂ­nea base documentadas en `pruebas-base.md`:

- **Suite frontend inicial:** 179 passed.
- **Suite rÃƒÂ¡pida inicial:** 1314 passed, 25 deselected (69.10s).
- **Suite completa inicial:** Ruff check OK, Ruff format OK, 1316 passed, 23 skipped (56.30s).
- **Docker tests:** 23 skipped por ausencia de Docker daemon iniciado.
- **ValidaciÃƒÂ³n visual inicial:** Capturas base en `%TEMP%/qagent-issue92/` que permitieron identificar los defectos Q92-001 a Q92-004.

---

## 2. EjecuciÃƒÂ³n y VerificaciÃƒÂ³n: Fase de RecuperaciÃƒÂ³n (OpenCode)

Tras reanudar los trabajos, OpenCode ejecutÃƒÂ³ las siguientes suites de validaciÃƒÂ³n completa:

### 2.1. VerificaciÃƒÂ³n de Sintaxis y Formato

#### Ruff Lint (`python -m ruff check src tests scripts test.py`)
```text
All checks passed!
```
- **Resultado:** APROBADO (0 errores).

#### Ruff Format (`python -m ruff format --check src tests scripts test.py`)
```text
202 files already formatted
```
- **Resultado:** APROBADO (0 archivos desalineados).

#### Sintaxis JavaScript (`node --check`)
Ejecutado sobre todos los archivos `.js` de `src/qagent/frontend`:
- `src/qagent/frontend/componentes/vista-previa/vista-previa.js` -> OK
- `src/qagent/frontend/js/estado.js` -> OK
- Resto de archivos `.js` -> OK (100% sintaxis vÃƒÂ¡lida)

#### VerificaciÃƒÂ³n de Espacios en Blanco Git (`git diff --check`)
- **Resultado:** Salida limpia, sin errores de indentaciÃƒÂ³n ni caracteres espurios.

---

### 2.2. Suite Frontend (`pytest tests/frontend -q`)

```powershell
$env:QAGENT_FAKE_LLM = "1"
python -m pytest tests/frontend -q
```

**Resultado:**
```text
........................................................................ [ 38%]
........................................................................ [ 77%]
...........................................                              [100%]
187 passed in 1.50s
```
- **Referencia anterior:** 179 passed.
- **Diferencia:** +8 pruebas aprobadas (incorporadas en `tests/frontend/test_issue_92_fix_general.py`).

---

### 2.3. Suite RÃƒÂ¡pida del Sistema (`python test.py --rapido`)

```powershell
$env:QAGENT_FAKE_LLM = "1"
python test.py --rapido
```

**Resultado:**
```text
=== Pruebas (pytest) ===
$ python -m pytest -q -m "not docker and not red"
........................................................................ [  5%]
...
1322 passed, 25 deselected in 40.43s
--- Pruebas (pytest): OK (41.1 s)

=== Resumen ===
  OK     Pruebas (pytest)
```
- **Referencia anterior:** 1314 passed, 25 deselected.
- **Diferencia:** +8 pruebas aprobadas correspondientes a la regresiÃƒÂ³n de la Issue #92.

---

### 2.4. Suite Completa Oficial (`python test.py`)

```powershell
$env:QAGENT_FAKE_LLM = "1"
python test.py
```

**Resultado:**
```text
=== Lint (ruff check) ===
All checks passed!
--- Lint (ruff check): OK (2.0 s)

=== Formato (ruff format --check) ===
202 files already formatted
--- Formato (ruff format --check): OK (0.1 s)

=== Pruebas (pytest) ===
1347 passed in 197.31s (0:03:17)
--- Pruebas (pytest): OK (198.2 s)

=== Resumen ===
  OK     Lint (ruff check)
  OK     Formato (ruff format --check)
  OK     Pruebas (pytest)
```
- **Total de pruebas aprobadas:** 1347 pasadas.
- **Llamadas a LLM reales:** 0 (garantizado por `QAGENT_FAKE_LLM=1`).

---

### 2.5. ValidaciÃ³n Visual y MÃ©tricas DOM (Playwright)

Se ejecutÃ³ el arnÃ©s multirresoluciÃ³n automatizado sobre un servidor multihilo `ThreadingServer` sirviendo los ficheros de `src/qagent/frontend/`:

```powershell
python docs/evidencias/issue-92-fix-general/scripts/validar_visual_92.py
```

#### Mediciones Obtenidas por ResoluciÃ³n:

| ResoluciÃ³n | Q92-001 (Desbordamiento) | Q92-002 (Decisiones) | Q92-003 (Ãrbol Head) | Q92-004 (Favicon) |
|---|---|---|---|---|
| **1024Ã—700** | **PASS** (scroll: sl=0, sw=788, cw=788; table: sw=860, cw=738, ox=auto) | **PASS** (7 celdas, valores: `['â€”']`, undefined: false) | **PASS** (sw=738, cw=738) | **PASS** (href=svg, HTTP 200, 404=false) |
| **1280Ã—720** | **PASS** (scroll: sl=0, sw=1044, cw=1044; table: sw=860, cw=678, ox=auto) | **PASS** (7 celdas, valores: `['â€”']`, undefined: false) | **PASS** (sw=298, cw=298) | **PASS** (href=svg, HTTP 200, 404=false) |
| **1366Ã—768** | **PASS** (scroll: sl=0, sw=1130, cw=1130; table: sw=860, cw=764, ox=auto) | **PASS** (7 celdas, valores: `['â€”']`, undefined: false) | **PASS** (sw=298, cw=298) | **PASS** (href=svg, HTTP 200, 404=false) |
| **1440Ã—900** | **PASS** (scroll: sl=0, sw=1204, cw=1204; table: sw=860, cw=838, ox=auto) | **PASS** (7 celdas, valores: `['â€”']`, undefined: false) | **PASS** (sw=298, cw=298) | **PASS** (href=svg, HTTP 200, 404=false) |
| **1920Ã—1080** | **PASS** (scroll: sl=0, sw=1684, cw=1684; table: sw=1318, cw=1318, ox=auto) | **PASS** (7 celdas, valores: `['â€”']`, undefined: false) | **PASS** (sw=298, cw=298) | **PASS** (href=svg, HTTP 200, 404=false) |

#### Capturas de Pantalla Generadas:
- `img/despues/funciones-1024x700.png`
- `img/despues/endpoints-1024x700.png`
- `img/despues/vista-1024x700.png` (reemplaza la captura corrupta de Codex)
- `img/despues/funciones-1280x720.png`
- `img/despues/endpoints-1280x720.png`
- `img/despues/funciones-1366x768.png`
- `img/despues/endpoints-1366x768.png`
- `img/despues/funciones-1440x900.png`
- `img/despues/endpoints-1440x900.png`
- `img/despues/funciones-1920x1080.png`
- `img/despues/endpoints-1920x1080.png`

---

### 2.6. VerificaciÃ³n Posterior al Merge de Develop

Tras integrar `origin/develop` (commit de merge `31afd53`), se repitieron todas las suites:
- **Suite especÃ­fica Issue #92 (`test_issue_92_fix_general.py`):** 8 passed in 1.01s.
- **Suite frontend (`pytest tests/frontend -q`):** 192 passed in 2.73s (+5 pruebas agregadas por develop en `test_recientes_y_modulos.py`).
- **Suite rÃ¡pida (`python test.py --rapido`):** 1331 passed, 25 deselected in 37.15s.
- **Suite completa (`python test.py`):** 1356 passed in 201.42s (0:03:21).
  - Ruff check: All checks passed!
  - Ruff format: 204 files already formatted.
- **ValidaciÃ³n visual Playwright post-merge (`validar_visual_92.py`):** ValidaciÃ³n visual: OK en los 5 viewports sin desbordamientos ni regresiones.

---

## 3. Estado Ambiental y Limitaciones

1. **Docker Desktop:**
   - El daemon de Docker no se encuentra en ejecuciÃ³n en el entorno local de desarrollo.
   - 23 casos marcados con `@pytest.mark.docker` son excluidos/omitidos automÃ¡ticamente por pytest de manera controlada.
2. **pywebview nativo:**
   - La validaciÃ³n visual se efectuÃ³ con el motor Chromium/Playwright sobre los mismos activos estÃ¡ticos HTML/CSS/JS que carga pywebview.
   - Se proveen instrucciones de verificaciÃ³n manual en Windows para abrir la ventana nativa mediante `qagent` o `python -m qagent`.
