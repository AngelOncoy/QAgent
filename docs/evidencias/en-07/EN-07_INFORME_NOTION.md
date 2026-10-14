# EN-07 · Almacenamiento del proyecto (.pyagent/)

## Ítem del Backlog

| Campo | Valor |
|---|---|
| Habilitador | EN-07 — Almacenamiento del proyecto (.pyagent/) |
| Responsables | ADRIAN OLAF SANCHEZ VARGAS, MATEO SALVADOR VINCENZO CASTILLO PEZO |
| Épica | Épica 8 |
| Sprint | Sprint 1 |
| Status | Terminado (Done) |
| Fecha Inicio | 19 de octubre de 2026 |
| Fecha Fin | 25 de octubre de 2026 |
| Prioridad | Alta |
| Habilita a | HU-03 (Proyectos recientes), HU-20 (Reutilización de specs), HU-23 (Historial de corridas), HU-24 (Planes por módulo y huellas), HU-25 (Modo regresión) |

---

## Resumen del trabajo

**Descripción:** Guardar corridas, specs y pruebas aprobadas dentro del proyecto, para habilitar HU-03, HU-20, HU-23, HU-24 y HU-25.

Se verificó, consolidó y probó formalmente el módulo `src/pyagent/almacenamiento/`:
1. **Estructura dentro del proyecto (`<proyecto>/.pyagent/`):**
   - `runs/<run_id>/`: una subcarpeta por corrida conteniendo `run.json` (metadatos del ciclo de vida), además de `log.json`, `results.json` y `detalle.json` (EN-05).
   - `specs/<id>.json`: contratos del Planner para cada función/endpoint analizado.
   - `specs/<modulo>.spec.json`: planes modulares cacheados con huella criptográfica SHA-256 para reutilización (HU-24).
   - `tests/test_*.py`: repositorio exclusivo de pruebas aprobadas por el Reviewer en el sandbox.
   - `.gitignore`: generado automáticamente para excluir `runs/` del control de versiones mientras se permite versionar specs y tests aprobados.
2. **Persistencia atómica y resiliente:** Todas las escrituras usan reemplazo atómico (`write_atomic` / `tempfile` en la misma carpeta + `replace`) con codificación UTF-8 estricta, previniendo datos corruptos si la aplicación se interrumpe abruptamente.
3. **Registro de proyectos recientes en el entorno del usuario (`~/.pyagent/recientes.json`):** Gestionado de forma centralizada por `pyagent.almacenamiento.recientes`, tolerante a archivos dañados o inexistentes, ordenando por última apertura y conservando la última corrida efectuada.
4. **Verificación de ciclo de vida completo:** Simulación de sesiones cerradas y reiniciadas; tanto `AlmacenProyecto` como el puente pywebview `DesktopAPI` recuperan sin pérdidas el historial de corridas, los reportes detallados, las especificaciones y las pruebas aprobadas.

---

## Criterios de Aceptación

| # | Criterio de Aceptación | Estado | Implementación y verificación |
|---|---|---|---|
| **CA-01** | **Estructura de directorios:** `.pyagent/runs/<run_id>/`, `.pyagent/specs/` y `.pyagent/tests/`. | **Cumplido** | Implementado en `AlmacenProyecto.inicializar()`, `carpeta_run()`, `carpeta_specs` y `carpeta_tests`. Genera `.gitignore` con `runs/`. Verificado en `test_criterio_1_estructura_directorios`. |
| **CA-02** | **Guarda y lee specs, pruebas e historial:** Persistencia de specs vigentes, tests aprobados y `run.json`. | **Cumplido** | Funciones `guardar_run()`, `leer_run()`, `listar_runs()`, `guardar_spec()`, `leer_spec()`, `listar_specs()`, `guardar_prueba_aprobada()`, `leer_prueba_aprobada()` y `listar_pruebas_aprobadas()`. Verificado en `test_criterio_2_guarda_y_lee_specs_pruebas_e_historial`. |
| **CA-03** | **Proyectos recientes en ~/.pyagent/recientes.json:** Formato normalizado y tolerante a fallos. | **Cumplido** | Módulo `pyagent.almacenamiento.recientes` con `ruta_por_defecto() == Path.home() / ".pyagent" / "recientes.json"`, `registrar()`, `cargar()`, `registrar_corrida()`. Verificado en `test_criterio_3_proyectos_recientes_en_home`. |
| **CA-04** | **Evidencia de aceptación tras reinicio:** Corridas, specs y pruebas siguen en `.pyagent/` y recientes en `~/.pyagent/recientes.json`. | **Cumplido** | Simulación de cierre total (destrucción de objetos en memoria) y reapertura (nueva sesión de `AlmacenProyecto` y `DesktopAPI`). Historial, reportes, specs y tests recuperados al 100%. Verificado en `test_criterio_4_evidencia_persistencia_tras_reinicio_sesion`. |

> **Nota técnica de convención de nombres:** Conforme a las reglas del repositorio (`AGENTS.md`), los nombres técnicos fijos del motor (`.pyagent/`, `~/.pyagent/recientes.json`, `pyagent-sandbox:base`) se mantienen consistentes a nivel de sistema de archivos para garantizar retrocompatibilidad e interoperabilidad.

---

## Pruebas Realizadas

```bash
# Pruebas expresas de criterios de aceptación de EN-07:
pytest tests/almacenamiento/test_en07_criterios_aceptacion.py -v

# Suite completa de almacenamiento (83 pruebas):
pytest tests/almacenamiento/ -v

# Suite rápida del proyecto (sin docker/red):
python test.py --rapido
```

### Resultados de Ejecución
- `tests/almacenamiento/test_en07_criterios_aceptacion.py`: **4 passed** (100% de criterios de aceptación verificados).
- `tests/almacenamiento/`: **83 passed** (todas las pruebas del módulo de almacenamiento exitosas).
- `test.py --rapido`: **904 passed** (0 fallos, 0 advertencias de linting/formato).
