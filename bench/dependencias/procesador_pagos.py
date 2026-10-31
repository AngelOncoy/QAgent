"""Lógica de negocio para procesamiento de transferencias y pagos."""

from __future__ import annotations

import uuid
from typing import Any

from bench.dependencias.modelos import Transaccion
from bench.dependencias.servicio_banco import ejecutar_credito, ejecutar_debito


def procesar_transferencia(
    cuenta_origen: str, cuenta_destino: str, monto: float
) -> dict[str, Any]:
    """Procesa una transferencia monetaria entre dos cuentas bancarias.

    Realiza las validaciones de negocio, debita de la cuenta origen y
    acredita en la cuenta destino a través del servicio bancario.

    Args:
        cuenta_origen: Número o código de cuenta de origen (no vacío).
        cuenta_destino: Número o código de cuenta de destino (diferente a origen).
        monto: Importe a transferir, debe ser estrictamente mayor a 0.

    Returns:
        dict: Diccionario con el resultado de la operación:
            - "estado": "COMPLETADA"
            - "transaccion_id": identificador único generado
            - "codigo_origen": código retornado por el débito
            - "codigo_destino": código retornado por el crédito
            - "monto": monto transferido

    Raises:
        ValueError: Si las cuentas son iguales, vacías o si el monto es <= 0.
    """
    if not cuenta_origen or not cuenta_destino:
        raise ValueError("Las cuentas origen y destino son obligatorias.")
    if cuenta_origen == cuenta_destino:
        raise ValueError("La cuenta de origen y destino no pueden ser iguales.")
    if monto <= 0:
        raise ValueError("El monto a transferir debe ser mayor a cero.")

    codigo_debito = ejecutar_debito(cuenta_origen, monto)
    codigo_credito = ejecutar_credito(cuenta_destino, monto)

    tx_id = f"TX-{uuid.uuid4().hex[:8].upper()}"
    transaccion = Transaccion(
        id=tx_id,
        cuenta_origen=cuenta_origen,
        cuenta_destino=cuenta_destino,
        monto=monto,
        codigo_autorizacion=f"{codigo_debito}:{codigo_credito}",
        exitoso=True,
    )

    return {
        "estado": "COMPLETADA",
        "transaccion_id": transaccion.id,
        "codigo_origen": codigo_debito,
        "codigo_destino": codigo_credito,
        "monto": transaccion.monto,
    }
