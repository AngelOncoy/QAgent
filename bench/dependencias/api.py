"""API FastAPI con dependencias entre archivos."""

from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI, HTTPException, status

from bench.dependencias.modelos import (
    RespuestaTransferencia,
    SolicitudTransferencia,
)
from bench.dependencias.procesador_pagos import procesar_transferencia
from bench.dependencias.repositorio import (
    RepositorioTransferencias,
    obtener_repositorio,
)

app = FastAPI(title="API de Transferencias")
router = APIRouter(prefix="/transferencias", tags=["transferencias"])


@router.post("", response_model=RespuestaTransferencia, status_code=status.HTTP_201_CREATED)
def crear_transferencia(
    solicitud: SolicitudTransferencia,
    repo: RepositorioTransferencias = Depends(obtener_repositorio),
) -> RespuestaTransferencia:
    """Crea y ejecuta una transferencia entre cuentas.

    Valida la solicitud, procesa los débitos/créditos a través de la lógica
    de negocio inter-archivo y persiste la transacción en el repositorio.
    """
    try:
        resultado = procesar_transferencia(
            solicitud.cuenta_origen,
            solicitud.cuenta_destino,
            solicitud.monto,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    repo.guardar(resultado["transaccion_id"], resultado)

    return RespuestaTransferencia(
        transaccion_id=resultado["transaccion_id"],
        estado=resultado["estado"],
        codigo=f"{resultado['codigo_origen']}-{resultado['codigo_destino']}",
        monto=resultado["monto"],
    )


app.include_router(router)
