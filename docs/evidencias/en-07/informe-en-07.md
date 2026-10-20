# EN-07 · Almacenamiento del proyecto (.pyagent/)

**Informe técnico de implementación y evidencia** · Octubre de 2026 · Responsables: Adrián Olaf Sánchez Vargas, Mateo Salvador Vincenzo Castillo Pezo

---

## 1. En pocas palabras

El habilitador técnico **EN-07** establece la arquitectura de persistencia local dentro de cada proyecto analizado por QAgent (`<proyecto>/.pyagent/`), así como el registro centralizado de proyectos recientes en el entorno del usuario (`~/.pyagent/recientes.json`).

Esta infraestructura permite guardar de forma persistente y atómica:
1. Las **corridas históricas** (`runs/<run_id>/`) con metadatos de inicio, fin, resumen, trazabilidad de tokens y reportes de auditoría completos (EN-05, HU-18, HU-23).
2. Las **especificaciones (specs)** generadas por el agente Planner (`specs/`), tanto individuales como modulares cacheadas por huella SHA-256 (HU-20, HU-24, HU-25).
3. Las **pruebas aprobadas** por el agente Reviewer en el sandbox Docker (`tests/test_*.py`).
4. El **registro de proyectos recientes** (`recientes.json`) que alimenta la pantalla de bienvenida y apertura de repositorios (HU-01, HU-03).

---

## 2. Arquitectura de Almacenamiento

### 2.1 Estructura en disco dentro del proyecto

```text
<proyecto>/
└── .pyagent/
    ├── .gitignore                 <- Excluye runs/ del repositorio Git
    ├── runs/
    │   └── <run_id>/              <- Carpeta por corrida (AAAAMMDD-HHMMSS-xxxx)
    │       ├── run.json           <- Metadatos de ciclo de vida y estado
    │       ├── log.json           <- Consumo de tokens y costos por agente
    │       ├── results.json       <- Métricas, cobertura y pass rate
    │       └── detalle.json       <- Contratos, código generado y trazas
    ├── specs/
    │   ├── <id>.json              <- Spec unitaria (contrato planner_contract.v2)
    │   └── <modulo>.spec.json     <- Plan modular con huella SHA-256 para HU-24
    └── tests/
        └── test_<id>.py           <- Pruebas pytest aprobadas por el Reviewer
```

### 2.2 Registro de recientes en el Home de usuario

```text
~/.pyagent/
└── recientes.json                 <- Lista ordenada cronológicamente de proyectos
```

---

## 3. Verificación de los Criterios de Aceptación

### CA-01: Estructura `.pyagent/runs/<run_id>/`, `.pyagent/specs/` y `.pyagent/tests/`
- `AlmacenProyecto.inicializar()` asegura la creación idempotente de las carpetas de trabajo y del archivo `.gitignore`.
- Cada corrida nueva genera su propia subcarpeta nombrada con marca temporal y token único (`runs/<run_id>/`).
- Las especificaciones se ubican en `specs/` y las pruebas aprobadas en `tests/`.

### CA-02: Guarda y lee specs, pruebas aprobadas e historial
- La escritura se ejecuta mediante funciones atómicas (`escribir_json_atomico`, `escribir_texto_atomico`), escribiendo primero en un archivo temporal en la misma carpeta antes del reemplazo (`os.replace`), previniendo corrupción de datos en caso de corte de energía o interrupción del proceso.
- La validación es estricta con schemas JSON Schema (`planner_contract.v2.json`, `run_log.schema.json`).
- Toda lectura valida la integridad del contenido antes de exponerlo a la lógica de negocio.

### CA-03: Proyectos recientes en `~/.pyagent/recientes.json`
- `ruta_por_defecto()` apunta a `~/.pyagent/recientes.json`.
- `registrar()` incorpora nuevos proyectos al tope de la lista, evitando duplicados mediante normalización insensible a mayúsculas/minúsculas de rutas en Windows.
- `registrar_corrida()` actualiza la marca temporal de la última corrida asociada a un proyecto.
- `cargar()` maneja con total tolerancia archivos ausentes, ilegibles o corruptos, retornando una lista vacía sin emitir excepciones que rompan la interfaz.

### CA-04: Evidencia de aceptación tras cerrar y reabrir la aplicación
- Se simuló el cierre de la sesión destruyendo los objetos en memoria y abriendo una nueva sesión de la aplicación (`DesktopAPI` y `AlmacenProyecto`).
- Todas las corridas, specs, pruebas aprobadas y proyectos recientes persisten exactamente intactos en el disco y son consumidos por el frontend.

---

## 4. Pruebas Automatizadas

Se implementó una suite dedicada que comprueba de forma exhaustiva los cuatro criterios de aceptación:

| Archivo de Prueba | Cobertura / Criterios | Resultado |
|---|---|---|
| `tests/almacenamiento/test_en07_criterios_aceptacion.py` | CA-01, CA-02, CA-03, CA-04 | **4/4 PASSED** (100%) |
| `tests/almacenamiento/test_proyecto.py` | Métodos de `AlmacenProyecto` | **28/28 PASSED** (100%) |
| `tests/almacenamiento/test_recientes.py` | Operaciones básicas de recientes | **14/14 PASSED** (100%) |
| `tests/almacenamiento/test_recientes_lista.py` | Listado y manipulación de recientes | **18/18 PASSED** (100%) |
| `tests/almacenamiento/test_persistencia.py` | Persistencia y atomicidad en disco | **11/11 PASSED** (100%) |
| `tests/almacenamiento/test_hu24_specs.py` | Reutilización de planes y specs | **8/8 PASSED** (100%) |
