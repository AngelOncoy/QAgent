# Bitácora de pruebas — issue #67

Fecha de la validación final: 2026-10-16 (America/Lima).

## Entorno

| Componente | Versión o valor |
|---|---|
| Sistema operativo | Microsoft Windows NT 10.0.26300.0 |
| Python | 3.14.7 |
| pytest | 9.1.1 |
| Ruff | 0.17.1 |
| Node.js | v24.20.0 |
| Rama | `feat/sprint1-tipos-pruebas-qagent` |
| HEAD | `b8fac9292e267d7cb2d4e7acc2b466bdc62c221b` |
| IA | `QAGENT_FAKE_LLM=1` |

No se ejecutaron Docker, pruebas marcadas `docker` o `red`, ni solicitudes reales a
proveedores LLM.

## Fase 2 — resultados históricos

Estos datos proceden de la ejecución realizada durante la Fase 2. No se presentan
como una nueva ejecución:

- Matriz focalizada: 163 aprobadas.
- Suite rápida: 1.076 aprobadas y 19 excluidas.

## Fase 3 — resultados históricos

Estos datos proceden de la ejecución realizada durante la Fase 3. No se presentan
como una nueva ejecución:

- Proveedores y roles: 111 aprobadas.
- Matriz focalizada: 369 aprobadas y 1 excluida.
- Suite rápida: 1.086 aprobadas y 19 excluidas.

## Fase 4 — resultados nuevos

Las suites se superponen; sus cantidades se informan separadamente y no deben
sumarse.

| Validación | Comando | Resultado | Duración pytest |
|---|---|---|---:|
| Matriz focalizada | `python -m pytest -q tests/pruebas tests/frontend/test_sprint1_tipos_prueba.py tests/frontend/test_fase2_seleccion_clonado.py tests/agents/test_planner.py tests/agents/test_planner_endpoints.py tests/agents/test_generator.py tests/agents/test_reviewer.py tests/agents/test_reviewer_ejecucion.py tests/agents/test_reviewer_endpoints.py tests/orchestrator/test_corrida.py tests/orchestrator/test_hu24_reutilizar_specs.py tests/orchestrator/test_hu25_regresion.py tests/storage/test_registro.py tests/storage/test_vista_ejecucion.py tests/storage/test_vista_reporte.py tests/almacenamiento/test_proyecto.py tests/config/test_roles.py tests/llm/test_cliente_real.py tests/llm/test_fabrica.py tests/llm/test_fake_llm.py tests/llm/test_precios.py tests/llm/test_proveedores.py tests/llm/test_integracion_roles_issue67.py tests/app/test_desktop_corrida.py -m "not docker and not red"` | 360 aprobadas, 0 fallidas, 0 excluidas | 10,61 s |
| Frontend | `python -m pytest -q tests/frontend -m "not docker and not red"` | 90 aprobadas, 0 fallidas, 0 excluidas | 1,14 s |
| Suite rápida oficial | `python test.py --rapido` | 1.086 aprobadas, 0 fallidas, 19 excluidas | 26,21 s |
| Ruff lint | `python -m ruff check src tests scripts test.py` | Sin incidencias | — |
| Ruff formato | `python -m ruff format --check src tests scripts test.py` | 176 archivos ya formateados | — |
| Sintaxis JavaScript | `node --check` sobre los 22 archivos `*.js` de `src/qagent/frontend` | 22 válidos, 0 fallidos | — |
| Whitespace | `git diff --check` | Exit code 0; solo aviso informativo LF/CRLF de Git | — |
| Secretos | Escaneo local de patrones sobre los 41 archivos cambiados o nuevos | 0 coincidencias; 0 archivos `.env` cambiados | — |

La matriz focalizada comenzó a las 21:10:31, el frontend a las 21:10:46 y la suite
rápida a las 21:10:51, hora local UTC-05:00.

## Cobertura funcional observada

- Estrategias escalares `unitaria`, `limites`, `humo` y `regresion`.
- Política de límites basada en metadatos estáticos y política de humo de un único
  caso nominal verificable por objetivo.
- Regresión con reutilización de aprobadas, huellas AST, rutas resueltas de
  `APIRouter`, filtro de objetivos y cero clientes LLM.
- Rechazo de valores desconocidos y listas.
- Propagación, persistencia, vistas y compatibilidad de registros históricos.
- Roles independientes, clientes simulados, proveedores y clasificación de errores.
- Compatibilidad de las pruebas frontend existentes, incluida la issue #63.

## Exclusiones y limitaciones

- Las 19 exclusiones de la suite rápida corresponden a pruebas marcadas para Docker
  o red por el comando oficial `--rapido`.
- No se validó una ejecución real en sandbox porque la fase prohíbe ejecutar Docker.
- No se probaron cuentas ni APIs reales; los resultados LLM son simulados.
- Las pruebas frontend validan estructura y cableado. No sustituyen una sesión
  visual interactiva de pywebview.
- No hubo control interactivo de escritorio para producir capturas auténticas.

## Evidencias relacionadas

- `informe-issue-67-sprint1-tipos-pruebas.md`
- `validacion-apis.md`
- `evidencias_sha256.json`
- `img/README.md`

## Estado final

Todas las comprobaciones automatizadas autorizadas terminaron correctamente. Los
niveles pendientes son la validación visual interactiva, la ejecución real en
sandbox y la conexión real a proveedores; ninguno fue simulado como evidencia real.
