"""Servicio que interactúa con el core bancario externo.

En pruebas unitarias estas funciones NUNCA deben ejecutarse directamente,
sino simularse mediante mocks o stubs.
"""

from __future__ import annotations


def ejecutar_debito(cuenta: str, monto: float) -> str:
    """Debita el monto indicado de la cuenta en el sistema central bancario.

    Args:
        cuenta: Identificador de la cuenta bancaria.
        monto: Monto a debitar (debe ser mayor a 0).

    Returns:
        str: Código único de comprobante de débito (ej. 'DEB-XXXX').

    Raises:
        RuntimeError: Si se ejecuta sin simulación en entorno de prueba.
    """
    raise RuntimeError(
        "Conexión externa no permitida en pruebas unitarias: core bancario no disponible."
    )


def ejecutar_credito(cuenta: str, monto: float) -> str:
    """Acredita el monto indicado a la cuenta en el sistema central bancario.

    Args:
        cuenta: Identificador de la cuenta bancaria destino.
        monto: Monto a acreditar (debe ser mayor a 0).

    Returns:
        str: Código único de comprobante de crédito (ej. 'CRE-XXXX').

    Raises:
        RuntimeError: Si se ejecuta sin simulación en entorno de prueba.
    """
    raise RuntimeError(
        "Conexión externa no permitida en pruebas unitarias: core bancario no disponible."
    )
