# ADR-012: Contexto de dependencias inter-archivo con tree-sitter frente a Graphify

- **Estado:** Aceptado
- **Fecha:** 2026-11-03
- **Ítem:** SPK-196 / TA de #196 (#223, #231) — Contexto de dependencias entre archivos y descarte definitivo de Graphify
- **Responsable:** Equipo QAgent
- **Relacionado:** ADR-002 (mapa de código y Graphify), ADR-007 (adaptadores por lenguaje, EN-17), ADR-009 (parser por lenguaje: tree-sitter), ADR-010 (arquitectura del Sprint 2), ADR-013 (versión de Python del sandbox), `docs/arquitectura.md`, `AGENTS.md`, `bench/dependencias/`

---

## 1. Contexto

En el PR #223 (#196) se abordó el enriquecimiento de contexto para el Generator de Python en proyectos modulares donde las funciones y endpoints delegan en módulos y paquetes internos del repositorio (ver `bench/dependencias/`).

En estos proyectos modulares, el análisis intra-módulo tradicional dejaba dos brechas críticas:
1. **Funciones de negocio:** La función a probar (por ejemplo, `procesar_transferencia`) importa e invoca funciones de otro archivo (por ejemplo, `ejecutar_debito` y `ejecutar_credito` en `servicio_banco.py`). Sin el contexto del módulo importado, el Generator o no simulaba las llamadas (haciendo que fallen en tiempo de ejecución con excepciones reales como `RuntimeError` del core bancario) o inventaba tipos de retorno incompatibles, reduciendo la tasa de aprobación de pruebas en `bench/dependencias/` al **60 % (3 de 5)**.
2. **Endpoints de FastAPI:** Los endpoints (`crear_transferencia` en `api.py`) delegan en servicios de otros archivos que a su vez realizan llamadas externas. Dado que los endpoints no recibían el contexto del módulo, las pruebas con `TestClient` disparaban la ejecución de servicios sin simular y fallaban con error 500.

El PR #223 introdujo una implementación híbrida en `graphify_dependencias.py` que intentaba ejecutar Graphify (`graphify update --no-cluster`) con fallback a un análisis estático de imports propio implementado en `grafo_imports.py` mediante tree-sitter.

Sin embargo, el análisis posterior de la implementación reveló que Graphify nunca aportó a la mejora real, agregaba riesgos severos de seguridad e incompatibilidad técnica, y contradecía las reglas inquebrantables del proyecto.

---

## 2. Pregunta

¿Cómo suministrar al Generator el contexto de dependencias y firmas entre archivos sin ejecutar código del usuario, con 0 tokens en la fase de análisis estático, latencia inferior a 50 ms y sin comprometer la seguridad ni la portabilidad de QAgent?

---

## 3. Opciones evaluadas

| Opción | Descripción | A favor | En contra |
|---|---|---|---|
| **A. Integrar Graphify** | Ejecutar el binario `graphify` (o buscarlo en el `.venv` del usuario) para generar `graphify-out/graph.json` y consultar el grafo relacional. | Reutiliza una herramienta de grafos existente. | Ejecuta binarios fuera del sandbox, modifica el código del usuario, pide `tree-sitter >= 0.25`, añade +31 dependencias, tarda > 1 250 ms y gasta tokens si usa clustering. |
| **B. Grafo estático propio con tree-sitter (`grafo_imports`)** | Resolver los imports de Python estáticamente con tree-sitter, extraer firmas tipadas y docstrings de los símbolos llamados, e inyectarlos en el prompt. | **0 tokens**, **~27–36 ms**, 0 dependencias nuevas, determinista, 100 % seguro (sin subprocesos en la máquina del usuario). | Requiere mantener la resolución de imports en el adaptador de Python (extender a JS/TS y Java en tareas futuras). |
| **C. No proveer contexto inter-archivo** | Mantener solo el contexto local del módulo actual (`contexto_de_funcion`). | No agrega código. | Tasa de fallo del 40 % en proyectos modulares por dependencias externas sin simular. |

---

## 4. Comparación Técnica y Mediciones Empíricas (SPK-196 / TA de #196)

Las opciones se evaluaron de forma reproducible mediante `bench/dependencias/medir_dependencias_spk196.py` sobre el banco modular `bench/dependencias/`:

| Métrica | Contexto Actual (Sin Grafo) | Prototipo Tree-sitter (`grafo_imports`) | Graphify (Modo Estructural / Semántico) |
|---|:---:|:---:|:---:|
| **Aprobadas / Total** | 3/5 (**60.0 %**) | 5/5 (**100.0 %**) | 5/5 (vía el mismo fallback TS o variable) |
| **Dependencias sin simular** | 2 | **0** | 0–1 |
| **Falsos positivos** | 0 | **0** | No garantizado |
| **Tokens consumidos en análisis** | 0 | **0 tokens** | 0 (--no-cluster) a 8,600 tokens (semántico) |
| **Tiempo de análisis del grafo** | ~1.5 ms | **27–36 ms** | ~1,250 ms a ~12,225 ms (> 30x más lento) |
| **Tokens extra en prompt Generator** | 0 | **+~120–300 tokens** | 0 (archivo externo) o similar |
| **Dependencias externas añadidas** | 0 | **0** (usa tree-sitter ya fijado) | **+31 paquetes** (`networkx`, `scikit-learn`, etc.) |
| **Compatibilidad con `tree-sitter`** | Compatible | Compatible (**0.24**, ADR-009) | **Incompatible** (exige `tree-sitter >= 0.25`) |
| **Subprocesos en PC del host** | Ninguno | **Ninguno** | Sí (`graphify update` en host) |

### Hallazgos clave:
1. **La mejora de 60 % a 100 % provino 100 % de `grafo_imports.py` (tree-sitter):** Graphify nunca estuvo en `pyproject.toml` ni en el empaquetado de Windows (`packaging/windows/`), por lo que en ejecuciones de prueba o instalaciones reales cada llamada terminaba en el fallback de tree-sitter.
2. **Latencia y recursos:** Tree-sitter analiza la recursión de imports y extrae firmas tipadas en ~27–36 ms para el banco completo, frente a más de 1 250 ms de Graphify sin clustering (y más de 12 segundos con clustering).

---

## 5. Riesgos de Seguridad y Motivos del Descarte Definitivo de Graphify

La integración de Graphify presentó riesgos graves que motivaron su eliminación inmediata:

1. **Ejecución arbitraria en la máquina del usuario (Violación crítica de AGENTS.md):**
   `encontrar_ejecutable_graphify` buscaba activamente `graphify.exe` en `.venv/Scripts/` o carpetas `venv/` dentro del repositorio del proyecto analizado y lo ejecutaba mediante `subprocess.run` en la máquina anfitriona fuera del contenedor Docker. Si un repositorio malicioso o descargado incluía un binario o script troyanizado con ese nombre, QAgent lo ejecutaba con los privilegios del usuario. La regla inquebrantable de AGENTS.md establece:
   > *«Nunca ejecutar código del usuario ni tests generados fuera del sandbox. El análisis del código del usuario es solo estático.»*
2. **Confianza ciega en artefactos no verificados:**
   `asegurar_grafo_json` leía y confiaba directamente en cualquier archivo `graphify-out/graph.json` existente en el repositorio del usuario sin saneamiento previo.
3. **Modificación indeseada del espacio de trabajo del usuario:**
   `graphify update` escribe la carpeta `graphify-out/` dentro del código del usuario, violando el principio de que el análisis estático no debe alterar el proyecto analizado.
4. **Conflicto de dependencias en el ecosistema:**
   Graphify exige `tree-sitter >= 0.25`, lo que rompe las versiones fijadas en QAgent (`tree-sitter 0.24`, ADR-009) y requeriría arrastrar más de 30 librerías pesadas (como `scikit-learn` y `networkx`) en el instalador de Windows.
5. **Incumplimiento de ADRs previos:**
   Tanto el ADR-002 como el ADR-009 estipularon de forma explícita que Graphify quedaba fuera de QAgent. La introducción en #223 violó dicha directriz sin un ADR aprobatorio previo.

---

## 6. Decisión

**Se adopta la Opción B: Grafo estático de dependencias e imports con tree-sitter (`grafo_imports.py`). Graphify queda total y definitivamente descartado y eliminado de QAgent.**

Se aplican las siguientes medidas técnicas:

1. **Eliminación completa de Graphify:**
   - Se elimina el módulo `src/qagent/analysis/graphify_dependencias.py`.
   - Se eliminan las pruebas exclusivas de Graphify en `tests/analysis/test_graphify_dependencias.py`.
   - Se quita `graphify-out` de `DIRECTORIOS_IGNORADOS` en `src/qagent/analysis/analyzer.py` y de `.gitignore`.
2. **Consumo directo en el Generator:**
   - `src/qagent/lenguajes/python_generacion.py` invoca directamente `construir_grafo_dependencias` y `formatear_contexto_grafo` de `qagent.analysis.grafo_imports`.
   - No queda ningún subproceso, búsqueda de binarios en `.venv` ni lectura de archivos `graph.json`.
3. **Eliminación de la caché en disco:**
   - Dado que el análisis estático con tree-sitter tarda entre ~1.5 ms y ~36 ms, no se justifica el costo de invalidación de caché ni la persistencia de `graph_cache.json` en `.qagent/`. El grafo se calcula en memoria durante la generación del prompt.
4. **Formulación precisa de la regla del prompt:**
   - El encabezado del bloque en el prompt deja de decir *«detectadas con Graphify»* y pasa a:
     `DEPENDENCIAS INTERNAS DEL PROYECTO (firmas estáticas extraídas con tree-sitter):`
   - La regla para mocks establece:
     `REGLA: Usa las firmas y tipos anteriores para configurar retornos de mocks coherentes con el negocio.`
     `Simula servicios externos y efectos (red, base de datos, servicios como el core bancario); no simules funciones puras internas.`
5. **Verificación de seguridad:**
   - Se añade una prueba unitaria específica que garantiza que la presencia de un archivo `.venv/Scripts/graphify.exe` en el proyecto analizado no sea ejecutada bajo ninguna circunstancia.

---

## 7. Consecuencias

### Positivas
- **100 % de efectividad en proyectos modulares:** La suite `bench/dependencias/` mantiene 5/5 pruebas aprobadas y 0 dependencias sin simular.
- **Seguridad garantizada:** Cero subprocesos fuera del sandbox; el análisis de código del usuario sigue siendo 100 % estático e inofensivo.
- **Rendimiento:** Tiempos de análisis imperceptibles (< 36 ms) y 0 tokens gastados en el análisis del grafo.
- **Simplicidad arquitectural:** Se eliminan archivos redundantes, cachés innecesarias y dependencias ficticias. Cumplimiento estricto de AGENTS.md, ADR-002 y ADR-009.

### Trabajo futuro
- Llevar la resolución de grafos de imports y dependencias a los adaptadores de JavaScript/TypeScript y Java en sus respectivos ítems de backlog (ADR-007).
