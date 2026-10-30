# Banco del Agente Explicador (SPK #167)

Mide el Explicador con un LLM real (paso 2 del ADR-008) frente a las plantillas (paso 1, 0 tokens) antes de decidir si `[agentes.explicador]` queda en `modo = "ia"` por defecto.

Es el **único** lugar de QAgent que llama a una API real. Lo corre una persona con su clave en `~/.qagent/.env`. Ninguna prueba de `tests/` lo hace con la IA real: las pruebas del script (`tests/agents/test_issue167_*.py`) usan la IA simulada y clientes falsos.

Va fuera de `bench/` porque las pruebas del sistema analizan esa carpeta completa y esperan solo las 6 funciones de `banco_mvp.py`.

## Qué hay

| Archivo | Qué es |
|---|---|
| `banco_explicador.py` | Funciones de los hallazgos que `bench/banco_mvp.py` no da: prueba estancada, Assertion Laundering y sin veredicto (detalle en `bench/bugs.md`) |
| `casos/results.json`, `casos/detalle.json` | La corrida fija que se explica: los 3 bugs de `banco_mvp.py` (salida real de pytest grabada) y una traza de 2 o 3 intentos de cada tipo nuevo. Sin rutas de la máquina |
| `preparar_casos.py` | Vuelve a armar `casos/` sin red, sin Docker y sin gastar tokens. Solo hace falta correrlo si cambian el banco, las grabaciones o el formato de `results.json` o `detalle.json` |
| `medir_explicador.py` | La medición |
| `rubrica.md` | Criterios de calidad para la revisión a ciegas |
| `revision_ciega.py` | Arma las planillas a ciegas (`exportar`) y las junta y revela (`puntuar`) |
| `resultados/<fecha>/` | Lo que deja cada medición: `metricas.json`, `respuestas.json` y `resumen.md`, y después de la revisión, `revision/` |

## Cómo repetir la medición

1. Instala QAgent en modo editable (`pip install -e .[dev]`) y pon en `~/.qagent/.env` la clave de cada proveedor que quieras medir. El script busca primero la clave propia del Explicador (`<PROVEEDOR>_API_KEY_EXPLICADOR`) y después la del proveedor, igual que la aplicación. Ninguna clave se escribe en los resultados.
2. Quita `QAGENT_FAKE_LLM` del sistema y de `.env`. Con la IA simulada el script funciona igual, pero las cifras salen marcadas [SIMULADO] y no sirven para decidir.
3. Opcional, para medir cuánto suma el Explicador al costo de una corrida: abre `bench/` en QAgent, haz una corrida del perfil Estándar con la IA real y guarda la ruta de su `.qagent/runs/<run_id>/log.json`.
4. Desde la raíz del repositorio:

   ```bash
   python bench_explicador/medir_explicador.py --log-corrida bench/.qagent/runs/<run_id>/log.json
   ```

   Opciones:

   - `--modelos planner reviewer`: qué modelos probar, por el agente de `config.toml` que lo usa (por omisión, todos los distintos; con `modo = "ia"` también el de `[agentes.explicador]`).
   - `--repeticiones 3`: cuántas veces se explica cada hallazgo con cada modelo.
   - `--tiempo-maximo 60`: segundos por explicación. Al vencer, se usa la plantilla y cuenta como descarte `tiempo_agotado`.
   - `--salida <carpeta>`: dónde dejar los resultados (por omisión, `resultados/<fecha>/`).
   - `--config-local <archivo>`: otro `config.local.toml` (por omisión, `~/.qagent/config.local.toml`, como la aplicación).

5. Revisa `resumen.md` y versiona la carpeta de `resultados/` en el PR.

Costo esperado: 6 hallazgos × 3 repeticiones por modelo, con unos 1 000 a 3 000 tokens de entrada cada uno. Con los precios de `config.toml` son centavos de dólar. Además, el Explicador corta solo antes de pasar `max_tokens_por_corrida` o `tope_por_corrida_usd`.

## Qué mide

Por explicación y por corrida (una corrida = los 6 hallazgos de `casos/`), por modelo y para la plantilla:

- tokens de entrada y salida, costo en USD y latencia (p50 y p95);
- porcentaje de respuestas descartadas, por motivo. Cada descarte deja la plantilla en su lugar:

  | Motivo | Cuándo |
  |---|---|
  | `json_invalido` | La respuesta no es un objeto JSON o le falta una clave |
  | `decision_distinta` | `decision` no coincide con `results.json` o no es un valor válido |
  | `relaja_asercion` | Propone relajar una aserción o cambiar el valor esperado |
  | `tiempo_agotado` | El LLM no respondió en `--tiempo-maximo` |
  | `presupuesto` | Se habría pasado `max_tokens_por_corrida` o el tope en USD |
  | `error_llm` | Error del proveedor o de red |
  | `contrato_invalido` | Otro incumplimiento de `explanation.v1` |

- con `--log-corrida`, qué porcentaje del costo total de la corrida es el Explicador.

Comprobaciones que hace siempre:

- **Entrada limpia:** antes de enviar cada hallazgo revisa que la entrada (`entrada_ia`) no tenga rutas absolutas ni nada que `sanitizar_secretos` reconozca como clave. Si lo encuentra, se detiene sin enviarlo.
- **Topes:** cada corrida usa los topes de `[presupuesto]` y el resumen indica si se respetaron. Además repite la corrida con `max_tokens_por_corrida = 1` y con un tope de US$ 0,000000001, con un cliente que falla si lo llaman, para comprobar que el Explicador corta **antes** de llamar al LLM.
- **Resultados sin claves:** todo lo que escribe pasa por `sanitizar_secretos`.

## Revisión a ciegas de la calidad

La calidad la revisan al menos dos integrantes con `rubrica.md`, comparando plantilla e IA sin saber cuál es cuál.

1. Quien coordina arma una planilla por persona a partir de la medición:

   ```bash
   python bench_explicador/revision_ciega.py exportar bench_explicador/resultados/<fecha> --revisores ana rodrigo
   ```

   Esto deja en `resultados/<fecha>/revision/` un archivo `planilla-<nombre>.csv` por persona (separado por `;`, en UTF-8; se abre en Excel o en Google Sheets) y `clave.json`.

   - Cada fila es un hallazgo con su columna **Hechos** (decisión, documentación, casos y cada intento con su error) y dos explicaciones, **A** y **B**: la de la plantilla y la de un modelo, en orden al azar.
   - Se usa la repetición 1 de cada modelo (`--repeticion` elige otra). Las explicaciones de IA descartadas no entran, porque en la corrida real se habría mostrado la plantilla; quedan anotadas en `clave.json`.
   - **`clave.json` no se comparte** con quienes revisan: es lo que revela cuál era cada explicación.

2. Cada persona llena su planilla por su cuenta: un 1, un 2 o un 3 en cada criterio de A y de B, y `A`, `B` o `igual` en **preferida**. La guarda con el mismo nombre, en CSV y con `;` como separador.
3. Con todas las planillas en `revision/`:

   ```bash
   python bench_explicador/revision_ciega.py puntuar bench_explicador/resultados/<fecha>
   ```

   Si a una planilla le falta algo, el script dice qué celda. Si está todo, deja `resultado.json` y `resultado.md` con el promedio de cada criterio por modelo y para la plantilla, la cantidad de 1 en «no inventa» y «no contradice», las preferencias y el acuerdo entre quienes revisaron.

4. Versiona la carpeta `revision/` completa, con las planillas y `clave.json`.

## Cómo se marcan las cifras

Con el mismo criterio que el ADR-008:

- **[MEDIDO]:** salió de esta medición con un LLM real, con los tokens que informó el proveedor.
- **[ESTIMADO]:** el proveedor no informó tokens y se calcularon como caracteres / 4.
- **[SIMULADO]:** IA simulada (0 tokens). Solo prueba que el script funciona.
