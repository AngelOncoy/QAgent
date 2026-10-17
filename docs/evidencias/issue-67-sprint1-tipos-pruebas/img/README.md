# Capturas pendientes — issue #67

Esta carpeta no contiene capturas porque la ejecución automatizada de la Fase 4 no
dispone de control interactivo del escritorio. Deben obtenerse desde una sesión real
de QAgent. No se deben recrear interfaces ni resultados.

## Preparación segura

1. Mantener la rama `feat/sprint1-tipos-pruebas-qagent` y el árbol de trabajo actual.
2. Definir `QAGENT_FAKE_LLM=1` antes de iniciar `qagent`.
3. Usar únicamente un proyecto sintético sin datos privados.
4. No abrir ni capturar `.env`, claves, tokens o rutas personales innecesarias.
5. Confirmar visualmente que la aplicación indica el modo simulado.

## Capturas solicitadas

| Archivo sugerido | Contenido auténtico que debe mostrar |
|---|---|
| `CAP-01-configuracion-sprint1.png` | Pantalla Configuración de pruebas del Sprint 1. |
| `CAP-02-cuatro-tipos.png` | Las cuatro opciones visibles simultáneamente. |
| `CAP-03-unitarias.png` | Solo Unitarias seleccionada. |
| `CAP-04-limites.png` | Solo Valores límite seleccionada. |
| `CAP-05-humo.png` | Solo Humo seleccionada. |
| `CAP-06-regresion.png` | Solo Regresión seleccionada. |
| `CAP-07-ejecucion-simulada.png` | Ejecución con FakeLLMClient identificada como simulada. |
| `CAP-08-resultados-estrategia.png` | Resultados con la estrategia registrada. |
| `CAP-09-historial-informe.png` | Historial o Informe mostrando el tipo de prueba. |
| `CAP-10-pruebas-automatizadas.png` | Terminal real con la suite rápida aprobada. |

Después de tomar las capturas se debe revisar cada imagen, calcular su SHA-256 con
`Get-FileHash -Algorithm SHA256`, actualizar `evidencias_sha256.json` y enlazar solo
los archivos que realmente existan desde el informe.
