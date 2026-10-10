"""Almacenamiento del proyecto (EN-07): `.pyagent/` dentro del proyecto del usuario.

`AlmacenProyecto` guarda y lee corridas, specs y pruebas aprobadas. Todo se escribe de
forma atómica y en UTF-8 (ver `disco`).
"""

from pyagent.almacenamiento.disco import DatoCorrupto, DatoNoEncontrado, ErrorAlmacen
from pyagent.almacenamiento.proyecto import AlmacenProyecto

__all__ = [
    "AlmacenProyecto",
    "DatoCorrupto",
    "DatoNoEncontrado",
    "ErrorAlmacen",
]
