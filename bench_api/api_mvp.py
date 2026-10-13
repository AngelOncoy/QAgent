"""API de prueba de QAgent (EP-09): artículos en memoria, con 3 bugs sembrados.

Banco para medir las pruebas de endpoints FastAPI, como ``bench/banco_mvp.py``
para las funciones. Cada endpoint declara lo que promete (estado, modelo de
respuesta, docstring); tres de ellos no lo cumplen a propósito. Los bugs están
listados en ``bugs.md``.

No necesita base de datos ni red: los artículos se guardan en un repositorio en
memoria que se entrega con ``Depends``, así las pruebas pueden reemplazarlo con
``app.dependency_overrides``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


class ItemEntrada(BaseModel):
    """Datos para crear un artículo."""

    nombre: str = Field(min_length=1, max_length=50)
    precio: float = Field(gt=0)


class Item(ItemEntrada):
    """Artículo guardado, con su identificador."""

    id: int


class Repositorio:
    """Guarda los artículos en memoria."""

    def __init__(self) -> None:
        self._items: dict[int, Item] = {}

    def crear(self, datos: ItemEntrada) -> Item:
        item = Item(id=len(self._items) + 1, **datos.model_dump())
        self._items[item.id] = item
        return item

    def listar(self) -> list[Item]:
        return list(self._items.values())

    def obtener(self, item_id: int) -> Item | None:
        return self._items.get(item_id)

    def borrar(self, item_id: int) -> bool:
        return self._items.pop(item_id, None) is not None


_REPOSITORIO = Repositorio()


def obtener_repositorio() -> Repositorio:
    """Dependencia: el repositorio de artículos de la aplicación."""
    return _REPOSITORIO


def calcular_descuento(precio: float, porcentaje: float) -> float:
    """Precio final tras aplicar un descuento porcentual.

    Ejemplo: precio 100 con 20 % de descuento devuelve 80.
    """
    return precio * (porcentaje / 100)  # BUG 3: devuelve el descuento, no el precio final


app = FastAPI(title="API de prueba de QAgent")
router = APIRouter(prefix="/items", tags=["items"])


@app.get("/salud")
def salud() -> dict[str, str]:
    """Indica que la API está en línea: devuelve {"estado": "ok"}."""
    return {"estado": "ok"}


@router.post("", response_model=Item, status_code=status.HTTP_201_CREATED)
def crear_item(
    datos: ItemEntrada, repo: Repositorio = Depends(obtener_repositorio)
) -> Item:
    """Crea un artículo y lo devuelve con su id. Un precio menor o igual a 0 da 422."""
    return repo.crear(datos)


@router.get("", response_model=list[Item])
def listar_items(repo: Repositorio = Depends(obtener_repositorio)) -> list[Item]:
    """Devuelve todos los artículos guardados."""
    return repo.listar()


@router.get("/{item_id}", response_model=Item)
def obtener_item(item_id: int, repo: Repositorio = Depends(obtener_repositorio)):
    """Devuelve el artículo con ese id; responde 404 si no existe."""
    return repo.obtener(item_id)  # BUG 1: no responde 404 cuando el artículo no existe


@router.delete("/{item_id}", status_code=204)
def borrar_item(item_id: int, repo: Repositorio = Depends(obtener_repositorio)):
    """Borra el artículo: responde 204 sin cuerpo, o 404 si no existe."""
    if not repo.borrar(item_id):
        raise HTTPException(status_code=404, detail="Artículo no encontrado")
    return JSONResponse({"borrado": item_id})  # BUG 2: responde 200 con cuerpo, no 204


@app.get("/descuento")
def descuento(
    precio: float = Query(gt=0), porcentaje: float = Query(ge=0, le=100)
) -> dict[str, float]:
    """Precio final con descuento: precio=100 y porcentaje=20 devuelve {"precio_final": 80}."""
    return {"precio_final": calcular_descuento(precio, porcentaje)}


app.include_router(router)
