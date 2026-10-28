from ... import servicios
from .. import desde_paquete


def ayuda(n: int) -> int:
    """Ayuda."""
    return n + desde_paquete() + servicios.validar()
