"""Almacenamiento del proyecto (EN-07): `.qagent/` dentro del proyecto del usuario.

`AlmacenProyecto` guarda y lee corridas, specs, pruebas aprobadas y evidencias de bugs.
Todo se escribe de forma atómica y en UTF-8 (ver `disco`).
"""

from qagent.almacenamiento.bloqueo import BloqueoCorrida, corrida_activa
from qagent.almacenamiento.disco import DatoCorrupto, DatoNoEncontrado, ErrorAlmacen
from qagent.almacenamiento.proyecto import (
    AlmacenProyecto,
    huella_de_prueba,
    id_de_modulo,
    id_de_spec,
    nombre_prueba,
    nombre_spec_modulo,
)

__all__ = [
    "AlmacenProyecto",
    "BloqueoCorrida",
    "DatoCorrupto",
    "DatoNoEncontrado",
    "ErrorAlmacen",
    "corrida_activa",
    "huella_de_prueba",
    "id_de_modulo",
    "id_de_spec",
    "nombre_prueba",
    "nombre_spec_modulo",
]
