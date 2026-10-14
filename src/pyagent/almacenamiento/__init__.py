"""Almacenamiento del proyecto (EN-07): `.qagent/` dentro del proyecto del usuario.

`AlmacenProyecto` guarda y lee corridas, specs y pruebas aprobadas. Todo se escribe de
forma atómica y en UTF-8 (ver `disco`).
"""

from pyagent.almacenamiento.disco import DatoCorrupto, DatoNoEncontrado, ErrorAlmacen
from pyagent.almacenamiento.proyecto import (
    AlmacenProyecto,
    id_de_modulo,
    id_de_spec,
    nombre_prueba,
    nombre_spec_modulo,
)

__all__ = [
    "AlmacenProyecto",
    "DatoCorrupto",
    "DatoNoEncontrado",
    "ErrorAlmacen",
    "id_de_modulo",
    "id_de_spec",
    "nombre_prueba",
    "nombre_spec_modulo",
]
