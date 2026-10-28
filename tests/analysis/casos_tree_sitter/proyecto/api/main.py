import fastapi
from fastapi import FastAPI

from api import rutas
from api.rutas import otro as router_otro

app = FastAPI(title="Casos")
segunda = fastapi.FastAPI()

app.include_router(rutas.router, prefix="/v1")
app.include_router(router_otro, prefix=PREFIJO_DINAMICO)

try:
    from api.extra import extra_router
    app.include_router(extra_router, prefix="/extra")
except ImportError:
    extra_router = None


@app.get("/")
def raiz():
    """Raíz."""
    return {"ok": True}


@app.post("/items/{item_id}", status_code=fastapi.status.HTTP_201_CREATED)
async def crear_item(item_id: str, cantidad: int = 1, *, nombre: str, desc: str | None = None):
    for _ in range(cantidad):
        pass
    return rutas.obtener_db()


@segunda.get("/s")
def en_segunda():
    return calcular()


def calcular():
    return raiz()
