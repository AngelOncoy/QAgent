# HU-25 — Re-ejecutar pruebas sin costo (Regresión)

## 1. Portada y datos

| Campo | Valor |
|---|---|
| Producto | QAgent |
| Épica / sprint | Épica 8 / Sprint 1 |
| Prioridad / Story Points | Media / 1 |
| Responsable | Rodrigo Abel Rodríguez Malca |
| Rama | `feat/hu-25-regresion-sin-costo` |
| Fecha de validación | 13/10/2026 |
| Estado documental | Implementado y validado; sin commit ni push |

## 2. Historia de usuario

Como equipo de QA, quiero volver a ejecutar las pruebas aprobadas sin usar IA, para confirmar que nada se rompió sin gastar tokens.

## 3. Problema identificado

Analicé el soporte existente y comprobé que la interfaz ya mostraba un perfil llamado Regresión, pero el backend enviaba ese perfil al mismo flujo de Planner, Generator y Reviewer. Por tanto, la opción era visual y todavía no garantizaba reutilización, ausencia de clientes LLM ni comparación por función.

También comprobé que QAgent ya guardaba únicamente pruebas aceptadas en `.pyagent/tests/`, pero las specs solo conservaban una huella del módulo completo. Esa huella modular sirve para reutilizar el plan, pero no permite decidir de manera independiente si una prueba aprobada sigue vigente para una función concreta.

## 4. Objetivo general

Implementé una ruta determinista para el perfil `reg` que selecciona pruebas aprobadas, verifica su huella por objetivo, ejecuta las elegibles en el sandbox Docker existente y registra una corrida nueva con cero llamadas LLM.

## 5. Criterios de aceptación originales

| Criterio | Resultado |
|---|---|
| CA-01 — re-ejecución en sandbox sin IA | Cumplido |
| CA-02 — función modificada requiere corrida nueva | Cumplido |
| CA-03 — solo pruebas aprobadas | Cumplido |
| CA-04 — nueva corrida en Historial | Cumplido |
| CA-05 — 0 tokens y estado visible | Cumplido |

## 6. Diagnóstico inicial

Antes de modificar código verifiqué que `develop` estaba limpio y actualizado en `7d4ce70`, con EN-15 y HU-28 integradas, y creé la rama independiente indicada. Identifiqué estos componentes reutilizables:

- `AlmacenProyecto` ya administra `.pyagent/tests/`, specs y runs.
- `_registrar()` ya promociona un test solo cuando `decision == "accept"`.
- `ejecutar_pruebas()` ya usa Docker con `network_mode="none"`, límites, capabilities eliminadas y `no-new-privileges`.
- `TokenTracker` ya persiste tokens y costo.
- `escribir_corrida()` ya crea `log.json`, `results.json` y `detalle.json` compatibles con Historial, Ejecución y Reporte.

## 7. Arquitectura y componentes utilizados

Reutilicé el flujo existente y añadí `orchestrator/regresion.py` como una ruta especializada del orquestador. `ejecutar_corrida()` delega inmediatamente cuando `perfil == "reg"`; esta decisión ocurre antes de crear cualquier cliente LLM.

```text
Perfil reg
  -> leer specs con archivo_prueba aprobado
  -> calcular huella AST actual por (módulo, objetivo)
  -> distinta/dudosa: requiere corrida nueva, no ejecutar
  -> coincidente: ejecutar pytest en Docker sin red
  -> escribir log/results/detalle y finalizar run
```

## 8. Decisiones técnicas justificadas

Elegí SHA-256 sobre `ast.dump(..., include_attributes=False)` de cada función. Así la huella depende de la estructura, firma, decoradores, docstring y cuerpo, pero no de números de línea. La identidad usa la pareja `(ruta POSIX del módulo, objetivo)`, por lo que dos funciones con el mismo nombre en módulos distintos no colisionan.

Mantuve la huella modular de HU-24 sin cambiar su significado. Añadí `huella_objetivo` a la spec individual como dato opcional para conservar compatibilidad con specs antiguas. Si falta o es inválida, el comportamiento es conservador: la prueba no se ejecuta.

## 9. Implementación del perfil Regresión

Implementé `ejecutar_regresion()` para leer candidatas aprobadas, preparar Docker solo si hay al menos una prueba elegible, copiar de manera temporal una prueba a la vez y reutilizar `ejecutar_pruebas()`. No regenera código y no actualiza las specs de origen.

Cada resultado conserva `reutilizada`, `motivo_regresion`, duración, cobertura disponible y salida de pytest. El resumen incluye `requieren_corrida_nueva`.

## 10. Persistencia de pruebas aprobadas

Confirmé que la corrida normal mantiene la regla existente:

```python
if objetivo.decision == "accept" and objetivo.codigo:
    almacen.guardar_prueba_aprobada(archivo, objetivo.codigo)
```

Extendí ese punto para guardar la huella individual. Las specs rechazadas, con bug o estancadas pueden permanecer como auditoría, pero su `archivo_prueba` es `null`; Regresión no las selecciona. En la corrida real del banco hubo seis specs y solo tres archivos elegibles.

## 11. Mecanismo de huellas

La función `huellas_de_objetivos()` analiza exclusivamente con `ast`; no importa ni ejecuta módulos del usuario. Para endpoints también relaciona el método y la ruta declarados en el decorador con la huella AST del manejador.

La evidencia exacta está en [comparacion_huellas.json](comparacion_huellas.json):

- guardada: `6f86909ad605b18aa1ce90f6c88bde448da368995bbe0adbeadd7f7f0886fa56`;
- actual: `3ec93f8e7a555ddb495035bcf04d28e7f5f81682d1d09fe2630de9afdc66c8c1`.

## 12. Detección de funciones modificadas

Modifiqué una copia temporal de `es_palindromo`. La segunda regresión comparó las huellas, produjo `motivo_regresion: "huella_distinta"`, registró cero intentos y no envió esa prueba al ejecutor. Las otras dos pruebas sí se ejecutaron.

También probé función eliminada/renombrada, huella ausente, hash corrupto y nombres duplicados en módulos diferentes. Una spec completamente ilegible no se ejecuta; al no existir identidad confiable, se omite como candidata y la corrida solo usa metadatos verificables.

## 13. Ejecución sin llamadas a IA

La delegación a Regresión ocurre antes del bloque que llama `crear_cliente`. Además, implementé una prueba espía que reemplaza `crear_cliente` por una función que lanza `AssertionError`. La regresión terminó correctamente, lo que demuestra que el contador en cero no es un simple cambio visual.

El `log.json` real quedó con `llamadas: []`; Planner, Generator y Reviewer registraron 0 tokens y el costo LLM fue US$ 0.00. Véase [validacion_cero_tokens.json](validacion_cero_tokens.json).

## 14. Sandbox Docker y seguridad

Ejecuté la regresión con Docker Engine 29.7.2 y la imagen `pyagent-sandbox:base`. Reutilicé los controles reales:

- `network_mode="none"`;
- CPU, memoria, PIDs y timeout limitados;
- `cap_drop=["ALL"]`;
- `security_opt=["no-new-privileges"]`;
- copia temporal del proyecto sin `.env`;
- eliminación defensiva del contenedor y temporales.

Una prueba aprobada intentó abrir una conexión a `1.1.1.1:53` y exigió `OSError`; pasó dentro del sandbox, confirmando la ausencia de salida de red.

## 15. Integración con la interfaz

Conecté la opción existente de Regresión al backend real. La disponibilidad ahora depende de `tiene_pruebas_aprobadas()` y no solo de haber tenido una corrida previa. El Monitor recibe mensajes del orquestador con “sin IA” y no simula generación. Ejecución y Reporte reconocen `requiere_corrida_nueva`. Historial etiqueta las corridas `reg` como `— (sin IA)`.

## 16. Registro en Historial

La demostración generó tres IDs distintos:

| Run | Perfil | Resultado | Tokens | Costo |
|---|---|---:|---:|---:|
| `20261013-153821-5ff6` | Profundo, IA simulada | 3 aprobadas / 3 bugs | 0 | US$ 0.00 |
| `20261013-153839-1bb6` | Regresión | 3 aprobadas | 0 | US$ 0.00 |
| `20261013-153850-96c4` | Regresión | 2 aprobadas / 1 requiere nueva | 0 | US$ 0.00 |

No se sobrescribió ninguna corrida.

## 17. Archivos creados y modificados

Modifiqué almacenamiento, enrutamiento de corrida, modelo de resultado, registro, esquema, vistas Python, puente de escritorio y cinco componentes JavaScript. Creé:

- `src/pyagent/orchestrator/regresion.py`;
- `tests/orchestrator/test_hu25_regresion.py`;
- `tests/sandbox/test_hu25_regresion_docker.py`;
- `tests/frontend/test_hu25_regresion.py`;
- esta carpeta de evidencias.

No modifiqué Planner, Generator, Reviewer ni el ejecutor Docker funcional más allá de reutilizarlos.

## 18. Pruebas unitarias

Implementé casos para selección de aprobadas, cliente LLM prohibido, cero tokens, huellas diferentes, función eliminada, renombrada y movida de módulo, hash ausente/corrupto, nombres duplicados, proyecto sin aprobadas y estados de frontend. El archivo focalizado del orquestador obtuvo 10 pruebas aprobadas.

## 19. Pruebas de integración

Las pruebas focalizadas de HU-25, vistas y almacenamiento obtuvieron 57 aprobadas antes de agregar los dos casos finales de identidad. La suite rápida completa final obtuvo 899 aprobadas y 19 omitidas por marcadores Docker/red. `ruff check .` y `git diff --check` terminaron sin errores.

## 20. Corrida real de Regresión

En Docker ejecuté una corrida normal con IA simulada sobre una copia del banco. Las seis pruebas generadas se ejecutaron en el sandbox: tres quedaron aprobadas y tres detectaron los bugs sembrados. Luego Regresión reejecutó únicamente las tres aprobadas y obtuvo 100 % de pass rate, sin clientes LLM.

Los valores saneados están en [resultado_regresion.json](resultado_regresion.json) y los comandos en [pruebas_ejecutadas.md](pruebas_ejecutadas.md).

## 21. Escenario de función modificada

Después de modificar `es_palindromo`, ejecuté otra regresión. QAgent omitió su prueba, ejecutó las otras dos y registró exactamente `requiere_corrida_nueva`. El Pass Rate fue 66.7 % porque dos de tres objetivos tuvieron ejecución satisfactoria.

## 22. Verificación de cero tokens

Comprobé tres niveles: el cliente espía no fue invocado, el `TokenTracker` no recibió llamadas y los artefactos persistieron lista de llamadas vacía, total 0 y costo 0. La interfaz leyó esos datos desde las vistas Python; JavaScript no calculó tokens.

## 23. Capturas de pantalla

| ID | Evidencia |
|---|---|
| CAP-01 | [Selección del perfil Regresión](img/CAP-01-seleccion-regresion.png) |
| CAP-02 | [Pruebas aprobadas almacenadas](img/CAP-02-pruebas-aprobadas.png) |
| CAP-03 | [Ejecución Docker real](img/CAP-03-docker-real.png) |
| CAP-04 | [Historial con 0 tokens](img/CAP-04-historial-cero-tokens.png) |
| CAP-05 | [Cambio de huella](img/CAP-05-cambio-huella.png) |
| CAP-06 | [Estado requiere corrida nueva](img/CAP-06-requiere-corrida-nueva.png) |
| CAP-07 | [Exclusión de no aprobadas](img/CAP-07-exclusion-no-aprobadas.png) |
| CAP-08 | [Historial de varias corridas](img/CAP-08-varias-corridas.png) |
| CAP-09 | [Pruebas automatizadas](img/CAP-09-pruebas-automatizadas.png) |
| CAP-10 | [Consistencia con JSON](img/CAP-10-consistencia-json.png) |

Las capturas de QAgent usan el frontend real en Chrome headless y las estructuras generadas por `vista_ejecucion`, `vista_reporte` e Historial. No son una prueba manual en la ventana nativa pywebview; dejo esa comprobación de humo como recomendación previa al PR. Los paneles de soporte CAP-02, 03, 05, 07, 09 y 10 reproducen datos de artefactos reales saneados y están identificados como evidencia, no como pantallas de QAgent.

## 24. Evidencias JSON y resultados

- [resultado_regresion.json](resultado_regresion.json)
- [comparacion_huellas.json](comparacion_huellas.json)
- [validacion_cero_tokens.json](validacion_cero_tokens.json)
- [qa_visual.json](qa_visual.json)
- [evidencias_sha256.json](evidencias_sha256.json)

## 25. Matriz CA-01 a CA-05

| CA | Evidencia verificable | Estado |
|---|---|---|
| CA-01 | 3 pruebas reutilizadas en Docker, red bloqueada, cliente espía y `llamadas: []` | Cumplido |
| CA-02 | `es_palindromo`, huellas distintas, 0 intentos y estado exacto | Cumplido |
| CA-03 | 6 specs, solo 3 archivos en `.pyagent/tests/`; no aprobadas con archivo `null` | Cumplido |
| CA-04 | tres IDs y runs distintos visibles en Historial | Cumplido |
| CA-05 | Historial con 0 tokens y Ejecución con `requiere corrida nueva` | Cumplido |

## 26. Problemas encontrados y soluciones

Encontré una opción de Regresión desconectada, una huella demasiado amplia y una cobertura inicialmente solicitada con la ruta `archivo.py` en vez del nombre importable `archivo`. Separé la ruta sin IA, añadí huella individual y normalicé el módulo de coverage igual que Reviewer. También conservé compatibilidad con specs antiguas marcándolas como no verificables en lugar de ejecutarlas.

## 27. Limitaciones y riesgos

- Una modificación en una dependencia privada no cambia la huella de la función objetivo; esto es intencional para que la regresión ejecute el test y detecte el cambio de comportamiento. Lo validé con un fallo real.
- Una spec JSON completamente ilegible se excluye sin atribuirla a una función porque su identidad no es confiable.
- La cobertura mostrada por una prueba individual corresponde al módulo en esa ejecución; no la comparé automáticamente con una línea base anterior.
- Falta una comprobación manual breve dentro de pywebview; la QA visual automatizada fue headless.
- El costo LLM es cero; el uso local de CPU/RAM de Docker no es un costo de tokens.

## 28. Aprendizajes obtenidos

Aprendí que “mostrar 0 tokens” no demuestra ausencia de IA: la garantía debe estar en el control de flujo y verificarse con un cliente que falle si es usado. También confirmé que una identidad compuesta por módulo y objetivo evita ambigüedades, y que ante metadatos dudosos es más seguro omitir que reutilizar.

## 29. Conclusión

Implementé y comprobé una Regresión real que reutiliza solamente pruebas aprobadas, mantiene el aislamiento Docker, no construye clientes LLM y registra resultados auditables. Verifiqué tanto el caso feliz como una función modificada y un fallo posterior real. Considero HU-25 terminada dentro de su alcance técnico, con la validación manual pywebview como control de presentación recomendado antes de publicar el PR.

## 30. Resumen para Notion

| Descripción / Historia de Usuario / Objetivo | Criterios de Aceptación / Detalles Clave |
|---|---|
| Como equipo de QA, quiero volver a ejecutar las pruebas aprobadas sin usar IA, para confirmar que nada se rompió sin gastar tokens. Implementé una ruta de Regresión que valida huellas por objetivo y ejecuta pytest en Docker sin red. | CA-01 a CA-05 cumplidos: 3 tests aprobados reutilizados, no aprobados excluidos, 0 llamadas y 0 tokens, runs nuevos en Historial y función modificada marcada `requiere corrida nueva` sin ejecutarla. |

Demostración breve: primero muestro las tres pruebas aprobadas en `.pyagent/tests/`; después selecciono Regresión; enseño la corrida Docker y el Historial con 0 tokens; finalmente modifico `es_palindromo` y muestro que su huella cambia, su test registra 0 intentos y las otras pruebas continúan ejecutándose.

**Título sugerido del PR:** `feat(HU-25): reejecutar pruebas aprobadas sin IA en regresión`  
**Destino:** `develop`.
