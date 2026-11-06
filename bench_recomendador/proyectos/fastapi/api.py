"""API de inventario con FastAPI."""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()
INVENTARIO: dict[int, dict] = {}


class Articulo(BaseModel):
    nombre: str
    cantidad: int


@app.get("/articulos/{articulo_id}")
def leer_articulo(articulo_id: int) -> dict:
    """Devuelve el artículo o responde 404 si no existe."""
    if articulo_id not in INVENTARIO:
        raise HTTPException(status_code=404, detail="no existe")
    return INVENTARIO[articulo_id]


@app.post("/articulos", status_code=201)
def crear_articulo(articulo: Articulo) -> dict:
    """Crea un artículo nuevo y devuelve su identificador."""
    nuevo_id = len(INVENTARIO) + 1
    INVENTARIO[nuevo_id] = articulo.model_dump()
    return {"id": nuevo_id}


@app.get("/salud")
def salud() -> dict:
    """Indica que el servicio responde."""
    return {"estado": "ok"}
