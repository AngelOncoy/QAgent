from fastapi import APIRouter

extra_router = APIRouter(prefix="/e")


@extra_router.get("/hola")
def hola(nombre: str = "mundo"):
    return nombre
