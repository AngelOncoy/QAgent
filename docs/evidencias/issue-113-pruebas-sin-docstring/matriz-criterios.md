# Matriz de criterios de aceptación — issue #113

| Criterio | Estado | Evidencia |
|---|---|---|
| Analizar funciones sin docstring | Cumplido | `test_analizador_conserva_funcion_sin_docstring` |
| Planificar sin docstring cuando hay tipos suficientes | Cumplido | casos `-> None` y `Literal['ok']` |
| Planificar errores deducibles de la firma | Cumplido | `TypeError` por argumentos faltantes |
| No aceptar una docstring inexistente como origen | Cumplido | tres variantes de `get_siamese_model` |
| No inventar resultados desde la firma | Cumplido | resultado funcional arbitrario descartado |
| No usar tipos ausentes | Cumplido | `origen: tipo` sin anotación se descarta |
| Mantener `planner_contract.v2` | Cumplido | schema sin cambios y contratos validados |
| Conservar objetivos válidos independientes | Cumplido | se omite modelo y se conserva `limpiar_cache` |
| Diferenciar JSON inválido de falta de oráculo | Cumplido | error recuperable frente a `omitidas` |
| Mantener perfil Humo | Cumplido | no convierte un error en prueba funcional |
| Compatibilidad Planner → Generator → Reviewer | Cumplido | test integrado sin Docker |
| Mantener Assertion Laundering | Cumplido | igualdad degradada a `is not None` detectada |
| Mantener regresiones históricas | Cumplido | 1456 pruebas aprobadas |
| Evitar IA real | Cumplido | clientes grabados y `QAGENT_FAKE_LLM=1` |
| Validar directamente APP-RF | Pendiente | proyecto no disponible localmente |
| Inferir constantes o expresiones del cuerpo | Fuera del cambio mínimo | el contrato no posee procedencia AST pública |
