"""Sandbox Docker de QAgent (EN-03): ejecución aislada de pruebas, sin red y con límites.

Paso 1 (con red): `preparar_imagen` instala el requirements.txt del proyecto en una imagen derivada.
Paso 2 (sin red): `ejecutar_pruebas` corre pytest + coverage sobre una copia del proyecto.
"""

from pyagent.sandbox.cliente import obtener_cliente
from pyagent.sandbox.ejecucion import (
    copiar_proyecto,
    ejecutar_en_sandbox,
    ejecutar_pruebas,
)
from pyagent.sandbox.imagen import IMAGEN_BASE, construir_imagen_base, preparar_imagen
from pyagent.sandbox.modelos import (
    LIMITES_POR_DEFECTO,
    DockerNoDisponible,
    ErrorConstruccionImagen,
    ErrorSandbox,
    ImagenNoEncontrada,
    LimitesSandbox,
    ResultadoSandbox,
)

__all__ = [
    "IMAGEN_BASE",
    "LIMITES_POR_DEFECTO",
    "DockerNoDisponible",
    "ErrorConstruccionImagen",
    "ErrorSandbox",
    "ImagenNoEncontrada",
    "LimitesSandbox",
    "ResultadoSandbox",
    "construir_imagen_base",
    "copiar_proyecto",
    "ejecutar_en_sandbox",
    "ejecutar_pruebas",
    "obtener_cliente",
    "preparar_imagen",
]
