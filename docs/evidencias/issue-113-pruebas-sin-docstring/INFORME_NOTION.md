# Issue #113 — Pruebas para funciones sin docstring

- **Responsable:** equipo QAgent
- **Issue:** https://github.com/AngelOncoy/QAgent/issues/113
- **Rama:** `fix/issue-113-pruebas-sin-docstring`
- **Estado del Pull Request:** no creado

## Problema original

Observamos que el Planner podía recibir una función sin docstring y aceptar casos que
decían provenir de esa documentación inexistente. En `get_siamese_model`, los casos de
device intentaban fijar como esperado un objeto de modelo que no podía deducirse de la
firma ni de tipos declarados.

## Objetivo

Buscamos permitir pruebas sin docstring cuando existiera una propiedad verificable y,
cuando no existiera, informar la limitación sin inventar resultados ni debilitar las
aserciones.

## Qué investigamos

Revisamos el analizador AST, Planner, schema v2, Generator, Reviewer, orquestador,
reintentos y detección de Assertion Laundering. Confirmamos que el analizador sí
conservaba funciones sin docstring. El problema estaba en que el schema validaba el
nombre de la procedencia, pero no comprobaba que esa procedencia existiera.

## Qué decidimos implementar y por qué

Implementamos una validación semántica antes de formar el contrato. Comprobamos que una
docstring exista, que los casos de tipo tengan anotaciones y que la firma solo se use
para errores de invocación demostrables. También verificamos exactamente retornos
`None` y `Literal` únicos. Conservamos el schema para no romper datos históricos.

## Dificultades y solución

No encontramos APP-RF en el equipo. Resolvimos la validación con un fixture sintético
seguro que reprodujo la firma y los tres devices reportados, sin cargar modelos ni usar
CUDA. También encontramos una mejora previa que ya omitía objetivos sin oráculo;
extendimos ese mecanismo en vez de duplicarlo.

## Archivos modificados

- `src/qagent/agents/planner.py`
- `tests/agents/test_issue113_sin_docstring.py`
- Evidencias e informes locales de esta carpeta

## Pruebas ejecutadas y resultados

- Antes: 7 fallidas y 6 aprobadas en la reproducción.
- Tests específicos finales: 20 aprobadas.
- Regresión focalizada: 129 aprobadas.
- Suite rápida: 1454 aprobadas y 25 excluidas.
- Suite completa: 1456 aprobadas y 23 omitidas.
- Ruff check y formato: aprobados.

Usamos `QAGENT_FAKE_LLM=1`; no hicimos llamadas reales a IA.

## Evidencias

- [Reproducción previa](reproduccion-antes.txt)
- [Resultados finales](resultados-despues.txt)
- [Bitácora](bitacora-pruebas.md)
- [Matriz de criterios](matriz-criterios.md)
- [Informe técnico](informe-issue-113.md)

## Conclusiones

Corregimos la aceptación de procedencias inexistentes y mantuvimos el contrato v2, el
flujo completo y Assertion Laundering. Las funciones sin docstring ahora se prueban solo
si existe evidencia suficiente; las demás quedan omitidas con un motivo comprensible.

## Pendientes

- Repetir la validación controlada cuando APP-RF esté disponible.
- Evaluar en otra issue si el contrato debe incorporar una procedencia AST para
  retornos constantes u operaciones deterministas del cuerpo.
- Crear commit, push y Pull Request después de la revisión humana.
