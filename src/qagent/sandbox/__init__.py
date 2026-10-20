"""Sandbox Docker de QAgent (EN-03): ejecución aislada de pruebas, sin red y con límites.

Paso 1 (con red): `preparar_imagen` instala el requirements.txt del proyecto en una imagen derivada.
Paso 2 (sin red): `ejecutar_pruebas` corre pytest + coverage sobre una copia del proyecto.
Mutation testing (EN-09): `ejecutar_mutacion` corre mutmut solo sobre las funciones críticas.
"""

from qagent.sandbox.cliente import obtener_cliente
from qagent.sandbox.ejecucion import (
    clasificar_resultado,
    comando_pytest,
    copiar_proyecto,
    ejecutar_en_sandbox,
    ejecutar_pruebas,
)
from qagent.sandbox.estado import estado_docker, verificar_docker
from qagent.sandbox.imagen import IMAGEN_BASE, construir_imagen_base, preparar_imagen
from qagent.sandbox.informe_pytest import (
    CasoPrueba,
    InformePytest,
    JUnitInvalido,
    parsear_junit,
    recortar_salida,
    resumir_ejecucion,
)
from qagent.sandbox.modelos import (
    LIMITES_POR_DEFECTO,
    MENSAJE_DOCKER_CERRADO,
    DockerNoDisponible,
    ErrorConstruccionImagen,
    ErrorSandbox,
    ImagenNoEncontrada,
    LimitesSandbox,
    ResultadoSandbox,
)
from qagent.sandbox.mutacion import (
    MutacionFuncion,
    ResultadoMutacion,
    Sobreviviente,
    ejecutar_mutacion,
)

__all__ = [
    "IMAGEN_BASE",
    "LIMITES_POR_DEFECTO",
    "MENSAJE_DOCKER_CERRADO",
    "CasoPrueba",
    "DockerNoDisponible",
    "ErrorConstruccionImagen",
    "ErrorSandbox",
    "ImagenNoEncontrada",
    "InformePytest",
    "JUnitInvalido",
    "LimitesSandbox",
    "MutacionFuncion",
    "ResultadoMutacion",
    "ResultadoSandbox",
    "Sobreviviente",
    "clasificar_resultado",
    "comando_pytest",
    "construir_imagen_base",
    "copiar_proyecto",
    "ejecutar_en_sandbox",
    "ejecutar_mutacion",
    "ejecutar_pruebas",
    "estado_docker",
    "obtener_cliente",
    "parsear_junit",
    "preparar_imagen",
    "recortar_salida",
    "resumir_ejecucion",
    "verificar_docker",
]
