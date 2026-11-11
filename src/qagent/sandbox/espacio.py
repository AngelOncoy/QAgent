"""Espacio libre del disco que usa Docker (#267, Capa 2).

Docker guarda imágenes y capas en un disco virtual que crece en el disco del equipo
(en Windows, `docker_data.vhdx` en `C:`, y no se achica solo). Si ese disco se llena,
Docker deja de responder. Por eso, antes de construir o descargar una imagen se comprueba
que quede al menos el espacio mínimo de `[disco] espacio_libre_minimo_gb` (config.toml).

Es una comprobación del equipo, no de Docker: no hace falta que Docker responda, y es
determinista (el orquestador solo recibe el resultado, ADR-008). Nunca lanza excepciones
por no poder medir: si no se sabe cuánto queda, no se bloquea nada.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import shutil
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

from qagent.config.disco import BYTES_POR_GB, LimitesDisco, leer_limites_disco
from qagent.sandbox.modelos import EspacioInsuficiente

registro = logging.getLogger(__name__)

#: Claves (en minúsculas) con las que Docker Desktop guarda dónde está el disco de datos.
_CLAVES_AJUSTES = ("customwsldistrodir", "datafolder", "diskpath")


def carpeta_datos_docker(
    entorno: Mapping[str, str] | None = None, plataforma: str | None = None
) -> Path:
    """Carpeta (o su primer padre que exista) del disco donde Docker guarda sus datos.

    En Windows y macOS Docker Desktop corre en una máquina virtual cuyo disco vive en el
    disco del usuario; en Linux, Docker usa `/var/lib/docker`. Si no se puede saber,
    se usa la carpeta personal, que casi siempre está en el mismo disco.
    """
    entorno = os.environ if entorno is None else entorno
    plataforma = sys.platform if plataforma is None else plataforma
    candidatos: list[Path] = []
    if plataforma == "win32":
        candidatos += [p for p in _ajustes_docker_desktop(entorno) if p]
        if local := entorno.get("LOCALAPPDATA"):
            candidatos += [Path(local, "Docker", "wsl"), Path(local)]
    elif plataforma == "darwin":
        candidatos.append(
            Path.home() / "Library" / "Containers" / "com.docker.docker" / "Data"
        )
    else:
        candidatos.append(Path("/var/lib/docker"))
    candidatos.append(Path.home())
    for candidato in candidatos:
        existente = _primer_existente(candidato)
        if existente is not None:
            return existente
    return Path(".")


def _ajustes_docker_desktop(entorno: Mapping[str, str]) -> list[Path | None]:
    """Ubicación del disco elegida en los ajustes de Docker Desktop, si la cambiaron."""
    base = entorno.get("APPDATA")
    if not base:
        return []
    encontrados: list[Path | None] = []
    for nombre in ("settings-store.json", "settings.json"):
        with contextlib.suppress(OSError, ValueError):
            datos = json.loads(Path(base, "Docker", nombre).read_text(encoding="utf-8"))
            if isinstance(datos, dict):
                for clave, valor in datos.items():
                    if (
                        str(clave).lower() in _CLAVES_AJUSTES
                        and isinstance(valor, str)
                        and valor.strip()
                    ):
                        encontrados.append(Path(valor.strip()))
    return encontrados


def _primer_existente(ruta: Path) -> Path | None:
    for candidata in (ruta, *ruta.parents):
        with contextlib.suppress(OSError):
            if candidata.exists():
                return candidata
    return None


def _libre_en(ruta: Path) -> int | None:
    try:
        return shutil.disk_usage(ruta).free
    except OSError:
        return None


def espacio_libre_bytes() -> int | None:
    """Bytes libres del disco que usa Docker, o None si no se pudo medir."""
    try:
        return _libre_en(carpeta_datos_docker())
    except Exception:  # noqa: BLE001 — medir el espacio nunca debe romper nada
        registro.warning("No se pudo medir el espacio libre del disco.", exc_info=True)
        return None


def _gb(bytes_: float) -> str:
    return f"{bytes_ / BYTES_POR_GB:.1f}".replace(".", ",")


def mensaje_espacio_insuficiente(libre: int, minimo: int) -> str:
    """Texto para personas: cuánto queda, cuánto falta y qué hacer."""
    return (
        f"Queda poco espacio en el disco que usa Docker: {_gb(libre)} GB libres y "
        f"QAgent necesita al menos {_gb(minimo)} GB para preparar el entorno aislado "
        f"(faltan {_gb(minimo - libre)} GB). Libera espacio en ese disco (vacía la "
        "papelera, borra archivos grandes que no uses o desinstala programas) y "
        "vuelve a intentar."
    )


def verificar_espacio_libre(
    limites: LimitesDisco | None = None,
    libre: Callable[[], int | None] | None = None,
) -> None:
    """Falla si no hay espacio suficiente para construir o descargar una imagen.

    Args:
        limites: límites de `[disco]`; si es None se leen de config.toml.
        libre: función que devuelve los bytes libres (por defecto, `espacio_libre_bytes`).

    Raises:
        EspacioInsuficiente: si el espacio libre está por debajo del mínimo.
    """
    limites = limites or leer_limites_disco()
    minimo = limites.espacio_libre_minimo_bytes
    if minimo is None:
        return
    disponible = (libre or espacio_libre_bytes)()
    if disponible is None or disponible >= minimo:
        return
    raise EspacioInsuficiente(mensaje_espacio_insuficiente(disponible, minimo))


def estado_espacio(
    limites: LimitesDisco | None = None,
    libre: Callable[[], int | None] | None = None,
) -> dict[str, str]:
    """Estado del espacio libre para la verificación del entorno (EN-06).

    Returns:
        `{"estado": "ok" | "poco" | "desconocido", "mensaje": str}`. Nunca lanza.
    """
    try:
        limites = limites or leer_limites_disco()
        disponible = (libre or espacio_libre_bytes)()
    except Exception:  # noqa: BLE001
        disponible, limites = None, LimitesDisco()
    if disponible is None:
        return {
            "estado": "desconocido",
            "mensaje": "No se pudo medir el espacio libre del disco.",
        }
    minimo = limites.espacio_libre_minimo_bytes if limites else None
    if minimo is not None and disponible < minimo:
        return {
            "estado": "poco",
            "mensaje": mensaje_espacio_insuficiente(disponible, minimo)
            + " Solo hace falta para preparar el entorno la primera vez.",
        }
    return {
        "estado": "ok",
        "mensaje": f"{_gb(disponible)} GB libres en el disco de Docker.",
    }
