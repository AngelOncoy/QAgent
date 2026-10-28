"""Modelos Pydantic de los casos límite (TA-16)."""
from typing import Annotated, Optional

import pydantic
from pydantic import BaseModel, Field


class Base(BaseModel):
    """Modelo base."""
    id: int
    creado: str = "hoy"


class Usuario(Base):
    '''Usuario con restricciones.'''
    nombre: str = Field(..., min_length=1, max_length=50)
    edad: int = Field(18, ge=0, lt=150)
    correo: Optional[str] = Field(default=None, pattern=r"^\S+@\S+$")
    etiquetas: list[str] = Field(default_factory=list)
    puntaje: Annotated[float, Field(gt=0.0, multiple_of=0.5)] = 1.0
    saldo: float = Field(-1.5, le=1e6)
    activo: bool = True
    id: int = Field(0, ge=-1)


class Pedido(pydantic.BaseModel):
    usuario: Usuario
    articulos: list["Articulo"] = []
    nota: "Optional[str]" = None
    total: float = Field(default=0, ge=0)


class Articulo(BaseModel):
    nombre: str
    precio: float = Field(gt=0)


class NoModelo:
    campo: int = 1


class DeNoModelo(NoModelo):
    otro: int
