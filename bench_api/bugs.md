# Bugs sembrados en `api_mvp.py`

API de prueba de EP-09: 6 endpoints, 3 correctos y 3 con un bug a propósito. El oráculo de cada uno sale de lo que la ruta declara (`status_code`, `response_model`, modelos Pydantic) o de su docstring, nunca de ejecutarla.

| Endpoint | Qué promete | Bug | Prueba que lo detecta |
|---|---|---|---|
| `GET /salud` | 200 y `{"estado": "ok"}` | — | — |
| `POST /items` | 201 y el artículo con su `id`; 422 si `precio` ≤ 0 o `nombre` vacío | — | — |
| `GET /items` | 200 y la lista de artículos | — | — |
| `GET /items/{item_id}` | 404 si el artículo no existe (docstring) | **1.** Devuelve el resultado de `repo.obtener()` sin revisar si es `None`: FastAPI no puede validar `None` contra `Item` y falla con un error 500 en vez de 404 | Pedir un id que no existe y esperar 404 |
| `DELETE /items/{item_id}` | 204 sin cuerpo (`status_code=204`); 404 si no existe | **2.** Devuelve un `JSONResponse`, que reemplaza el 204 por 200 con cuerpo | Borrar un artículo existente y esperar 204 |
| `GET /descuento` | `precio=100`, `porcentaje=20` → `{"precio_final": 80}` (docstring) | **3.** `calcular_descuento` devuelve el monto del descuento (20), no el precio final | Comparar `precio_final` con 80 |

Necesita solo `fastapi` (ver `requirements.txt`); el sandbox ya trae `httpx` para `TestClient`.
