# Adaptadores por lenguaje (EN-17)

Todo lo que depende del lenguaje del código del usuario vive aquí. El orquestador,
el Planner, el Generator y el Reviewer son compartidos: piden un adaptador al
registro y hablan con él y con los contratos, nunca con un parser o un runner
concreto. Decisión completa en `docs/decisiones/ADR-007-adaptadores-por-lenguaje.md`.

| Archivo | Contenido | Estado |
|---|---|---|
| `base.py` | `LanguageAdapter`, `AdaptadorEnDesarrollo`, `Deteccion`, `EntornoSandbox`, `NoImplementado` | Estable |
| `registro.py` | `Registro`, `listar_archivos` | Estable |
| `python.py` | `PythonAdapter` (delega en el flujo actual) | Completo |
| `javascript.py` | `JavaScriptAdapter`, `TypeScriptAdapter` | Solo detecta |
| `java.py` | `JavaAdapter` | Solo detecta |

## Uso

```python
from qagent.lenguajes import adaptador_de_contrato, adaptador_para, detectar_lenguaje

detectar_lenguaje("ruta/al/proyecto")
# [Deteccion(lenguaje='typescript', archivos=12, marcadores=('tsconfig.json',), confianza=0.8), ...]

adaptador = adaptador_para("python")
# Igual que analizar_proyecto, más "lenguaje".
estructura = adaptador.analizar("ruta/al/proyecto")
# [{"modulo", "tipo", "objetivo"}, ...]
adaptador.objetivos(estructura)
# ["pytest", "/work/tests", "--cov=tienda.precios", ...]
adaptador.comando_pruebas("tienda.precios")

# v2 -> PythonAdapter; v3 -> según "lenguaje".
adaptador_de_contrato(contrato)
```

Contratos:

```python
from qagent import contracts

contracts.validar_versionado(contracts.FAMILIA_PLANNER, contrato)  # acepta v2 y v3
contracts.normalizar_planner(contrato_v2)  # copia en v3 (python + pytest)
```

## La interfaz

| Operación | Qué devuelve | Notas |
|---|---|---|
| `detectar(archivos)` | `Deteccion` o `None` | Ya implementada con `extensiones` y `marcadores`. Se puede sobrescribir `es_fuente` (TypeScript ignora `.d.ts`). |
| `analizar(raiz)` | `{"lenguaje", "modulos", "errores", "resumen"}` | Misma forma que `qagent.analysis.analizar_proyecto`. **Estático.** |
| `objetivos(estructura)` | `[{"modulo", "tipo", "objetivo"}]` | Ya implementada: recorre `funciones` y `endpoints`. |
| `comando_pruebas(modulo, framework=None)` | `list[str]` | Usa `elegir_framework()` para validar el framework del contrato. |
| `entorno_sandbox()` | `EntornoSandbox` | Imagen, herramientas base, carpetas e informe. |
| `interpretar_resultados(informe)` | `dict` con `total`, `pasaron`, `fallaron`, `errores`, `omitidos`, `duracion_s`, `inicio`, `casos` | Jest (`jest-junit`), Vitest (`--reporter=junit`) y Surefire de JUnit 5 también escriben JUnit XML: conviene reutilizar `qagent.sandbox.informe_pytest`. |
| `validar_sintaxis(codigo)` | `list[str]` (vacía = válido) | Parsear, no ejecutar. |
| `comparar_aserciones(original, reparado)` | objeto con `es_laundering` y `resumen` | Ver las 7 reglas de `qagent.analysis.laundering`. |

## Cómo implementar un lenguaje

1. Trabaja solo en tu archivo (`javascript.py` o `java.py`) y en `tests/lenguajes/`.
2. Reemplaza los métodos de `AdaptadorEnDesarrollo` **uno por uno**; los que falten siguen lanzando `NoImplementado`.
3. `analizar` debe devolver objetivos cuyo `objetivo` cumpla el contrato v3: un nombre (`calcularDescuento`, `Precios.calcular`) o `MÉTODO /ruta` para endpoints.
4. El parser sigue la decisión de SPK-04. Una dependencia nueva necesita su ADR antes de entrar en `pyproject.toml`.
5. Si cambian los lenguajes o frameworks admitidos, actualiza a la vez los `enum` de `planner_contract.v3` / `generated_test.v2` y `contracts.FRAMEWORKS_PRUEBAS` / `FRAMEWORKS_APP` (una prueba lo exige).

Reglas que no se rompen (AGENTS.md): nada del usuario se ejecuta fuera del sandbox, el valor esperado sale del contrato y nunca de ejecutar el código, y este paquete no importa `qagent.app` ni `webview`.

## Revisión con los responsables de JS/TS y Java

Antes de cerrar EN-17 conviene revisar juntos:

- [ ] ¿Alcanzan `lenguaje`, `framework_pruebas` y `framework_app` del contrato v3? ¿Falta algún framework (Mocha, TestNG…)?
- [ ] ¿El `objetivo` como `Clase.metodo` sirve para Java y para métodos de clases en TS?
- [ ] ¿Los `origen` del oráculo (`docstring` incluye JSDoc y Javadoc) bastan?
- [ ] ¿La forma de `analizar` (módulos → funciones/endpoints) es suficiente para su parser?
- [ ] ¿El runner de cada lenguaje puede producir JUnit XML para reutilizar `interpretar_resultados`?
- [ ] ¿Qué imagen de sandbox necesita cada lenguaje (Node, JDK + Maven/Gradle sin red)?
