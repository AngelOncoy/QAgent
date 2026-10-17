# QAgent — Informe técnico definitivo

| Campo | Valor |
|---|---|
| Proyecto | QAgent |
| Issue | #67 — Validar tipos de pruebas del Sprint 1 e integración de APIs de IA |
| Sprint | Sprint 1 |
| Rama | `feat/sprint1-tipos-pruebas-qagent` |
| Commit base / HEAD validado | `b8fac9292e267d7cb2d4e7acc2b466bdc62c221b` |
| Fecha | 2026-10-16 |
| Estado | Validación automatizada aprobada; validación visual, sandbox real y APIs reales pendientes |

## 1. Resumen ejecutivo

La issue #67 incorpora un modelo escalar con cuatro estrategias de prueba:
`unitaria`, `limites`, `humo` y `regresion`. La estrategia se selecciona de forma
exclusiva, se valida en el backend, llega al orquestador y queda persistida en las
salidas de la corrida. Planner aplica políticas distintas para unitarias, límites y
humo; regresión toma una ruta independiente que reutiliza pruebas aprobadas sin crear
clientes LLM.

La validación de Fase 4 produjo 360 pruebas focalizadas aprobadas, 90 pruebas de
frontend aprobadas y 1.086 pruebas aprobadas con 19 excluidas en la suite rápida
oficial. Ruff, formato, sintaxis JavaScript, whitespace y el control de secretos
también finalizaron sin errores. Todas las llamadas LLM fueron simuladas mediante
`QAGENT_FAKE_LLM=1`.

No se ejecutaron Docker ni proveedores reales. El entorno tampoco permitió controlar
interactivamente el escritorio; por eso existen cero capturas auténticas y el
manifiesto SHA-256 permanece vacío. Estos puntos se declaran pendientes y no se
presentan como validados.

## 2. Introducción y contexto del problema

Antes de este trabajo, el flujo principal estaba orientado a pruebas unitarias y
usaba perfiles históricos para algunos comportamientos. La issue exige hacer
explícitos los cuatro tipos del Sprint 1, impedir la selección múltiple, mantener la
selección de objetivos AST, aplicar una política real por estrategia y conservar la
compatibilidad con registros existentes.

Además, la solución debía comprobar la configuración independiente de Planner,
Generator y Reviewer con Gemini, OpenRouter y Groq, respectivamente, sin introducir
dependencias nuevas ni usar credenciales reales. La Fase 3 detectó y corrigió dos
defectos concretos del manejo LLM: HTTP 403 no se distinguía adecuadamente de una
credencial inválida y se perdían propiedades del subtipo `ErrorLLM` al propagar
determinados errores.

## 3. Objetivos generales y específicos

El objetivo general fue validar un flujo coherente y auditable para los cuatro tipos
de prueba del Sprint 1.

Objetivos específicos:

- representar la estrategia como un único valor canónico;
- rechazar valores desconocidos, vacíos, nulos y colecciones;
- especializar la planificación de unitarias, límites y humo sin inventar oráculos;
- ejecutar regresión a partir de una línea base aprobada y sin LLM;
- conservar objetivos seleccionados y rutas completas de endpoints;
- persistir y presentar la estrategia en corrida, historial, ejecución e informe;
- leer registros anteriores mediante una política determinista;
- validar roles y proveedores con transportes locales y clientes falsos;
- mantener las funcionalidades previas, incluida la issue #63;
- producir resultados repetibles y separar claramente simulación de ejecución real.

## 4. Alcance funcional del Sprint 1

El alcance incluye pruebas unitarias de funciones Python, casos límite sustentados
por firmas, docstrings y metadatos AST, humo con un único caso feliz verificable por
objetivo, y regresión de pruebas ya aprobadas. Para endpoints FastAPI se usan sus
declaraciones estáticas y las rutas resueltas, incluidas composiciones con
`APIRouter`.

Quedan fuera de esta fase la selección simultánea de estrategias del Sprint 2, una
refactorización transversal de telemetría, el uso de código o datos privados, la
ejecución Docker no autorizada y las solicitudes reales a Gemini, OpenRouter o Groq.

Se distinguen tres niveles: nivel 1, pruebas unitarias y mocks, completado; nivel 2,
aplicación real con FakeLLMClient, cubierto en lógica y cableado pero pendiente de una
sesión visual interactiva; nivel 3, sandbox y APIs reales, pendiente por restricción
expresa.

## 5. Arquitectura de QAgent

QAgent mantiene responsabilidades separadas. El frontend pywebview conserva el
estado y envía una estrategia escalar al puente de escritorio. El backend la valida
con `qagent.pruebas.tipos`, el orquestador decide la ruta y los agentes se comunican
exclusivamente mediante contratos JSON.

En las estrategias generativas, Planner recibe la estrategia y construye contratos,
Generator produce pytest desde esos contratos y Reviewer valida y ejecuta mediante
la abstracción de sandbox. En regresión, el orquestador evita Planner, Generator y
Reviewer, localiza pruebas aprobadas, compara huellas y ejecuta solo los objetivos
seleccionados mediante la ruta específica.

`AlmacenProyecto` y `storage/registro.py` escriben `run.json`, `log.json` y
`results.json`. Las vistas de almacenamiento normalizan registros históricos antes
de exponerlos al frontend. La fábrica LLM crea clientes por rol a partir de la
configuración; con `QAGENT_FAKE_LLM=1` usa `FakeLLMClient` sin leer claves.

## 6. Auditoría inicial y problemas identificados

La auditoría inicial identificó que el concepto de tipo estaba parcialmente mezclado
con perfiles y no existía una fuente canónica única para las cuatro estrategias. La
interfaz no expresaba el requisito del Sprint 1 como selección exclusiva y el tipo no
se propagaba ni persistía de extremo a extremo.

También faltaban políticas específicas para límites y humo. La ruta de regresión
necesitaba respetar la selección, resolver rutas completas de endpoints y demostrar
que no consume LLM. Los registros históricos carecían del nuevo campo, por lo que se
requería una migración de lectura sin reescribir datos.

En la integración LLM se comprobó que la configuración por rol ya era una base válida.
Los defectos reproducibles encontrados fueron la clasificación de 403 y la pérdida de
tipo, código o detalle de `ErrorLLM` en una propagación. Las correcciones quedaron
cubiertas por pruebas simuladas. No se detectó ningún defecto nuevo en la Fase 4.

## 7. Diseño del nuevo modelo de estrategias

`src/qagent/pruebas/tipos.py` define las constantes y la tupla ordenada
`ESTRATEGIAS_PRUEBA`. `validar_estrategia()` acepta exclusivamente una cadena
perteneciente a esa tupla y lanza `EstrategiaInvalida` para entradas inválidas. Esto
impide que listas como `['humo', 'regresion']` activen selección múltiple.

`estrategia_historica()` aplica la política de compatibilidad solo al leer entradas
antiguas: perfil `reg` se interpreta como `regresion`, perfil `humo` como `humo` y
cualquier otro registro sin campo como `unitaria`. Un valor explícito siempre tiene
prioridad y debe ser válido.

El diseño evita cambiar `planner_contract.v2`: la estrategia gobierna cómo se
construye el contrato, pero no rompe su esquema. Esto conserva consumidores y pruebas
existentes.

## 8. Implementación de pruebas unitarias

`unitaria` mantiene el comportamiento de cobertura funcional existente. Planner
recibe explícitamente la estrategia y diseña casos sustentados por firma, tipos y
docstring. Generator opera sobre el contrato validado, y Reviewer conserva sus
controles de aserciones, ejecución y reintentos del orquestador.

La reutilización de especificaciones existente se limita a la estrategia unitaria,
evitando que una planificación creada para otra política se emplee implícitamente.
Los tests de agentes y orquestador comprueban propagación, contratos y resultados sin
ejecutar código de usuario fuera del sandbox.

## 9. Implementación de valores límite y casos borde

`limites` añade al prompt del Planner una política que exige basarse en restricciones
observables. Las funciones usan anotaciones, parámetros, valores predeterminados y
docstrings. Los endpoints incorporan metadatos FastAPI/Pydantic disponibles en el
análisis estático.

Los tests cubren límites explícitos, mínimos, máximos y entradas inválidas cuando
existe sustento. La política prohíbe deducir resultados esperados mediante ejecución
y evita convertir una suposición en oráculo. Cuando no hay una restricción verificable
no se inventa un caso límite.

Esta validación es de nivel 1: demuestra la política y los contratos con entradas
sintéticas. No afirma haber ejecutado un proyecto real en Docker.

## 10. Implementación de pruebas de humo

`humo` no es una simple etiqueta de interfaz. Planner limita la salida a un máximo de
un caso nominal verificable por objetivo y elimina casos redundantes. El orquestador
conserva la selección de funciones y endpoints, de modo que no se incorporan
objetivos ajenos.

Las pruebas automatizadas demuestran que la política difiere de `unitaria`, que solo
se conserva el caso feliz y que el tipo llega a almacenamiento. La ejecución real en
sandbox permanece pendiente porque Docker fue excluido explícitamente; por ello, la
política backend está cumplida en nivel 1, pero el recorrido real de nivel 3 no se
declara aprobado.

## 11. Implementación de pruebas de regresión

`regresion` toma una ruta de orquestación independiente. Reutiliza pruebas aprobadas,
calcula y compara huellas SHA-256 de representaciones AST, conserva los objetivos
seleccionados y trata metadatos ausentes o corruptos como estados explícitos. Las
rutas de endpoints incluyen prefijos resueltos de `APIRouter` e `include_router`.

La ruta no crea clientes Planner, Generator ni Reviewer. El `TokenTracker` asociado
queda con cero solicitudes simuladas porque no hubo invocaciones LLM, no porque una
API real haya demostrado consumo cero. Cuando no existe una línea base se informa el
motivo y no se fabrica una corrida histórica.

Las pruebas de regresión verifican filtrado, huellas, rutas completas, ausencia de
clientes y persistencia. La ejecución efectiva de pytest dentro de Docker sigue
pendiente de autorización.

## 12. Selección única, frontend y backend

El estado frontend contiene exactamente cuatro opciones y un único valor
`testStrategy`, inicialmente `unitaria`. El componente usa controles `radio` con el
mismo nombre, actualiza una sola clave y conserva la selección de objetivos AST al
navegar. El monitor envía el valor escalar a `start_run`.

El puente de escritorio valida antes de iniciar la corrida y no acepta listas ni
valores desconocidos. La estrategia queda presente en el estado de ejecución. Las
vistas Historial, Ejecución e Informe muestran el valor normalizado.

Las 90 pruebas frontend validan estructura, estilos, cableado y compatibilidad, pero
no sustituyen una interacción visual de pywebview. Las capturas que demostrarán el
comportamiento gráfico siguen pendientes.

## 13. Integración de Planner, Generator y Reviewer

La matriz simulada verifica configuración independiente por rol: Planner con Gemini
`gemini-3.8-flash`, Generator con OpenRouter
`google/gemma-4-31b-it:free` y Reviewer con Groq `openai/gpt-oss-20b`. Un transporte
local valida proveedor, modelo, endpoint y variable de entorno esperada sin efectuar
tráfico externo. `FakeLLMClient` funciona para los tres roles sin claves.

Se probaron HTTP 401, 403, 404, 429, 402 y 503, timeout, fallo de red, respuesta vacía,
JSON inválido, credencial ausente, agotamiento de reintentos, redacción de
credenciales y ausencia de `usage`. Los subtipos de `ErrorLLM` conservan tipo, código
y detalle. No existe fallback silencioso a otro proveedor.

`TokenTracker` registra rol, modelo, tokens de entrada y salida, solicitudes, costo
estimado, objetivo, intento, hora e indicador simulado. `results.json` incluye además
proveedor, modelo y precios configurados. Los ceros de FakeLLM son métricas simuladas;
si una respuesta real omite `usage`, cero significa dato no disponible, no consumo
comprobado.

## 14. Validación automatizada y resultados

Resultados nuevos de Fase 4, todos con `QAGENT_FAKE_LLM=1`:

| Suite o control | Resultado |
|---|---|
| Matriz focalizada | 360 aprobadas, 0 fallidas, 0 excluidas, 10,61 s |
| Frontend | 90 aprobadas, 0 fallidas, 0 excluidas, 1,14 s |
| `python test.py --rapido` | 1.086 aprobadas, 0 fallidas, 19 excluidas, 26,21 s |
| Ruff lint | Sin incidencias |
| Ruff formato | 176 archivos ya formateados |
| JavaScript | 22 archivos válidos, 0 fallidos |
| `git diff --check` | Exit code 0; aviso LF/CRLF no bloqueante |
| Escaneo de secretos | 41 archivos, 0 patrones sensibles, 0 `.env` modificados |

Las suites se superponen y no se suman. Los comandos completos, entorno y resultados
históricos de Fases 2 y 3 están en `pruebas_ejecutadas.md`.

## 15. Problemas encontrados, limitaciones y soluciones

Durante Fase 3 se corrigieron la clasificación de HTTP 403 como acceso denegado y la
preservación de propiedades de `ErrorLLM`. No surgieron fallos nuevos durante Fase 4,
por lo que no se modificó código ni tests.

Limitaciones conocidas:

- no hay latencia individual por llamada LLM;
- los reintentos HTTP y las llamadas fallidas no se persisten en `TokenTracker`;
- `usage` ausente puede ser indistinguible de consumo real cero;
- el costo es una estimación basada en configuración, no una factura;
- el pipeline normal no fija todavía un máximo explícito de salida para llamadas
  reales;
- no se ejecutó Docker ni se verificaron cuentas, cuotas o elegibilidad regional;
- no hubo control interactivo de escritorio, por lo que no se obtuvieron capturas.

La solución en esta fase fue documentar cada límite, mantener los niveles pendientes
y evitar una refactorización de telemetría fuera de alcance. El aviso Git de que un
archivo podría convertirse de LF a CRLF no representa un error de whitespace y no se
alteraron finales de línea.

## 16. Conclusiones y recomendaciones

La implementación de nivel 1 satisface el modelo escalar, las políticas diferenciadas,
la ruta de regresión sin LLM, la persistencia, la lectura histórica y la integración
simulada de roles. La suite completa autorizada no mostró regresiones y los controles
de calidad y seguridad finalizaron limpios.

Antes de staging y commit se recomienda completar una sesión visual con
`QAGENT_FAKE_LLM=1`, incorporar solo capturas auténticas y actualizar sus hashes. Si
el criterio de aceptación exige ejecución real, se debe pedir autorización separada
para Docker. Las APIs reales deben seguir pendientes hasta definir límites de salida,
revalidar cuotas y obtener autorización expresa. Después conviene revisar el diff,
forzar únicamente la adición de la carpeta ignorada de evidencias y mantener fuera
cualquier configuración personal.

## Anexo A — Archivos de implementación conservados

Archivos nuevos:

- `src/qagent/pruebas/__init__.py`
- `src/qagent/pruebas/tipos.py`

Archivos modificados: `agents/planner.py`, `almacenamiento/historial.py`,
`almacenamiento/proyecto.py`, `app/desktop.py`, `contracts/run_log.schema.json`, los
componentes frontend de configuración, ejecución, historial, informe, monitor y vista
previa, `frontend/js/estado.js`, `llm/cliente.py`, `llm/proveedores.py`,
`orchestrator/corrida.py`, `orchestrator/regresion.py`, `storage/registro.py`,
`storage/vista_ejecucion.py` y `storage/vista_reporte.py`, todos bajo `src/qagent/`.

La Fase 4 no modificó ninguno de estos archivos.

## Anexo B — Tests relacionados

Se añadieron `tests/pruebas/test_tipos.py`,
`tests/frontend/test_sprint1_tipos_prueba.py` y
`tests/llm/test_integracion_roles_issue67.py`, junto con sus paquetes cuando aplica.
También se ampliaron pruebas de agentes, almacenamiento, app, configuración,
frontend, LLM, orquestador y storage. La lista y los comandos exactos están en la
bitácora.

## Anexo C — Matriz de aceptación

| Requisito | Estado | Archivo o función responsable | Test | Evidencia | Observaciones |
|---|---|---|---|---|---|
| Cuatro tipos escalares | CUMPLIDO | `pruebas/tipos.py` | `tests/pruebas/test_tipos.py` | Matriz focalizada | Orden y valores exactos comprobados. |
| Unitarias | CUMPLIDO | `agents/planner.py`, `orchestrator/corrida.py` | Tests de Planner y corrida | 360 aprobadas | Nivel 1 con FakeLLM. |
| Valores límite | CUMPLIDO | Política de límites de Planner | Tests de Planner y endpoints | 360 aprobadas | Casos sustentados por metadatos estáticos. |
| Humo | CUMPLIDO | Política de humo de Planner | Tests de Planner y corrida | 360 aprobadas | Un caso feliz máximo; sandbox real pendiente aparte. |
| Regresión sin LLM | CUMPLIDO | `orchestrator/regresion.py` | `test_hu25_regresion.py` | 360 aprobadas | Reutiliza aprobadas; cero clientes LLM. |
| Rutas completas de endpoints | CUMPLIDO | Huellas y análisis de regresión | Tests de regresión y Planner endpoints | 360 aprobadas | Incluye prefijos `APIRouter`. |
| Selección única | CUMPLIDO | `estado.js`, `config-pruebas.js` | `test_sprint1_tipos_prueba.py` | 90 frontend | Radio y valor escalar; evidencia visual pendiente. |
| Validación backend | CUMPLIDO | `validar_estrategia()` y `desktop.py` | Tests de tipos y desktop | 360 aprobadas | Rechaza desconocidos y listas. |
| Propagación frontend/backend | CUMPLIDO | Monitor, desktop y corrida | Tests frontend, desktop y corrida | 360/90 aprobadas | Verificada por cableado y comportamiento aislado. |
| Persistencia | CUMPLIDO | Proyecto y registro | Tests de proyecto y storage | 360 aprobadas | `run.json`, `log.json` y `results.json`. |
| Vistas Historial/Ejecución/Informe | CUMPLIDO | Vistas storage y componentes frontend | Tests storage/frontend | 360/90 aprobadas | Valor normalizado expuesto. |
| Compatibilidad histórica | CUMPLIDO | `estrategia_historica()` | Tests de tipos, proyecto y vistas | 360 aprobadas | `reg`, `humo` y valor por defecto. |
| Contrato `planner_contract.v2` | CUMPLIDO | Planner y schemas existentes | Tests de agentes/contratos incluidos en suite rápida | 1.086 aprobadas | Sin ruptura del schema. |
| Integración de tres roles | CUMPLIDO | Fábrica y proveedores LLM | `test_integracion_roles_issue67.py` | Matriz focalizada | Transporte local; no conexión real. |
| Manejo de errores LLM | CUMPLIDO | `llm/cliente.py`, `llm/proveedores.py` | Tests de cliente/proveedores | Matriz focalizada | Casos HTTP y transporte simulados. |
| Registro de métricas | PARCIAL | `llm/tracker.py`, `storage/registro.py` | Tests de tracker/storage en suite | Bitácora y validación API | Faltan latencia, fallos y reintentos HTTP persistidos. |
| Pruebas simuladas | CUMPLIDO | `FakeLLMClient` | Suites Fase 4 | Bitácora | `QAGENT_FAKE_LLM=1`. |
| Aplicación visual interactiva | PENDIENTE | Frontend pywebview | No ejecutada | `img/README.md` | Sin control interactivo del escritorio. |
| Sandbox real | PENDIENTE | Sandbox Docker | Excluida | 19 deselected | Docker no autorizado. |
| APIs reales | PENDIENTE | Clientes LLM reales | No ejecutada | `validacion-apis.md` | Requiere autorización, claves y control de cuota. |
| Compatibilidad issue #63 | CUMPLIDO | Frontend y desktop existentes | `test_fase2_seleccion_clonado.py` y suite rápida | 1.086 aprobadas | Sin regresiones automatizadas. |

## Anexo D — Evidencias visuales

Cantidad de capturas auténticas incorporadas: **0**. CAP-01 a CAP-10 están
pendientes. `img/README.md` describe cada toma y el procedimiento seguro. El
manifiesto `evidencias_sha256.json` contiene una lista vacía y ningún hash inventado.

## Anexo E — Compatibilidad histórica

Los registros no se reescriben. Al leerlos, perfil `reg` se normaliza a `regresion`,
perfil `humo` a `humo`, y cualquier otro perfil antiguo sin campo a `unitaria`. Si
`estrategia_prueba` existe, prevalece después de validarse. Esta política se aplica a
historial y vistas de ejecución e informe.

## Anexo F — Referencias y validación real pendiente

- Bitácora local: `pruebas_ejecutadas.md`.
- Validación simulada, fuentes oficiales y procedimiento real:
  `validacion-apis.md`.
- Gemini: <https://ai.google.dev/gemini-api/docs/openai>.
- OpenRouter: <https://openrouter.ai/docs/api_reference/limits>.
- Groq: <https://console.groq.com/docs/openai>.

La validación real debe comenzar, tras autorización, con una comprobación mínima por
rol y un proyecto sintético. Se deben registrar los contadores de las consolas antes
y después, detenerse ante cualquier indicio de facturación o falta de cuota y no
confundir la estimación local con consumo facturado.
