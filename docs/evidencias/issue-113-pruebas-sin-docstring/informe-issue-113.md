# QAgent — Informe técnico de la issue #113

- **Título:** Permitir pruebas para funciones sin docstring sin invalidar el contrato del Planner
- **Fecha:** 20 de octubre de 2026
- **Rama:** `fix/issue-113-pruebas-sin-docstring`
- **Issue:** [#113](https://github.com/AngelOncoy/QAgent/issues/113)
- **Base:** `origin/develop` en `23a0d1b6010dc06f59fdd7c96a4e46fe5dc36a3b`

## 1. Resumen ejecutivo

Corregimos una brecha semántica del Planner: el JSON Schema comprobaba que el campo
`origen` perteneciera al vocabulario permitido, pero no comprobaba que la función
tuviera realmente esa fuente. Una respuesta podía declarar `origen: "docstring"`
aunque `docstring` fuera `null`. Ahora cada caso de función pasa una validación cruzada
de procedencia. Las funciones sin documentación siguen siendo analizables y pueden
producir contratos cuando una anotación o la firma respalda una propiedad verificable.
Si no existe un oráculo fiable, el objetivo queda en `omitidas` con un mensaje claro.

No modificamos el schema público. La suite completa terminó con 1456 pruebas aprobadas
y 23 omitidas.

## 2. Introducción

QAgent construye pruebas desde análisis AST y contratos JSON sin ejecutar el código del
usuario para descubrir resultados. La issue surgió con `get_siamese_model`, una función
sin docstring y sin retorno informativo cuyo resultado depende de una biblioteca y de
hardware. Los valores concretos del modelo no podían justificarse con las fuentes que
admite `planner_contract.v2`.

## 3. Problema identificado

El analizador ya conservaba funciones sin docstring y representaba la ausencia como
`None`; ese componente no era la causa. El Planner enviaba nombre, firma y docstring al
modelo, y el prompt prohibía inventar resultados. Sin embargo, `_casos_validos` solo
validaba la forma del caso contra el schema. El schema no puede expresar por sí solo la
regla “si origen es docstring, esta función debe tener docstring”.

En la reproducción previa, tres variantes equivalentes a `device_por_defecto`,
`device_cpu` y `device_cuda` fueron aceptadas aunque citaban una docstring inexistente.
También se aceptaba un valor funcional arbitrario atribuido a la firma.

## 4. Objetivos de la corrección

- Aceptar funciones sin docstring cuando exista una propiedad verificable.
- Rechazar procedencias inexistentes o insuficientes.
- Omitir objetivos sin oráculo sin inventar resultados ni detener otros objetivos.
- Mantener contrato, Generator, Reviewer, reintentos y Assertion Laundering.
- Conservar compatibilidad con `develop` y las specs históricas.

## 5. Alcance

El cambio se limita al Planner y a pruebas automatizadas. No cambiamos frontend,
orquestador, Generator, Reviewer, schemas ni almacenamiento. No inferimos valores desde
el cuerpo completo de una función ni ejecutamos código del usuario. La continuidad
general de corridas y nuevas procedencias públicas quedan fuera de esta corrección.

## 6. Arquitectura relacionada

1. `analysis/analyzer.py` extrae firma, parámetros, retorno y docstring con `ast`.
2. `PlannerAgent` pide casos y arma contratos v2 con metadatos confiables del AST.
3. `contracts.validar` aplica JSON Schema estricto.
4. `GeneratorAgent` usa los valores del contrato, nunca resultados observados.
5. `ReviewerAgent` valida el oráculo, ejecuta en sandbox y compara reintentos.
6. El orquestador muestra `omitidas` y continúa con objetivos válidos.

## 7. Análisis del Planner

El Planner recibe por función nombre, firma y docstring en el prompt; conserva además
retorno y parámetros en los metadatos del módulo. Los campos de identidad del contrato
se reconstruyen desde el análisis, no desde el LLM. Los casos aportados por el modelo
incluyen entrada, valor o excepción, procedencia y categoría.

Los errores de sintaxis JSON o casos estructuralmente inválidos siguen levantando
`ErrorRespuestaPlanner`. La ausencia de un oráculo no es un error técnico: registra el
objetivo en `omitidas`. Los reintentos del orquestador pertenecen al ciclo
Generator–Reviewer; no se repite indefinidamente un objetivo sin nueva información.

## 8. Diagnóstico del contrato `planner_contract.v2`

El contrato exige versión, módulo, huella, tipo, objetivo, firma, marca crítica y al
menos un caso. Cada caso exige id, entrada, origen y valor esperado o excepción. La
enumeración de origen se mantuvo sin cambios.

La causa raíz no era un schema demasiado estricto sino una validación semántica
incompleta alrededor del schema. Añadir una procedencia `ast` habría modificado la API
pública y los consumidores históricos; no fue necesario para resolver el escenario
confirmado y, por tanto, no se hizo.

## 9. Tratamiento de funciones sin docstring

Una función sin docstring permanece seleccionable. No se permite que un caso declare
`origen: "docstring"`. Sí se admiten:

- un retorno `None` con valor esperado `null`;
- un `Literal` único con el mismo valor esperado;
- otros casos respaldados por anotaciones existentes conforme al modelo vigente;
- un `TypeError` demostrable antes de entrar al cuerpo por argumentos incompatibles.

La falta simultánea de docstring, tipos y una propiedad de invocación verificable
produce un mensaje que indica que se necesita información adicional.

## 10. Gestión de oráculos verificables

La validación cruza `origen` con los metadatos reales. Para `None` y `Literal[x]` se
comprueba además igualdad exacta. Para `firma`, solo se acepta `TypeError` cuando el AST
de la firma demuestra argumentos obligatorios faltantes, claves inesperadas o uso
inválido de parámetros posicionales exclusivos. No se ejecuta el cuerpo ni se toma la
salida actual como expectativa.

## 11. Protección contra Assertion Laundering

No se tocó `analysis/laundering.py`. La regresión nueva confirma que cambiar una
igualdad concreta por `is not None` sigue detectándose como rigor debilitado. El prompt
del Planner ahora prohíbe explícitamente convertir una prueba funcional en mera
invocación. Generator y Reviewer continúan exigiendo los valores del contrato.

## 12. Cambios implementados

- `src/qagent/agents/planner.py`: validación cruzada de procedencia, análisis seguro de
  firmas y anotaciones, mensajes de omisión y reglas de prompt.
- `tests/agents/test_issue113_sin_docstring.py`: 20 pruebas de regresión.
- `docs/evidencias/issue-113-pruebas-sin-docstring/`: resultados e informes locales.

No se modificó `planner_contract.v2.schema.json`.

## 13. Pruebas unitarias

Los 20 tests nuevos cubren funciones documentadas y no documentadas, ausencia de tipos,
`None`, `Literal`, errores de firma, oráculos no respaldados, JSON malformado, objetivos
independientes, Humo, contrato histórico y ausencia de proveedores reales.

La reproducción previa produjo 7 fallos y 6 aprobaciones sobre la primera versión del
archivo (13 casos). Después se añadieron 7 casos de borde: el archivo final reúne 20
pruebas, todas aprobadas. Los resultados previos se conservan sin alterar; el test que
allí figura como `test_tipo_int_no_justifica_un_valor_concreto` se llama ahora
`test_origen_tipo_sin_anotacion_no_justifica_un_valor_concreto`.

## 14. Pruebas de integración y regresión

La ruta Planner → Generator → Reviewer fue comprobada con clientes grabados y sin
Docker. La regresión focalizada produjo 129 aprobaciones. `python test.py --rapido`
produjo 1454 aprobaciones y 25 excluidas. `python test.py` produjo 1456 aprobaciones y
23 omitidas; Ruff y formato terminaron correctamente.

## 15. Evidencias, limitaciones y riesgos

Evidencias: [reproducción previa](reproduccion-antes.txt),
[resultados finales](resultados-despues.txt), [bitácora](bitacora-pruebas.md) y
[matriz de criterios](matriz-criterios.md).

APP-RF no estaba disponible en el entorno autorizado, por lo que no se ejecutó una
validación directa. El fixture reproduce su firma y los tres devices reportados, pero
no afirma equivalencia total con el proyecto original. Tampoco se extraen retornos
constantes u operaciones del cuerpo: representarlos como una fuente nueva requeriría
evaluar una ampliación compatible del contrato público.

El riesgo residual es que una anotación general puede requerir interpretación semántica
del Planner; la capa determinista comprueba la existencia de esa declaración, y aplica
comprobación exacta en `None` y `Literal`.

Ese riesgo se evaluó y se considera acotado, no una brecha que bloquee la publicación:

- Sin docstring, la anotación de retorno es la única fuente declarativa que queda; si se
  rechazara toda anotación general, las funciones `(x: int) -> int` volverían a omitirse y
  reaparecería el problema que motiva la issue #113.
- `docs/arquitectura.md` y `AGENTS.md` admiten firma, tipos y docstring como fuentes del
  oráculo, y una spec histórica (#76) exige aceptar `origen: "tipo"` para esa forma.
- La categoría `limite` con `origen: "tipo"` y sin especificación se descarta, así que la
  anotación general no habilita límites inventados.
- Un valor concreto equivocado produce un test que falla en el sandbox y entra al ciclo de
  reintento o queda reportado; nunca se convierte en un falso aprobado. El Reviewer exige
  además que el test use el valor esperado del contrato.

## 16. Conclusiones

La corrección evita contratos respaldados por documentación inexistente, permite casos
sin docstring cuando hay evidencia declarativa y comunica los objetivos no verificables
sin debilitar aserciones. El schema v2 y los consumidores permanecen compatibles. El
cambio está técnicamente listo para revisión, commit y Pull Request, pero no se realizó
ninguna de esas acciones.

## Matriz de criterios de aceptación

La matriz detallada está en [matriz-criterios.md](matriz-criterios.md). Todos los
criterios implementables dentro del contrato actual están cumplidos; la validación real
de APP-RF permanece pendiente por ausencia del proyecto.

## Relación de archivos modificados

- `src/qagent/agents/planner.py`
- `tests/agents/test_issue113_sin_docstring.py`
- Archivos de esta carpeta de evidencias, ignorados por Git según la política del repo.

## Anexos técnicos

- La issue #92 está integrada en la base mediante PR #93 (`516aa83`); su tip
  `20a6776` es ancestro de `origin/develop`.
- La mejora previa de omisiones (`ba8aa2c`) también está en la base y fue extendida, no
  reemplazada.
- No hay commit, push ni PR creados para #113.
