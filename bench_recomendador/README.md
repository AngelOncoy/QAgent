# Banco del Agente Recomendador (SPK #201)

Mide el Recomendador con un LLM real (paso 2 del ADR-011) frente a las reglas (paso 1, 0 tokens) antes de decidir si `[agentes.recomendador]` queda en `modo = "ia"` por defecto.

Es, junto con `bench_explicador/`, el **único** lugar de QAgent que llama a una API real. Lo corre una persona con su clave en `~/.qagent/.env`. Ninguna prueba de `tests/` lo hace con la IA real: las de este script (`tests/agents/test_issue201_medir_recomendador.py`) usan la IA simulada y clientes falsos.

Va fuera de `bench/` porque las pruebas del sistema analizan esa carpeta completa.

## Qué hay

| Ruta | Qué es |
|---|---|
| `proyectos/solo_funciones/` | Cuatro funciones, una sin tipos ni documentación: la recomendación esperada es unitarias y mutación |
| `proyectos/fastapi/` | Tres endpoints FastAPI: endpoints y mutación |
| `proyectos/mixto/` | Una API y funciones de negocio: endpoints, unitarias y mutación |
| `medir_recomendador.py` | La medición, la planilla a ciegas y su puntuación |
| `rubrica.md` | Criterios para la evaluación de una persona del equipo |
| `resultados/<fecha>/` | Lo que deja cada medición: `metricas.json`, `respuestas.json`, `resumen.md` y `revision/` |

No hay un proyecto de Reflex: QAgent todavía no tiene adaptador para ese framework, así que el Recomendador no puede analizarlo.

## Cómo repetir la medición

1. Instala QAgent en modo editable (`pip install -e .[dev]`) y pon en `~/.qagent/.env` la clave del proveedor que quieras medir. El script busca primero la clave propia del Recomendador (`<PROVEEDOR>_API_KEY_RECOMENDADOR`, por ejemplo `DEEPSEEK_API_KEY_RECOMENDADOR`) y después la del proveedor (`DEEPSEEK_API_KEY`), igual que la aplicación. La clave de otro agente (`..._PLANNER`) no se usa. Ninguna clave se escribe en los resultados.
2. Quita `QAGENT_FAKE_LLM` del sistema y de `.env`. Con la IA simulada el script funciona igual, pero las cifras salen marcadas [SIMULADO] y no sirven para decidir.
3. Desde la raíz del repositorio:

   ```bash
   python bench_recomendador/medir_recomendador.py
   ```

   Opciones:

   - `--modelos planner reviewer`: qué modelos probar, por el agente de `config.toml` (o `config.local.toml`) que lo usa. Por omisión, todos los distintos; con `modo = "ia"` también el de `[agentes.recomendador]`.
   - `--modelo deepseek/deepseek-flash`: en lugar de los de `config.toml`, modelos del catálogo (`src/qagent/llm/proveedores.toml`) como `proveedor/modelo`, con los precios del catálogo. No se combina con `--modelos`. El modelo que se elija se registra después en `[agentes.recomendador]`.
   - `--repeticiones 3`: cuántas veces se pide la recomendación de cada proyecto con cada modelo.
   - `--tiempo-maximo 30`: segundos por recomendación. Al vencer se usan las reglas y cuenta como descarte `tiempo_agotado`.
   - `--salida <carpeta>`: dónde dejar los resultados (por omisión, `resultados/<fecha>/`).
   - `--config-local <archivo>`: otro `config.local.toml` (por omisión, `~/.qagent/config.local.toml`, como la aplicación).

4. Revisa `resumen.md` y versiona la carpeta de `resultados/` en el PR.

Costo esperado: 3 proyectos × 3 repeticiones por modelo, con unos 600 a 1 000 tokens de entrada cada uno. Con los precios del catálogo son fracciones de centavo de dólar por modelo.

## Qué mide

Por proyecto y por modelo (la línea base son las reglas, sin tokens):

- tokens de entrada y salida, costo en USD y latencia (p50 y p95);
- cuántas respuestas se usaron y cuántas se descartaron, por motivo. Cada descarte deja las reglas en su lugar:

  | Motivo | Cuándo |
  |---|---|
  | `json_invalido` | La respuesta no es un objeto JSON o le falta la lista `recomendaciones` |
  | `contrato_invalido` | No cumple `recommendation.v1` (tipo repetido, propiedad extra, sin motivo…) |
  | `tipo_no_permitido` | Recomienda un tipo que las reglas no propusieron |
  | `sin_recomendaciones` | No recomienda ningún tipo habiendo opciones |
  | `tiempo_agotado` | No respondió en `--tiempo-maximo` |
  | `error_llm` | Error del proveedor o de red |

- si la IA **cambia el orden** respecto de las reglas, **omite tipos** o **cambia el motivo** (los motivos de la IA nunca son iguales palabra por palabra; interesa más si el orden cambia).

Comprobación que hace siempre: antes de enviar, la entrada (`entrada_ia`) no debe llevar rutas absolutas ni nada que `sanitizar_secretos` reconozca como clave. Si lo encuentra, se detiene sin enviarla. Todo lo que escribe pasa por `sanitizar_secretos`.

## Evaluación de una persona del equipo

La utilidad la juzga al menos una persona con `rubrica.md`, comparando reglas e IA **sin saber cuál es cuál**.

1. La medición deja `resultados/<fecha>/revision/planilla.csv` (separada por `;`, UTF-8, se abre en Excel o Google Sheets) y `clave.json`. Cada fila es un proyecto con un modelo, con sus **hechos** y dos recomendaciones, **A** y **B**, en orden al azar. Se usa la repetición 1; las respuestas descartadas no entran, porque en la aplicación se habría mostrado la de las reglas.
2. **`clave.json` no se comparte** con quien revisa: es lo que revela cuál era cuál.
3. Cada persona copia la planilla como `planilla-<nombre>.csv`, pone un 1, 2 o 3 en `util_A` y `util_B`, y `A`, `B` o `igual` en `preferida`.
4. Con las planillas en `revision/`:

   ```bash
   python bench_recomendador/medir_recomendador.py --puntuar bench_recomendador/resultados/<fecha>
   ```

   Si a una planilla le falta algo, dice qué celda. Si está todo, deja `revision/resultado.md` y `resultado.json` con la utilidad promedio y las preferencias de reglas e IA.
5. Versiona la carpeta `revision/` completa.

## Cómo se marcan las cifras

Con el mismo criterio que el ADR-008:

- **[MEDIDO]:** salió de esta medición con un LLM real, con los tokens que informó el proveedor.
- **[ESTIMADO]:** el proveedor no informó tokens y se calcularon como caracteres / 4.
- **[SIMULADO]:** IA simulada (0 tokens). Solo prueba que el script funciona.
