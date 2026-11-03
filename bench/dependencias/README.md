# Banco de pruebas con dependencias entre archivos (SPK #196)

Banco de pruebas diseñado para medir el impacto del contexto de dependencias entre archivos (alternativa a Graphify) en QAgent.

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
   - Con el contexto actual de QAgent, los endpoints reciben `contexto: None` en el prompt del Generator. Por ende, el Generator no sabe que se invocan funciones de otros archivos y no genera ningún `mock.patch`. Al ejecutarse con `TestClient`, se dispara la llamada real a `ejecutar_debito` y la prueba falla.
