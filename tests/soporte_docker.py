"""Pruebas con Docker real: cuándo se activan y qué imágenes borran al terminar (#250).

Las pruebas marcadas `docker` tardan varios minutos y construyen varios GB de imágenes,
así que no corren solas aunque Docker Desktop esté abierto: se activan con `--docker`
(`python test.py --docker` o `pytest --docker`) o eligiéndolas con `-m docker`.

Al terminar se borran las imágenes de QAgent que la corrida creó, comparando las de antes y
las de después. Nunca se borran las que ya existían, ni `qagent-sandbox:base`, ni imágenes
de otros repositorios (las que Docker descargó, como `node` o `eclipse-temurin`).
`--conservar-imagenes` las deja para repetir la corrida más rápido.

La lógica es pura y se prueba sin Docker en `tests/test_soporte_docker.py`; los hooks que
la usan están en `tests/conftest.py`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

# IMAGEN_BASE nunca se borra. Las derivadas (PREFIJOS_DERIVADAS) se borran antes que las
# imágenes base de lenguaje, que son su origen.
from qagent.sandbox.limpieza import PREFIJOS_DERIVADAS
from qagent.sandbox.modelos import IMAGEN_BASE, REPOSITORIO

MOTIVO_OMITIDA = "prueba con Docker real: se activa con --docker (python test.py --docker) o -m docker"
AVISO = (
    "Pruebas con Docker real activadas ({n}). Tardan varios minutos (unos 15 con todas)\n"
    "y construyen imágenes que pueden ocupar cerca de 10 GB. Al terminar se borran las\n"
    "que esta corrida creó{conservar}."
)

_NO_DOCKER = re.compile(r"\bnot\s+docker\b")
_DOCKER = re.compile(r"\bdocker\b")


def pruebas_docker_activas(opcion_docker: bool, expresion_m: str = "") -> bool:
    """True si la corrida pidió las pruebas `docker`: con `--docker` o con `-m docker`.

    Una expresión `-m` que solo las excluye (`not docker`) no las activa.
    """
    if opcion_docker:
        return True
    sin_negadas = _NO_DOCKER.sub("", expresion_m or "")
    return bool(_DOCKER.search(sin_negadas))


def texto_aviso(cantidad: int, conservar: bool) -> str:
    """Aviso que se muestra antes de empezar las pruebas `docker`."""
    nota = (
        " (no: --conservar-imagenes las deja para la próxima corrida)"
        if conservar
        else "; --conservar-imagenes las deja para repetir más rápido"
    )
    prueba = "prueba" if cantidad == 1 else "pruebas"
    return AVISO.format(n=f"{cantidad} {prueba}", conservar=nota)


def etiquetas_qagent(cliente: Any) -> set[str]:
    """Etiquetas de las imágenes del repositorio `qagent-sandbox` que hay en Docker."""
    return {
        etiqueta
        for imagen in cliente.images.list(name=REPOSITORIO)
        for etiqueta in imagen.tags
        if etiqueta.startswith(f"{REPOSITORIO}:")
    }


def imagenes_creadas(antes: Iterable[str], despues: Iterable[str]) -> list[str]:
    """Imágenes de QAgent que aparecieron durante la corrida y se pueden borrar.

    Quedan fuera las que ya existían, la imagen base y las de otros repositorios. Las
    derivadas van primero: se crean a partir de las imágenes base de lenguaje.
    """
    previas = set(antes)
    nuevas = {
        etiqueta
        for etiqueta in despues
        if etiqueta not in previas
        and etiqueta.startswith(f"{REPOSITORIO}:")
        and etiqueta != IMAGEN_BASE
    }
    return sorted(nuevas, key=lambda etiqueta: (not _es_derivada(etiqueta), etiqueta))


def borrar_imagenes(
    cliente: Any, etiquetas: Iterable[str]
) -> tuple[list[str], dict[str, str]]:
    """Borra cada imagen; una que no se puede borrar no detiene las demás.

    Returns:
        Las etiquetas borradas y, para las que fallaron, el motivo.
    """
    borradas: list[str] = []
    errores: dict[str, str] = {}
    for etiqueta in etiquetas:
        try:
            cliente.images.remove(etiqueta)
            borradas.append(etiqueta)
        except Exception as exc:  # noqa: BLE001 — en uso o ya borrada: se informa y sigue
            errores[etiqueta] = str(exc)
    return borradas, errores


def _es_derivada(etiqueta: str) -> bool:
    """True si la etiqueta es una imagen derivada por proyecto."""
    tag = etiqueta.removeprefix(f"{REPOSITORIO}:")
    return tag.startswith(PREFIJOS_DERIVADAS)
