# Métricas, contadores y estados de corrida en QAgent

Este documento detalla el significado, origen y cálculo de cada contador y métrica mostrada en el Monitor, Ejecución de pruebas, Reporte de auditoría, Historial y el apartado de Pruebas guardadas.

## 1. Contadores de objetivos y corridas

| Contador | Significado | Origen / Cálculo |
|---|---|---|
| **Objetivos seleccionados** (`total_seleccionados`) | Total de funciones y endpoints elegidos antes de iniciar la corrida (o todos los analizables del proyecto si no se aplicó filtro). | Suma de funciones y endpoints de los módulos filtrados por selección en AST (`analizar_proyecto`). Persistido en `results.json` y `run.json`. |
| **Objetivos procesados** (`total_procesados`) | Funciones y endpoints sobre los que el pipeline orquestador llegó a planificar y ejecutar pruebas con veredicto. | Conteo de objetivos con veredicto en `results.json` (`len(results["objetivos"])`). |
| **Objetivos pendientes** (`total_pendientes` / `no_procesados_por_detencion`) | Objetivos seleccionados que quedaron sin procesar debido a que la corrida se detuvo antes de finalizar. | `max(0, total_seleccionados - total_procesados)`. |
| **Pruebas ejecutadas** (`pruebas_ejecutadas`) | Conteo de ejecuciones de pruebas realizadas en el sandbox durante la corrida. | Suma de iteraciones/intentos de prueba evaluados por objetivo. |
| **Pruebas aprobadas** (`pruebas_aprobadas` / `pasaron`) | Objetivos cuya prueba fue verificada satisfactoriamente en el entorno aislado (sandbox) sin Assertion Laundering (`decision == "accept"`). | `sum(1 for o in objetivos if o["decision"] == "accept")`. |
| **Bugs detectados** (`posibles_bugs`) | Objetivos donde la prueba generada falló válidamente contra el código real revelando un defecto funcional (`decision == "bug_detectado"`). | `sum(1 for o in objetivos if o["decision"] == "bug_detectado")`. |
| **Errores técnicos** (`errores_tecnicos`) | Objetivos que no aprobaron ni fueron bugs debido a agotamiento de intentos (`stalled`), laundering persistente o fallos de ejecución sin veredicto (`sin_veredicto`). | Objetivos con `decision in ("stalled", None)`. |
| **Objetivos omitidos** (`objetivos_omitidos`) | Endpoints o funciones no analizables u omitidos deliberadamente por el analizador/orquestador. | `results.get("objetivos_omitidos", 0)`. |
| **Denominador de la columna PASAN** | El denominador corresponde estrictamente a los **objetivos procesados** con veredicto en esa corrida. Si la corrida fue parcial, se informa explícitamente el total seleccionado y los pendientes. | Formato: `${pasaron} / ${procesados} procesados (${pendientes} pend. de ${seleccionados})`. |

---

## 2. Clasificación de pruebas y artefactos guardados

En el apartado «Pruebas guardadas» de la pantalla Historial se distinguen 5 conceptos que representan artefactos distintos:

1. **Planes de prueba (specs)**:
   - Archivos JSON guardados en `.qagent/specs/<modulo>.spec.json`.
   - Contienen las especificaciones y contratos formales definidos por el Planner (casos normales, límites y de error).
2. **Archivos de prueba generados**:
   - Archivos Python guardados en `.qagent/tests/test_<spec_id>.py`.
   - Código ejecutable con pytest que implementa los contratos aprobados.
3. **Pruebas aceptadas**:
   - Funciones individuales `def test_*` dentro de los archivos de prueba aprobados.
4. **Pruebas disponibles para regresión**:
   - Pruebas guardadas cuya función o endpoint de origen mantiene su huella o código vigente en el proyecto, listas para reejecutarse sin IA.
5. **Pruebas que detectaron defectos**:
   - Pruebas que revelaron bugs durante las corridas. Sus evidencias quedan registradas en `results.json` y `detalle.json` para auditoría, pero no se guardan como pruebas verdes en `.qagent/tests/` para no romper regresiones limpias.

---

## 3. Estados de terminación de corrida (completas y parciales)

Cada corrida persistida clasifica su finalización según las siguientes categorías:

- **`completada` ("Completada")**: Todos los objetivos seleccionados fueron procesados sin errores no recuperables.
- **`completada_con_errores` ("Completada con errores")**: Todos los objetivos seleccionados fueron procesados, pero uno o más terminaron estancados (`stalled`) o sin veredicto.
- **`detenida_error` ("Detenida por error")**: La corrida se detuvo antes de procesar todos los módulos debido a una excepción global o fallo crítico de infraestructura.
- **`cancelada` ("Cancelada")**: El usuario detuvo voluntariamente la corrida desde la interfaz.
- **`limitada_recursos` ("Limitada por recursos")**: La corrida se detuvo al alcanzar el tope de gasto en dólares (`tope_por_corrida_usd`), el presupuesto de tokens (`max_tokens_por_corrida`) o el límite de tiempo.
