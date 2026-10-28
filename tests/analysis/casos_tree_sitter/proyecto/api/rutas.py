"""Routers con prefijos, dependencias y excepciones (TA-16)."""
from typing import Annotated

from fastapi import APIRouter, Body, Cookie, Depends, Form, Header, HTTPException, Path, Query, Request, Security, status

from . import modelos
from .modelos import Pedido as PedidoModelo, Usuario
from ..servicios import calcular_total, validar as validar_servicio
from paquete.sub import util

router = APIRouter(prefix="/usuarios", tags=["usuarios"])
otro: APIRouter = APIRouter()
dinamico = APIRouter(prefix=PREFIJO)


def obtener_db():
    return "db"


def usuario_actual(token: str = Header(...)):
    return token


@router.get("/{usuario_id}", response_model=Usuario, status_code=status.HTTP_200_OK)
async def leer_usuario(usuario_id: int, request: Request, db=Depends(obtener_db), detalle: bool = Query(False, description="x")):
    """Lee un usuario."""
    if usuario_id < 0:
        raise HTTPException(status_code=404, detail="No existe")
    if not db:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Sin base")
    return util.ayuda(usuario_id)


@router.post("", response_model=list[modelos.Usuario], status_code=201, dependencies=[Depends(usuario_actual), Security(obtener_db)])
def crear_usuario(usuario: Usuario, x_token: Annotated[str, Header()] = "t", limite: Annotated[int, Query(gt=0, le=100)] = 10, sesion: str = Cookie(None)):
    calcular_total(1)
    validar_servicio()
    return [usuario]


@router.api_route("/varios", methods=["GET", "POST", "OPTIONS"])
def varios(q: Annotated[str | None, Query(min_length=3)] = None):
    return q


@otro.put("/pedidos/{pedido_id}")
def actualizar(pedido_id: Annotated[int, Path(ge=1)], pedido: PedidoModelo, nota: str = Body(..., embed=True), archivo: bytes = Form(b"")):
    try:
        return pedido
    except KeyError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"conflicto {pedido_id}")


@otro.delete(path="/pedidos/{pedido_id}", status_code=204)
def borrar(pedido_id: int, usuario=Depends(usuario_actual), db: str = Depends()):
    raise HTTPException(400)


@dinamico.patch("/x")
def parche():
    return 1


@router.get(RUTA_VARIABLE)
def ruta_variable():
    return 1
