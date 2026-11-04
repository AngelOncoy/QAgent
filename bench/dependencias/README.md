# Banco de pruebas con dependencias entre archivos (SPK-196 / ADR-012)

Banco de pruebas diseñado para medir el impacto del contexto de dependencias entre archivos con tree-sitter (`grafo_imports.py`) frente a Graphify en QAgent (registrado en **ADR-012**).

## Estructura de archivos y flujo de dependencias

```
bench/dependencias/
├── __init__.py
├── modelos.py            <- Modelos Pydantic (Transaccion, SolicitudTransferencia, RespuestaTransferencia)
├── servicio_banco.py     <- Simula core bancario externo (ejecutar_debito, ejecutar_credito); lanza RuntimeError si se ejecuta real
├── procesador_pagos.py   <- Lógica de negocio / FUNCIÓN a probar (procesar_transferencia); llama a servicio_banco y modelos
├── repositorio.py        <- Dependencia inyectable (RepositorioTransferencias, obtener_repositorio)
└── api.py                <- ENDPOINT FastAPI a probar (POST /transferencias); llama a procesador_pagos y repositorio
```

## Por qué este caso expone el problema (GitHub #196)

1. **La función (`procesar_transferencia`)**:
   - Depende de `ejecutar_debito` y `ejecutar_credito` definidos en `servicio_banco.py`.
   - Si el Generator no tiene el contexto de `servicio_banco.py`:
     - O no los simula (dejando la llamada real que falla con `RuntimeError`), o
     - Inventa valores de retorno arbitrarios (por ejemplo un booleano `True` o un diccionario `{"ok": True}` en vez de un código de referencia `str`), lo que provoca fallos de tipo o falsos positivos.

2. **El endpoint (`crear_transferencia` / `POST /transferencias`)**:
   - Declara una inyección `Depends(obtener_repositorio)`.
   - Pero internamente delega en `procesar_transferencia` de otro archivo, que a su vez llama a `servicio_banco.py`.
   - Sin contexto inter-archivo, los endpoints reciben `contexto: None` en el prompt del Generator. Por ende, el Generator no sabe que se invocan funciones de otros archivos y no genera ningún `mock.patch`. Al ejecutarse con `TestClient`, se dispara la llamada real a `ejecutar_debito` y la prueba falla.

## Solución adoptada: Grafo de imports con tree-sitter (ADR-012)

- `grafo_imports.py` extrae estáticamente las firmas tipadas y docstrings de las dependencias importadas en **~27–36 ms** con **0 tokens consumidos** en el análisis.
- Las pruebas pasan del **60 % al 100 %** (5 de 5 aprobadas, 0 dependencias sin simular).
- **Graphify queda descartado definitivamente (ADR-012):** requería ejecutar subprocesos host fuera del sandbox, pedía `tree-sitter >= 0.25` incompatible con QAgent, añadía +31 dependencias y tardaba > 1 250 ms.
