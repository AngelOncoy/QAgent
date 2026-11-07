# Perfiles y presentación de resultados Java (#262)

Una aprobación describe los casos ejecutados, no demuestra que el método esté
libre de defectos. El oráculo procede de Javadoc, tipos o declaraciones de rutas;
la ejecución en Docker únicamente contrasta ese oráculo con el resultado real.

## Matriz de comprobación

| Opción | Alcance comprobado | Evidencia automatizada |
|---|---|---|
| Humo | Un caso normal por objetivo, sin exigir ramas ni ejecutar PIT. Para `calcularEnvio(50)`, el esperado y el obtenido son 10. | `tests/sandbox/test_issue262_perfiles_java_docker.py`, parámetro `humo`. |
| Estándar | Conserva los casos normales, límites y errores respaldados por el contrato. En el escenario grabado, 50 pasa y 100 revela el defecto: esperado 0, obtenido 10. | El mismo archivo, parámetro `std`. |
| Regresión | Repite la prueba aprobada guardada sin generar otra ni consumir tokens. | El escenario `humo` anterior incluye una repetición real. |
| Profundo y regresión profunda | PIT se limita al método crítico con prueba aprobada; su puntuación se reutiliza cuando las huellas siguen vigentes. | `tests/sandbox/test_pit_corrida_docker.py`; casos de invalidación en `tests/orchestrator/test_pit_cache_resultados.py`. |
| Endpoints Spring MVC | MockMvc y servicios simulados con MockBean; respuesta declarada correcta, defecto HTTP y omisión cuando falta un resultado verificable. | `tests/sandbox/test_spring_corrida_docker.py`. |
| Arquitectura Java | ArchUnit comprueba ciclos y reglas de capas; un proyecto limpio también debe aprobar. | Los casos Java de `tests/sandbox/test_issue185_arquitectura_docker.py`. |
| E2E con Playwright | No disponible para proyectos Java. Preparar deshabilita los botones y explica la compatibilidad actual con aplicaciones JavaScript/TypeScript. | `tests/frontend/test_issue262_opciones_java.py`. No anuncia soporte Java inexistente. |

La selección de casos del escenario grabado es reproducible. No garantiza que
un proveedor real elija siempre el límite de 100. Humo puede aprobar un método
defectuoso si el único caso normal elegido no alcanza el defecto; no se cambia
su perfil para forzar un fallo.

## Explicaciones y evidencia

`storage/resumen_prueba.py` construye un resumen determinista cuando no hay una
explicación del Explicador. Cita esperado y obtenido solo si están registrados.
Un error técnico queda sin veredicto, no se transforma en un bug del método.
Las explicaciones existentes del Explicador conservan prioridad y los logs se
mantienen en «Ver detalle técnico».

El encabezado muestra el perfil y la aprobación aclara que pasaron los casos
probados. Los casos registrados siguen disponibles en la evidencia de auditoría.
Los objetivos omitidos guardan su lenguaje; al abrir registros antiguos se puede
recuperar de la extensión del módulo sin modificar los archivos históricos.
Esta vista también se utiliza para exportar el informe.

## Comandos reproducibles

Desde la raíz del repositorio, con el entorno virtual activo:

```powershell
python -m pytest tests/storage/test_issue262_resumen_java.py tests/storage/test_issue262_omitidos_java.py tests/frontend/test_issue262_resumen_java.py tests/frontend/test_issue262_opciones_java.py -q
python -m pytest tests/sandbox/test_issue262_perfiles_java_docker.py --docker -q -s
python -m pytest tests/sandbox/test_spring_corrida_docker.py tests/sandbox/test_pit_corrida_docker.py tests/sandbox/test_issue185_arquitectura_docker.py::test_java_detecta_ciclo_y_capa "tests/sandbox/test_issue185_arquitectura_docker.py::test_proyecto_limpio_cumple_regla_universal[java]" --docker -q -s
python test.py -m "not docker and not red"
```

Las pruebas Docker requieren Docker Desktop y las imágenes Java y Spring
preparadas según [validacion-ep12.md](validacion-ep12.md). La red se utiliza solo
para preparar imágenes y dependencias; las pruebas Java se ejecutan sin red.
Los proveedores de IA están grabados: no se usan claves ni tokens reales.
Un resultado `skipped` indica que esa comprobación no se ejecutó y no cuenta
como aprobación. `--docker` es necesario para habilitar Docker real.

### Resultados observados el 7 de noviembre de 2026

- Humo y estándar con regresión de la prueba aprobada: **2 passed**; repetición
  del integrante: **2 passed en 87.12 s**.
- Spring, PIT y los dos escenarios ArchUnit anteriores: **4 passed en 182.52 s**,
  sin omisiones. Spring produjo un aprobado, un defecto HTTP y un omitido;
  PIT obtuvo 60 % y la regresión profunda reutilizó su puntuación.
- Ruff: lint aprobado y **479 archivos** con formato correcto.

Estos resultados corresponden a los escenarios indicados y no sustituyen la
regresión general ni la comprobación visual en la aplicación.

## Comprobación en la aplicación

Abrir QAgent desde esta versión del código con `python -m qagent`. Reabrir en
Historial una corrida Humo y una estándar del banco Java y comprobar:

- El perfil y el lenguaje Java aparecen en los resultados.
- El resumen principal es legible; la traza Maven sigue en el detalle técnico.
- Una aprobación delimita los casos probados; el fallo conserva sus valores
  esperado y obtenido.
- El informe exportado conserva la explicación y el lenguaje de los omitidos.
- En Preparar, E2E Java está deshabilitado y arquitectura sigue disponible.

Reabrir evidencia guardada no requiere repetir llamadas a la IA. Una corrida
nueva con proveedor real sí puede consumir tokens y sus casos deben revisarse.
Los límites del ejecutor siguen siendo Maven de un módulo y Spring MVC según
[ejecucion-revision.md](ejecucion-revision.md) y
[spring-mockmvc.md](spring-mockmvc.md); no se amplían a Gradle, servicios reales
ni un contexto SpringBootTest completo.
