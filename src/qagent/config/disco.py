"""Límites de espacio en disco del sandbox (#267), leídos de `[disco]` de config.toml.

Los umbrales viven solo en `config.toml` (los cambia el equipo, no el usuario: `disco`
está en `SECCIONES_SOLO_EQUIPO`). Si la sección falta o un valor no sirve, ese límite
queda en `None` y **no se aplica**: ante la duda, QAgent no borra ni bloquea nada.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - Python 3.10
    import tomli as tomllib

registro = logging.getLogger(__name__)

#: Bytes en un GB como lo muestra Windows (GiB).
BYTES_POR_GB = 1024**3

#: Claves de `[disco]` → qué significan (en el orden en que se documentan).
CLAVES = (
    "tope_imagenes_derivadas_gb",
    "cache_antiguedad_dias",
    "espacio_libre_minimo_gb",
)


@dataclass(frozen=True)
class LimitesDisco:
    """Límites de `[disco]`; `None` en un campo significa que ese límite no se aplica.

    Atributos:
        tope_imagenes_derivadas_gb: espacio total máximo de las imágenes derivadas
            (`req-`, `node-`, `java-`, `browser-`); al superarlo se borran las menos usadas.
        cache_antiguedad_dias: la caché de compilación más vieja que esto se poda.
        espacio_libre_minimo_gb: espacio libre mínimo del disco de Docker para construir
            o descargar una imagen.
    """

    tope_imagenes_derivadas_gb: float | None = None
    cache_antiguedad_dias: float | None = None
    espacio_libre_minimo_gb: float | None = None

    @property
    def tope_imagenes_derivadas_bytes(self) -> int | None:
        return _a_bytes(self.tope_imagenes_derivadas_gb)

    @property
    def espacio_libre_minimo_bytes(self) -> int | None:
        return _a_bytes(self.espacio_libre_minimo_gb)


def _a_bytes(gb: float | None) -> int | None:
    return None if gb is None else int(gb * BYTES_POR_GB)


def leer_limites_disco(
    ruta_config: str | Path | None = None, avisos: list[str] | None = None
) -> LimitesDisco:
    """Lee `[disco]` de `config.toml` sin validar el resto del archivo ni las claves.

    Nunca lanza excepciones. Cada valor que falta o no es un número mayor que 0 queda en
    `None`; el motivo se agrega a `avisos` (si se pasa) y al registro.
    """
    from qagent.config import carga

    ruta = Path(ruta_config) if ruta_config else carga.RUTA_CONFIG
    avisos = avisos if avisos is not None else []
    try:
        datos = tomllib.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        avisos.append(f"No se pudo leer [disco] de {ruta.name}: {error}")
        registro.warning(avisos[-1])
        return LimitesDisco()
    tabla = datos.get("disco")
    if not isinstance(tabla, dict):
        avisos.append("Falta la sección [disco] en config.toml: no se aplican límites.")
        registro.warning(avisos[-1])
        return LimitesDisco()
    return LimitesDisco(*(_numero(tabla, clave, avisos) for clave in CLAVES))


def _numero(tabla: dict[str, Any], clave: str, avisos: list[str]) -> float | None:
    valor = tabla.get(clave)
    if isinstance(valor, bool) or not isinstance(valor, (int, float)) or valor <= 0:
        avisos.append(f"{clave} en [disco] debe ser un número mayor que 0.")
        registro.warning(avisos[-1])
        return None
    return float(valor)
