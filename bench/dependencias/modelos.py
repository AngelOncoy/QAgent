"""Modelos de datos para el caso con dependencias entre archivos."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Transaccion(BaseModel):
    """Modelo de datos de una transacción procesada."""

    id: str
    cuenta_origen: str
    cuenta_destino: str
    monto: float
    codigo_autorizacion: str
    exitoso: bool


class SolicitudTransferencia(BaseModel):
    """Datos de entrada para solicitar una transferencia."""

    cuenta_origen: str = Field(min_length=4, max_length=20)
    cuenta_destino: str = Field(min_length=4, max_length=20)
    monto: float = Field(gt=0)


class RespuestaTransferencia(BaseModel):
    """Respuesta devuelta tras realizar una transferencia."""

    transaccion_id: str
    estado: str
    codigo: str
    monto: float
