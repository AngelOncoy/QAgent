"""Bloqueo de una corrida en curso (#139).

Mientras una corrida se ejecuta, el proceso de QAgent mantiene bloqueado el archivo
`runs/<run_id>/.en_curso.lock` con un bloqueo del sistema operativo. Si la app se
cierra o se cae, el sistema libera el bloqueo solo. Así, una corrida que figura
«en curso» pero cuyo bloqueo está libre (o que no tiene archivo de bloqueo) quedó
interrumpida, sin depender de PID que se reutilizan.

No se usa `os.kill(pid, 0)`: en Windows no comprueba un proceso, lo termina.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import IO

ARCHIVO_BLOQUEO = ".en_curso.lock"


def _bloquear(archivo: IO[bytes]) -> None:
    """Bloqueo exclusivo sin esperar; lanza OSError si otro lo tiene."""
    archivo.seek(0)
    if sys.platform == "win32":
        import msvcrt

        msvcrt.locking(archivo.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(archivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _desbloquear(archivo: IO[bytes]) -> None:
    archivo.seek(0)
    if sys.platform == "win32":
        import msvcrt

        msvcrt.locking(archivo.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(archivo.fileno(), fcntl.LOCK_UN)


class BloqueoCorrida:
    """Bloqueo que mantiene el proceso que ejecuta una corrida.

    Uso: `bloqueo = BloqueoCorrida.tomar(carpeta_run)` al empezar y
    `bloqueo.liberar()` al terminar (en un `finally`).
    """

    def __init__(self, ruta: Path, archivo: IO[bytes]) -> None:
        self.ruta = ruta
        self._archivo: IO[bytes] | None = archivo

    @classmethod
    def tomar(cls, carpeta_run: str | Path) -> BloqueoCorrida:
        """Crea y bloquea el archivo de la corrida.

        Raises:
            OSError: si no se puede crear o ya lo bloquea otro proceso.
        """
        ruta = Path(carpeta_run) / ARCHIVO_BLOQUEO
        ruta.parent.mkdir(parents=True, exist_ok=True)
        archivo = open(ruta, "a+b")  # noqa: SIM115 — se mantiene abierto a propósito
        try:
            _bloquear(archivo)
        except OSError:
            archivo.close()
            raise
        return cls(ruta, archivo)

    def liberar(self) -> None:
        """Suelta el bloqueo y borra el archivo. Se puede llamar más de una vez."""
        if self._archivo is None:
            return
        try:
            _desbloquear(self._archivo)
        except OSError:
            pass  # cerrar el archivo también lo libera
        finally:
            self._archivo.close()
            self._archivo = None
        try:
            self.ruta.unlink()
        except OSError:
            pass


def corrida_activa(carpeta_run: str | Path) -> bool:
    """Si algún proceso de QAgent está ejecutando la corrida de esa carpeta.

    Sin archivo de bloqueo (corridas anteriores a #139, o registradas sin lanzarse)
    no hay nadie ejecutándola. Si el bloqueo se puede tomar, nadie lo tenía.
    """
    ruta = Path(carpeta_run) / ARCHIVO_BLOQUEO
    if not ruta.is_file():
        return False
    try:
        archivo = open(ruta, "a+b")  # noqa: SIM115
    except OSError:
        return True  # no se puede abrir: por prudencia, se considera activa
    try:
        _bloquear(archivo)
    except OSError:
        archivo.close()
        return True
    try:
        _desbloquear(archivo)
    finally:
        archivo.close()
    return False


__all__ = ["ARCHIVO_BLOQUEO", "BloqueoCorrida", "corrida_activa"]
