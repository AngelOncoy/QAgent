"""Detalle técnico acotado de fallos de preparación, independiente del lenguaje."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from qagent.almacenamiento import AlmacenProyecto, ErrorAlmacen
from qagent.almacenamiento.disco import escribir_texto_atomico
from qagent.storage.exportar_informe import sanitizar_secretos


def sanear_diagnostico(log: str) -> str:
    """Acota texto técnico y oculta credenciales, URLs privadas y códigos ANSI."""

    def url_limpia(coincidencia: re.Match[str]) -> str:
        try:
            url = urlsplit(coincidencia[0])
            return urlunsplit(
                (url.scheme, url.netloc.rsplit("@", 1)[-1], url.path, "", "")
            )
        except ValueError:
            return "[URL omitida]"

    texto = log.encode("utf-8")[:524_288].decode("utf-8", errors="ignore")
    texto = re.sub(r"\x1b\[[0-9;]*m", "", texto)
    texto = re.sub(r"https?://[^\s<>]+", url_limpia, texto)
    texto = re.sub(
        r"""(?im)(\b(?:password|passphrase|token|secret|authorization|api[_-]?key)\b["']?\s*[=:]\s*)(?:(?:Bearer|Basic)\s+)?(?:"[^"\n]*"|'[^'\n]*'|[^\s,;]+)""",
        r"\1[oculto]",
        texto,
    )
    return (
        sanitizar_secretos(texto)
        .encode("utf-8")[:524_288]
        .decode("utf-8", errors="ignore")
    )


def guardar_diagnostico(raiz: Path, run_id: str | None, error: Exception) -> str | None:
    """Guarda hasta 512 KiB del log sin credenciales y devuelve su ruta relativa.

    Un fallo de escritura nunca reemplaza la causa original de preparación.
    """
    log = getattr(error, "log", None)
    if not run_id or not isinstance(log, str) or not log:
        return None

    try:
        texto = sanear_diagnostico(log)
        destino = AlmacenProyecto(raiz).carpeta_run(run_id) / "entorno.log"
        destino.parent.mkdir(parents=True, exist_ok=True)
        escribir_texto_atomico(destino, texto)
        return destino.relative_to(raiz).as_posix()
    except (OSError, ValueError, ErrorAlmacen):
        return None
